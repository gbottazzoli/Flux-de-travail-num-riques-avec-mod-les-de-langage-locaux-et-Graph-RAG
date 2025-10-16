#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
el_from_ocr_recipes.py  (Obsidian-only, robust FR/DE & multi-block safe)

Recette Prodigy: el.link.ocr
----------------------------
- Source: dataset NER (ex: dataset:03_...)
- KB: Obsidian vault (racine) avec fiches sous <root>/id/**/*.md
- UI: propose des choix clairement lisibles:
      [TYPE]  [FR] ...  | [DE] ...  —  /id/...

Caractéristiques
- Aucun CSV requis.
- Cross-type par défaut (PERSON/ORG/GPE) avec petit bonus pour le type cible.
- Pour limiter aux candidats du type cible, utiliser --strict-type true
  (activé automatiquement pour PERSON & GPE, OFF pour ORG).
- Parsing robuste: garde la PREMIÈRE valeur de label FR/DE rencontrée (n’écrase pas
  si un second bloc-modèle est présent en bas de page); alias cumulés.
"""

import re, unicodedata, json
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional, Set

from prodigy import recipe, set_hashes
from prodigy.components.stream import get_stream

try:
    import yaml  # facultatif
except Exception:
    yaml = None

# =======================
# Hyperparamètres simples
# =======================
TOP_N = 25
CTX_RADIUS = 80
W_MENTION = 0.30
W_CONTEXT = 0.70
BONUS_EXACT_MENTION = 25.0
BONUS_SAME_TYPE = 8.0
PENALTY_ZERO_TOKEN_OVERLAP = 15.0

# ---- utilitaires flags/valeurs ----
def _as_bool(v):
    if isinstance(v, bool):
        return v
    s = (v or "").strip().lower()
    return s in {"1","true","t","yes","y","on","oui","o"}

# ---- Headwords (optionnels, OFF par défaut) ----
def _load_headword_groups(path):
    if not path:
        return []
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [set(map(str.lower, grp)) for grp in data if isinstance(grp, list)]
    except Exception:
        pass
    return []

def _headword_group(tokens, groups):
    if not groups:
        return None
    toks = set(tokens)
    for i, group in enumerate(groups):
        if toks.intersection(group):
            return i
    return None

# -----------------
# Normalisation / tokens
# -----------------
def _norm(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower()
    s = re.sub(r"[^\w\s\-]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()

def _tokens(s):
    STOP_TOK = {
        "de","du","des","la","le","les","à","au","aux","en","d","l","et","pour","sur","dans",
        "der","die","das","den","von","zu","zur","zum","im","in","am","und","mit",
        "of","the","for","to","at","in","on","by","and","or"
    }
    return [t for t in _norm(s).split() if t and t not in STOP_TOK and len(t) > 1]

def _ratio(a, b):
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()

def _context_window(text, start, end, radius=CTX_RADIUS):
    a = max(0, start - radius)
    b = min(len(text), end + radius)
    return text[a:b]

# ----------------------------
# Lecture KB (Obsidian .md)
# ----------------------------
# Regex robustes : group(1) = valeur
LABEL_FR_PAT = re.compile(r"label\s*pr(?:é|e)f(?:é|e)r(?:é|e)\s*\(fr\)\s*:\s*(.+)", re.I)
LABEL_DE_PAT = re.compile(r"(?:bevorzugt\w*\s*)?label\s*\(de\)\s*:\s*(.+)", re.I)
ALIAS_FR_PAT = re.compile(r"alias\s*\(fr\)\s*:\s*(.+)", re.I)
ALIAS_DE_PAT = re.compile(r"alias\s*\(de\)\s*:\s*(.+)", re.I)
ID_LINE_PAT  = re.compile(r"^\s*(?:\*\*)?\s*ID\s*(?:\*\*)?\s*:\s*(/id/[\w/\-]+)", re.I)
H1_TITLE_PAT = re.compile(r"^\s*#\s+(.+?)\s*$")

def _strip_md(s):
    s = re.sub(r"\*\*(.*?)\*\*", r"\1", s)  # enlève **bold**
    s = re.sub(r"^\-\s*", "", s)            # enlève "- " puces
    return s.strip()

def _extract_yaml_block(txt):
    if not txt.startswith("---"):
        return None, txt
    parts = txt.split("\n")
    if len(parts) < 3:
        return None, txt
    end_idx = None
    for i in range(1, min(200, len(parts))):
        if parts[i].strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        return None, txt
    yml_text = "\n".join(parts[1:end_idx])
    rest = "\n".join(parts[end_idx+1:])
    if yaml:
        try:
            data = yaml.safe_load(yml_text) or {}
            if isinstance(data, dict):
                return data, rest
        except Exception:
            pass
    # fallback: id: "/id/…"
    m = re.search(r'^\s*id\s*:\s*"?([^"\n]+)"?\s*$', yml_text, flags=re.M)
    data = {"id": m.group(1).strip()} if m else {}
    return data, rest

def _infer_type_from_id(kid):
    k = (kid or "").strip().lower()
    if "/id/person/" in k:
        return "PERSON"
    if "/id/org/" in k:
        return "ORG"
    if "/id/gpe/" in k or "/id/place/" in k:
        return "GPE"
    return ""

def _split_aliases(s):
    return [a.strip() for a in re.split(r"[;,|]", s or "") if a.strip()]

def _parse_md_entity(path):
    """Lit une fiche et renvoie un dict {id,type,prefLabel_fr,prefLabel_de,altLabel_fr,altLabel_de}.

    - Si plusieurs blocs "Noms / Labels" existent (modèle recopié), on **garde la première** valeur FR/DE rencontrée
      et on n’écrase pas par la suite. Les alias s’additionnent.
    - Si aucun label FR/DE trouvé, on prend le H1 (# Titre) comme fallback FR.
    """
    try:
        txt = path.read_text(encoding="utf-8")
    except Exception:
        return None

    yml, body = _extract_yaml_block(txt)
    kid = (yml or {}).get("id") if isinstance(yml, dict) else None

    title_fallback = ""
    for ln in body.splitlines():
        m = H1_TITLE_PAT.match(ln)
        if m:
            title_fallback = m.group(1).strip()
            break

    if not kid:
        for line in body.splitlines():
            m = ID_LINE_PAT.search(_strip_md(line))
            if m:
                kid = m.group(1).strip()
                break
    if not kid or not str(kid).startswith("/id/"):
        return None

    pref_fr = (yml or {}).get("prefLabel_fr") or ""
    pref_de = (yml or {}).get("prefLabel_de") or ""
    alt_fr, alt_de = [], []

    for line in body.splitlines():
        line_s = _strip_md(line)

        m = LABEL_FR_PAT.search(line_s)
        if m and not pref_fr:  # NE PAS écraser si déjà trouvé
            pref_fr = m.group(1).strip()
            continue

        m = LABEL_DE_PAT.search(line_s)
        if m and not pref_de:  # NE PAS écraser si déjà trouvé
            pref_de = m.group(1).strip()
            continue

        m = ALIAS_FR_PAT.search(line_s)
        if m:
            alt_fr.extend(_split_aliases(m.group(1)))
            continue

        m = ALIAS_DE_PAT.search(line_s)
        if m:
            alt_de.extend(_split_aliases(m.group(1)))
            continue

    if not pref_fr and title_fallback:
        # fallback raisonnable: titre FR si rien d'autre
        pref_fr = title_fallback

    rtype = _infer_type_from_id(kid)
    return {
        "id": str(kid),
        "type": rtype,
        "prefLabel_fr": pref_fr,
        "prefLabel_de": pref_de,
        "altLabel_fr": ";".join(alt_fr) if alt_fr else "",
        "altLabel_de": ";".join(alt_de) if alt_de else "",
    }

def _make_aliases(row):
    aliases = set()
    for k in ("prefLabel_fr","prefLabel_de","altLabel_fr","altLabel_de"):
        val = (row.get(k) or "").replace("|",";")
        for a in [x.strip() for x in val.split(";") if x.strip()]:
            aliases.add(a)
            aliases.add(a.upper())
    aliases_norm = {_norm(a) for a in aliases if a.strip()}
    alias_tokens = set()
    for a in aliases:
        alias_tokens.update(_tokens(a))
    return sorted(aliases), sorted(a for a in aliases_norm if a), alias_tokens

def load_kb_obsidian(root_dir):
    """
    Parcourt <root>/id/**/*.md et indexe les fiches.
    Retourne:
      - items: id -> row (+ _aliases / _aliases_norm / _alias_tokens)
      - alias_index: alias_norm -> set(ids)  (tous types)
      - token_index: token -> set(ids)       (tous types)
    """
    items: Dict[str, Dict[str, str]] = {}
    alias_index: Dict[str, Set[str]] = {}
    token_index: Dict[str, Set[str]] = {}

    root = Path(root_dir) / "id"
    for p in root.rglob("*.md"):
        row = _parse_md_entity(p)
        if not row:
            continue
        rid = (row.get("id") or "").strip()
        if not rid:
            continue

        aliases, aliases_norm, alias_toks = _make_aliases(row)
        row["_aliases"] = aliases
        row["_aliases_norm"] = aliases_norm
        row["_alias_tokens"] = alias_toks
        items[rid] = row

        for an in aliases_norm:
            alias_index.setdefault(an, set()).add(rid)
        for tok in alias_toks:
            token_index.setdefault(tok, set()).add(rid)

    return items, alias_index, token_index

# -----------------
# Classement
# -----------------
def _all_spans(ex):
    return ex.get("spans") or ex.get("ner_spans") or []

def _rank(mention, ctx_text, items, alias_index, token_index,
          target_type, strict_type=False,
          groups=None, headword_bonus=0.0, headword_penalty=0.0):
    groups = groups or []
    m_norm = _norm(mention)
    c_norm = _norm(ctx_text)
    m_toks = set(_tokens(mention))

    # blocking par tokens + alias exact normalisé
    cand_ids = set()
    for t in m_toks:
        cand_ids |= token_index.get(t, set())
    cand_ids |= alias_index.get(m_norm, set())
    if not cand_ids:
        cand_ids = set(items.keys())

    # restreindre si demandé
    if strict_type:
        cand_ids = {rid for rid in cand_ids if (items[rid].get("type") or "").upper() == target_type}

    want_group = _headword_group(m_toks, groups) if groups else None

    ranked = []
    for rid in cand_ids:
        row = items[rid]
        aliases_norm = row.get("_aliases_norm", [])
        alias_toks   = row.get("_alias_tokens", set())

        best_m = max((_ratio(m_norm, an) for an in aliases_norm), default=0.0)
        best_c = max((_ratio(c_norm, an) for an in aliases_norm), default=0.0)
        score = (W_MENTION * best_m + W_CONTEXT * best_c) * 100.0

        # bonus exact mention
        if m_norm in aliases_norm:
            score += BONUS_EXACT_MENTION

        # petit bonus si type = cible (quand cross-type autorisé)
        if not strict_type and (row.get("type") or "").upper() == target_type:
            score += BONUS_SAME_TYPE

        # recouvrement de tokens
        overlap = len(m_toks & alias_toks)
        if overlap == 0:
            score -= PENALTY_ZERO_TOKEN_OVERLAP
        else:
            score += min(12.0, 4.0 * overlap)

        # headwords (optionnel)
        if groups:
            alias_group = _headword_group(alias_toks, groups)
            if want_group is not None and alias_group is not None:
                if want_group == alias_group and headword_bonus:
                    score += headword_bonus
                elif want_group != alias_group and headword_penalty:
                    score -= headword_penalty

        ranked.append((rid, score))

    ranked.sort(key=lambda x: (
        -x[1],
        items[x[0]].get("prefLabel_fr") or items[x[0]].get("prefLabel_de") or x[0]
    ))
    out, seen = [], set()
    for rid, sc in ranked:
        if rid in seen:
            continue
        seen.add(rid)
        out.append((rid, sc))
        if len(out) >= TOP_N:
            break
    return out

# -------------
# Recette Prodigy
# -------------
@recipe(
    "el.link.ocr",
    dataset=("Dataset sortie", "positional", None, str),
    source=("Source Prodigy (ex: dataset:03_...)", "positional", None, str),
    obsidian_root=("Racine du vault (contient 'id/')", "positional", None, str),
    label=("Label cible (PERSON|ORG|GPE)", "option", "l", str),
    strict_type=("Limiter aux candidats du type cible (true/false)", "option", "S", str),
    enable_headwords=("Activer les headwords (true/false)", "option", "H", str),
    headword_groups=("Chemin JSON groupes headword", "option", "G", str),
    headword_bonus=("Bonus si groupe concorde (float)", "option", "B", float),
    headword_penalty=("Pénalité si groupe diverge (float)", "option", "P", float),
)
def el_link_ocr(dataset, source, obsidian_root,
                label="ORG", strict_type=None,
                enable_headwords=None, headword_groups=None,
                headword_bonus=0.0, headword_penalty=0.0):
    """
    Crée des tâches 'choice' pour chaque mention (PERSON/ORG/GPE) avec options
    issues des fiches Obsidian (<root>/id/**/*.md). Par défaut cross-type.
    """
    target_type = (label or "ORG").strip().upper()
    if target_type not in {"PERSON","ORG","GPE"}:
        raise ValueError("Paramètre -l/--label doit être PERSON, ORG ou GPE")

    # Strict par défaut pour PERSON/GPE, cross-type pour ORG
    if strict_type in (None, ""):
        strict_flag = target_type in {"PERSON", "GPE"}
    else:
        strict_flag = _as_bool(strict_type)

    groups = _load_headword_groups(headword_groups) if _as_bool(enable_headwords) else []

    items, alias_index, token_index = load_kb_obsidian(obsidian_root)

    def make_examples(stream):
        for ex in stream:
            text = ex.get("text") or ""
            spans = _all_spans(ex)
            if not spans:
                continue

            for s in spans:
                if (s.get("label") or "").upper() not in {"PERSON","ORG","GPE"}:
                    continue
                # UI: n'afficher que les spans du type cible
                if (s.get("label") or "").upper() != target_type:
                    continue

                st, en = s.get("start"), s.get("end")
                if not (isinstance(st, int) and isinstance(en, int)):
                    continue
                mention = text[st:en]
                ctx = _context_window(text, st, en, radius=CTX_RADIUS)

                ranked = _rank(
                    mention, ctx, items, alias_index, token_index,
                    target_type, strict_type=strict_flag,
                    groups=groups, headword_bonus=headword_bonus,
                    headword_penalty=headword_penalty
                )

                options = []
                for rid, sc in ranked:
                    row = items[rid]
                    fr = row.get("prefLabel_fr") or ""
                    de = row.get("prefLabel_de") or ""
                    typ = (row.get("type") or "").upper() or "?"
                    disp = f"[{typ}]  [FR] {fr or '—'}  | [DE] {de or '—'}"
                    options.append({"id": rid, "text": f"{disp}  —  {rid}"})

                meta_src = dict(ex.get("meta") or {})
                meta_src.update({
                    "SPAN_LABEL": s.get("label"),
                    "SPAN_TEXT": mention
                })
                task = {
                    "text": text,
                    "spans": [s],
                    "options": options,
                    "meta": meta_src,
                }
                task = set_hashes(task, input_keys=("text",), task_keys=("text","spans","options"))
                yield task

    stream = get_stream(source)
    stream.apply(make_examples)

    return {
        "dataset": dataset,
        "view_id": "choice",
        "stream": stream,
        "config": {"choice_style": "single"},
    }
