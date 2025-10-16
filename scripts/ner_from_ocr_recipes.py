#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Recettes Prodigy pour NER sur OCR corrigé (TRANSCRIPTION UNIQUEMENT) + alertes Obsidian.

Ce fichier fournit deux recettes :

1) ner.manual.ocr
   - Annotation 100% manuelle.
   - Lit STRICTEMENT ex['transcription'] (jamais le texte original).
   - Utilise le modèle passé en 2e argument uniquement pour tokeniser (ex: blank:xx).

2) ner.correct.ocr
   - Annotation assistée : suggestions NER d’un modèle spaCy (ex: ton XLM-R).
   - Lit STRICTEMENT ex['transcription'].
   - Optionnel: --kb <vault> et --kb-strict-type true|false pour afficher une bannière
     "À vérifier dans Obsidian" lorsqu’une mention NER ne semble pas exister dans le vault.

Notes :
- Les spans structurels hérités de l’étape OCR (SENDER, RECIPIENT, PLACE, DATE, SUBJECT, PARAGRAPH)
  sont supprimés avant annotation.
- Si un exemple n’a pas de `transcription`, il est ignoré (skip).
"""

from pathlib import Path
from typing import Iterable, List, Optional, Dict, Set
from difflib import SequenceMatcher
import re
import unicodedata
import html

import spacy
from prodigy import recipe, set_hashes
from prodigy.components.db import connect
from prodigy.components.loaders import JSONL
from prodigy.components.preprocess import add_tokens
from prodigy.util import split_string


# ------------------------------- Constantes ---------------------------------

STRUCT_LABELS = {"SENDER", "RECIPIENT", "PLACE", "DATE", "SUBJECT", "PARAGRAPH"}


# ------------------------------ I/O helpers ---------------------------------

def _stream(source: str) -> Iterable[dict]:
    """Charge un flux à partir d'un dataset Prodigy (dataset:NAME) ou d'un JSONL."""
    if source.startswith("dataset:"):
        db = connect()
        name = source.split("dataset:", 1)[1]
        for eg in db.get_dataset(name):
            yield eg
    else:
        for eg in JSONL(source):
            yield eg


def _use_transcript(ex: dict) -> bool:
    """Remplace toujours `text` par `transcription`. Retourne False si vide/absent."""
    tr = ex.get("transcription")
    if isinstance(tr, str) and tr.strip():
        ex["text"] = tr
        # Purge des spans structurels éventuels
        if ex.get("spans"):
            ex["spans"] = [s for s in ex["spans"] if (s.get("label") or "") not in STRUCT_LABELS]
        return True
    return False


def _align(span: dict, tokens: List[dict]) -> Optional[dict]:
    """Aligne un span (start/end) aux indices de tokens de Prodigy."""
    if not tokens:
        return span
    cs, ce = span["start"], span["end"]
    ts = te = None
    for i, t in enumerate(tokens):
        if t["start"] <= cs < t["end"]:
            ts = i
            break
    for i, t in enumerate(tokens):
        if t["start"] < ce <= t["end"]:
            te = i
            break
    if ts is None:
        for i, t in enumerate(tokens):
            if t["start"] <= cs:
                ts = i
    if te is None:
        for i, t in enumerate(tokens):
            if ce <= t["end"]:
                te = i
                break
    if ts is None or te is None:
        return None
    out = dict(span)
    out["token_start"] = ts
    out["token_end"] = te
    out["start"] = tokens[ts]["start"]
    out["end"] = tokens[te]["end"]
    return out


# ------------------------------ KB helpers ----------------------------------

def _norm(s: str) -> str:
    """Normalisation légère pour comparaisons (minuscule, accents retirés, ponctuation simplifiée)."""
    s = (s or "").replace("’", "'").replace("–", "-").replace("—", "-")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^\w\s\-]", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def _tokens_norm(s: str) -> List[str]:
    STOP = {
        "de", "du", "des", "la", "le", "les", "à", "au", "aux", "en", "d", "l", "et",
        "der", "die", "das", "den", "von", "zu", "zur", "zum", "im", "in", "am", "und", "mit"
    }
    return [t for t in _norm(s).split() if t and t not in STOP and len(t) > 1]


def _ngrams(s: str, n=3) -> Set[str]:
    s = _norm(s).replace(" ", "_")
    if len(s) < n:
        return {s}
    return {s[i:i + n] for i in range(len(s) - n + 1)}


def _ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


ID_LINE = re.compile(r"^\s*id\s*:\s*(/id/[\w/\-]+)\s*$", re.I | re.M)
H1 = re.compile(r"^\s*#\s+(.+?)\s*$", re.M)


def _infer_type_from_id(kid: str) -> str:
    k = kid.lower()
    if "/id/person/" in k:
        return "PERSON"
    if "/id/org/" in k:
        return "ORG"
    if "/id/gpe/" in k or "/id/place/" in k:
        return "GPE"
    return ""


def _parse_md_entity(p: Path) -> Optional[dict]:
    """Extrait {id, type, aliases[]} d'une note Obsidian (markdown)."""
    try:
        txt = p.read_text(encoding="utf-8")
    except Exception:
        return None
    m = ID_LINE.search(txt)
    if not m:
        return None
    kid = m.group(1).strip()
    # Titre H1 (nom affiché)
    m2 = H1.search(txt)
    title = m2.group(1).strip() if m2 else p.stem
    aliases = {title}
    # Essaie d'autres métadonnées usuelles
    for pat in (r"prefLabel_fr\s*:\s*(.+)", r"prefLabel_de\s*:\s*(.+)",
                r"alias\s*\(fr\)\s*:\s*(.+)", r"alias\s*\(de\)\s*:\s*(.+)"):
        for mm in re.finditer(pat, txt, flags=re.I):
            aliases.update(a.strip() for a in re.split(r"[;|,]", mm.group(1)) if a.strip())
    return {"id": kid, "type": _infer_type_from_id(kid), "aliases": list(aliases)}


class _KB:
    def __init__(self):
        self.items: Dict[str, dict] = {}
        self.alias_index: Dict[str, Set[str]] = {}
        self.token_index: Dict[str, Set[str]] = {}
        self.surname_index: Dict[str, Set[str]] = {}


def _load_kb_obsidian(vault_dir: str) -> _KB:
    """Parcourt vault/id/**/*.md (ou le vault entier si /id absent)."""
    kb = _KB()
    base = Path(vault_dir) / "id"
    if not base.exists():
        base = Path(vault_dir)
    for p in base.rglob("*.md"):
        row = _parse_md_entity(p)
        if not row:
            continue
        rid = row["id"]
        typ = (row.get("type") or "").upper()
        kb.items[rid] = row
        for a in row["aliases"]:
            an = _norm(a)
            if an:
                kb.alias_index.setdefault(an, set()).add(rid)
            for t in _tokens_norm(a):
                kb.token_index.setdefault(t, set()).add(rid)
            if typ == "PERSON":
                toks = _tokens_norm(a)
                if toks:
                    kb.surname_index.setdefault(toks[-1], set()).add(rid)
    return kb


def _kb_exists(mention: str, label: str, kb: _KB, strict: bool = True, sim_thresh: float = 0.6) -> bool:
    """Heuristique pour juger si une mention existe dans la KB Obsidian."""
    lab = (label or "").upper()
    mnorm = _norm(mention)
    if not mnorm or len(mnorm.replace(" ", "")) < 2:  # Ignorer les mentions trop courtes
        return False

    # 1) alias exact
    ids = kb.alias_index.get(mnorm, set())
    types = {(kb.items[i].get("type") or "").upper() for i in ids}
    if ids and (lab in types or (not strict and types)):
        return True

    # 2) PERSON : nom de famille unique
    if lab == "PERSON":
        toks = _tokens_norm(mention)
        if toks and len(toks[-1]) >= 3:  # Nom de famille d'au moins 3 caractères
            sname = toks[-1]
            cand = kb.surname_index.get(sname, set())
            if len(cand) == 1:
                return True

    # 3) fuzzy avec contraintes renforcées
    mtoks = set(_tokens_norm(mention))
    mention_words = len(mtoks)

    # Ignorer les mentions d'un seul mot court
    if mention_words == 1 and len(list(mtoks)[0]) < 4:
        return False

    m3 = _ngrams(mention, 3)
    cand = set()

    # Collecte plus sélective des candidats
    for t in mtoks:
        if len(t) >= 3:  # Seulement les tokens d'au moins 3 caractères
            cand |= kb.token_index.get(t, set())

    if not cand:
        return False

    # Seuil adaptatif mais plus strict
    adaptive_thresh = sim_thresh
    if lab == "PERSON":
        mention_lower = mention.lower()
        # Spécifique à Elisabeth Müller - seuil plus tolérant mais pas trop
        if (("elisabeth" in mention_lower or "elizabeth" in mention_lower) and
            ("müller" in mention_lower or "mueller" in mention_lower or "muller" in mention_lower)):
            adaptive_thresh = 0.5  # Plus strict qu'avant (était 0.35)
        elif mention_words >= 2:  # Noms composés
            adaptive_thresh = max(0.65, sim_thresh)  # Légèrement plus strict

    for rid in cand:
        if strict and (kb.items[rid].get("type") or "").upper() != lab:
            continue

        for a in kb.items[rid]["aliases"]:
            an = _norm(a)
            alias_words = len(set(_tokens_norm(a)))

            # Éviter de matcher des noms courts avec des noms longs
            if abs(mention_words - alias_words) > 1 and min(mention_words, alias_words) == 1:
                continue

            ratio_score = _ratio(mnorm, an)
            trigram_score = len(m3 & _ngrams(a, 3)) * 2.0 / (len(m3) + len(_ngrams(a, 3)) + 1e-9)

            # Pondération : favoriser la similarité globale
            final_score = 0.7 * ratio_score + 0.3 * trigram_score

            if final_score >= adaptive_thresh:
                return True

    return False


# ------------------------------ Recettes NER --------------------------------

@recipe(
    "ner.manual.ocr",
    dataset=("Dataset de sortie", "positional", None, str),
    model=("Modèle spaCy pour tokeniser (ex: blank:xx)", "positional", None, str),
    source=("Source (dataset:NAME ou path.jsonl)", "positional", None, str),
    label=("Labels NER (ex: PERSON,ORG,GPE)", "option", "l", split_string),
)
def ner_manual_ocr(dataset: str, model: str, source: str, label: List[str]):
    """Annotation NER manuelle STRICTEMENT sur la transcription corrigée."""
    spacy.prefer_gpu()
    nlp = spacy.load(model)

    def preprocess(s: Iterable[dict]) -> Iterable[dict]:
        for ex in s:
            if not _use_transcript(ex):
                continue
            yield ex

    stream = _stream(source)
    stream = preprocess(stream)
    stream = add_tokens(nlp, stream)

    return {
        "dataset": dataset,
        "view_id": "ner_manual",
        "stream": stream,
        "config": {
            "labels": label,
            "auto_count_stream": True,
            "force_stream_order": True,
        },
    }


@recipe(
    "ner.correct.ocr",
    dataset=("Dataset de sortie", "positional", None, str),
    model=("Modèle spaCy (prédictions NER)", "positional", None, str),
    source=("Source (dataset:NAME ou path.jsonl)", "positional", None, str),
    label=("Labels NER (ex: PERSON,ORG,GPE)", "option", "l", split_string),
    kb=("Chemin du vault Obsidian (optionnel)", "option", "K", str),
    kb_strict_type=("Strict par type (true/false)", "option", "S", str),
)
def ner_correct_ocr(
    dataset: str,
    model: str,
    source: str,
    label: Optional[List[str]] = None,
    kb: Optional[str] = None,
    kb_strict_type: str = "true",
):
    """
    Annotation NER assistée :
    - suggestions du modèle spaCy fourni
    - lit STRICTEMENT ex['transcription']
    - si --kb est fourni : bannière 'À vérifier dans Obsidian' pour les mentions inconnues
    """
    spacy.prefer_gpu()
    nlp = spacy.load(model)
    allowed = set(label or ["PERSON", "ORG", "GPE"])

    kb_obj = _load_kb_obsidian(kb) if kb else None
    strict = str(kb_strict_type or "true").lower() in {"1", "true", "t", "yes", "y"}

    def preprocess(s: Iterable[dict]) -> Iterable[dict]:
        for ex in s:
            if not _use_transcript(ex):
                continue
            yield ex

    def add_suggestions(s: Iterable[dict]) -> Iterable[dict]:
        for ex in s:
            doc = nlp(ex["text"])
            preds = [
                {"start": ent.start_char, "end": ent.end_char, "label": ent.label_}
                for ent in doc.ents
                if ent.label_ in allowed
            ]
            toks = ex.get("tokens") or []
            spans = []
            for p in preds:
                a = _align(p, toks) if toks else p
                if a:
                    spans.append(a)
            ex["spans"] = spans

            # Bannière d'alerte KB si demandée
            if kb_obj:
                import uuid  # Import local pour éviter les problèmes
                alerts = []
                for sspan in spans:
                    st, en = sspan["start"], sspan["end"]
                    lab = sspan["label"]
                    mention = ex["text"][st:en]
                    if not _kb_exists(mention, lab, kb_obj, strict=strict):
                        # Générer un UUID avec préfixe selon le type
                        if lab.upper() == "PERSON":
                            suggested_uid = f"/id/person/{uuid.uuid4()}"
                        elif lab.upper() == "ORG":
                            suggested_uid = f"/id/org/{uuid.uuid4()}"
                        elif lab.upper() == "GPE":
                            suggested_uid = f"/id/gpe/{uuid.uuid4()}"
                        else:
                            suggested_uid = f"/id/{uuid.uuid4()}"

                        alerts.append(f"vérifier: {mention} ({lab}) → UID: {suggested_uid}")

                if alerts:
                    ex.setdefault("meta", {})["kb_alerts"] = alerts
                    items = "".join(f"<li>{html.escape(a)}</li>" for a in alerts)
                    ex["html"] = (
                        '<div style="background:#fff3cd;border:1px solid #ffeeba;'
                        'color:#856404;border-radius:8px;padding:10px;margin-bottom:10px;">'
                        '<strong>À vérifier dans Obsidian :</strong>'
                        f'<ul style="margin:6px 0 0 18px;">{items}</ul></div>'
                    )

            yield set_hashes(ex, input_keys=("text",), task_keys=("text", "spans"))

    stream = _stream(source)
    stream = preprocess(stream)          # applique transcription-only + purge des spans structurels
    stream = add_tokens(nlp, stream)     # tokenise pour alignement
    stream = add_suggestions(stream)     # ajoute les suggestions + éventuelle bannière

    config = {
        "labels": sorted(list(allowed)),
        "auto_count_stream": True,
        "force_stream_order": True,
    }

    if kb_obj:
        # On utilise la vue "blocks" pour afficher la bannière + l'éditeur NER
        return {
            "dataset": dataset,
            "view_id": "blocks",
            "stream": stream,
            "config": {
                **config,
                "blocks": [{"view_id": "html"}, {"view_id": "ner_manual"}],
            },
        }
    else:
        # Sinon, on garde l'éditeur NER standard
        return {
            "dataset": dataset,
            "view_id": "ner_manual",
            "stream": stream,
            "config": config,
        }
