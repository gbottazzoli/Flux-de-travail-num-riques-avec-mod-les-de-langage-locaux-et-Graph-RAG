#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
pdf_ocr_correct_meta.py
---------------------------------
Recette Prodigy : OCR sur zones (issues de pdf.image.manual) + correction UI.
- OCR zone par zone (pytesseract), rendu page par page (pypdfium2)
- Sidecar metadata.* (yaml/json) fusionné dans meta visible
- Nettoyage léger de texte + normalisation du champ 'transcription'
- Détection de langue (si dispo) sur PARAGRAPH, propagée document-wide
- Règle spéciale : SUBJECT → suppression de tous les espaces
- Normalisation ANCRE (DATE d’en-tête) → champs meta: date_*
- Extraction dates inline (PARAGRAPH) ancrées + résumé doc-niveau

Cmd (exemple) :
    COLLECTION="elisabeth_mueller"
    prodigy -F ./recipe/pdf_ocr_correct_meta.py \
      pdf.ocr.correct.meta \
      02_ocr_correct_${COLLECTION} \
      dataset:01_ocr_raw_${COLLECTION} \
      --labels SENDER,RECIPIENT,PLACE,DATE,SUBJECT,PARAGRAPH \
      --lang deu+fra --scale 3 --fold-dashes --remove-base64
"""

import base64
import json
import re
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Optional

import pypdfium2 as pdfium
import pytesseract
from PIL import Image
from prodigy import ControllerComponentsDict, recipe, set_hashes
from prodigy.components.stream import get_stream
from prodigy.util import msg, split_string

# Normaliseur d’ancre (DATE) + dates inline (PARAGRAPH)
from scripts.date_norm_02_anchor import (
    normalize_anchor_date,
    extract_and_normalize_inline_dates,
)

# ---------- Sidecar YAML/JSON (optionnel) ----------
try:
    import yaml  # pip install pyyaml
except ImportError:
    yaml = None

SIDECARS = ("metadata.yaml", "metadata.yml", "metadata.yalm", "metadata.json")


def _load_sidecar(folder: Path) -> Dict:
    """Charge metadata.yaml/.yml/.yalm/.json si présent dans le dossier."""
    for name in SIDECARS:
        p = folder / name
        if not p.exists():
            continue
        try:
            if p.suffix.lower() in (".yaml", ".yml", ".yalm"):
                if not yaml:
                    msg.warn(f"PyYAML not installed → {p.name} ignored")
                    continue
                data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            else:
                data = json.loads(p.read_text(encoding="utf-8")) or {}
            return data if isinstance(data, dict) else {}
        except Exception as e:
            msg.warn(f"Invalid sidecar {p}: {e}")
    return {}


# ---------- Détection de langue (post-OCR, via langdetect si dispo) ----------
try:
    from langdetect import detect, DetectorFactory

    DetectorFactory.seed = 0  # stabilité

    def _detect_lang_2letter(text: str) -> Optional[str]:
        txt = (text or "").strip()
        if not txt:
            return None
        try:
            return detect(txt)  # 'de', 'fr', ...
        except Exception:
            return None

except Exception:
    def _detect_lang_2letter(text: str) -> Optional[str]:
        return None


# ---------- Helpers ----------
def page_to_cropped_image(pil_page: Image.Image, span: Dict, scale: int):
    """Découpe la zone annotée, retourne crop + data URI JPEG (base64)."""
    left, upper = span["x"], span["y"]
    right, lower = left + span["width"], upper + span["height"]
    scaled = (left * scale, upper * scale, right * scale, lower * scale)
    cropped = pil_page.crop(scaled)
    with BytesIO() as buffered:
        cropped.save(buffered, format="JPEG")
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
    return cropped, f"data:image/jpeg;base64,{img_str}"


def fold_ocr_dashes(text: str) -> str:
    """Rejoint uniquement les mots coupés par un tiret EN FIN DE LIGNE."""
    out, buf = [], ""
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.endswith("-"):
            buf += line[:-1]
        else:
            buf += line
            out.append(buf)
            buf = ""
    if buf:
        out.append(buf)
    return "\n".join(out)


def _normalize_to_one_paragraph(s: str) -> str:
    """Normalise la transcription en un seul paragraphe (utile pour NER)."""
    parts = []
    for line in s.splitlines():
        if not line.strip():
            continue
        parts.append(" ".join(line.split()))
    return " ".join(parts).strip()


def _validate_ocr_example(stream):
    """Validation comme dans le plugin pdf_ocr (attend meta.path/page)."""
    for eg in stream:
        if "meta" not in eg:
            raise ValueError("Missing meta key (did you use pdf.image.manual ?)")
        if "path" not in eg:
            raise ValueError("Missing path key (did you use pdf.image.manual ?)")
        if "page" not in eg["meta"]:
            raise ValueError("Missing meta.page (did you use pdf.image.manual ?)")
        yield eg


def _clean_spaces_keep_lines(s: str) -> str:
    """Trim par ligne + compaction des espaces multiples, conserve les retours ligne."""
    lines = []
    for line in s.splitlines():
        line = " ".join(line.split())
        lines.append(line)
    return "\n".join(lines).strip()


def _strip_all_whitespace(s: str) -> str:
    """Supprime absolument tous les espaces (y compris \n, \t, etc.)."""
    return re.sub(r"\s+", "", s or "")


# --- Tesseract lang sanitizer (2->3 lettres + combinaisons) ---
_TESS_MAP = {"fr": "fra", "fre": "fra", "de": "deu", "ger": "deu", "deu": "deu", "fra": "fra", "eng": "eng"}
def _tess_lang(s: str) -> str:
    if not s: return "eng"
    parts = re.split(r"[+,; ]+", s.strip())
    mapped = []
    for p in parts:
        p = p.strip().lower()
        mapped.append(_TESS_MAP.get(p, p))  # garde tel quel si déjà OK
    return "+".join(mapped)


# ---------- Recette principale ----------
@recipe(
    "pdf.ocr.correct.meta",
    dataset=("Dataset to save answers to", "positional", None, str),
    source=("Source with PDF Annotations", "positional", None, str),
    labels=("Labels to consider", "option", "l", split_string),
    lang=("Language hint for Tesseract (e.g. 'deu+fra')", "option", "la", str),
    scale=("Zoom scale. Increase above 3 to upscale the image for OCR.", "option", "s", int),
    remove_base64=("Remove base64-encoded image data", "flag", "R", bool),
    fold_dashes=("Removes dashes at the end of a textline and folds them with the next term.", "flag", "f", bool),
    autofocus=("Autofocus on the transcript UI", "flag", "af", bool),
)
def pdf_ocr_correct_meta(
    dataset: str,
    source: str,
    labels: List[str],
    lang: str = "deu+fra",
    scale: int = 3,
    remove_base64: bool = False,
    fold_dashes: bool = False,
    autofocus: bool = False,
) -> ControllerComponentsDict:

    stream = get_stream(source)
    stream = _validate_ocr_example(stream)

    # Lang détectée au premier PARAGRAPH du doc (propagée)
    doc_lang_cache: Dict[str, str] = {}
    doc_anchor_cache: Dict[str, str] = {}  # title -> anchor_date_norm (ISO)

    def new_stream(inner_stream, lang_hint):
        for ex in inner_stream:
            useful_spans = [s for s in ex.get("spans", []) if s["label"] in labels]
            if not useful_spans:
                continue

            pdf = pdfium.PdfDocument(ex["path"])
            page = pdf.get_page(ex["meta"]["page"])
            pil_page = page.render(scale=scale).to_pil()

            side = _load_sidecar(Path(ex["path"]).parent)
            doc_key = ex.get("meta", {}).get("title")

            # Ordre : DATE → entêtes → PARAGRAPH
            dates = [s for s in useful_spans if s.get("label") == "DATE"]
            headers = [s for s in useful_spans if s.get("label") in ("SENDER","RECIPIENT","PLACE","SUBJECT")]
            paragraphs = [s for s in useful_spans if s.get("label") == "PARAGRAPH"]
            # (on garde l’ordre d’annotation à l’intérieur de chaque groupe)
            ordered_spans = dates + headers + paragraphs

            for annot in ordered_spans:
                cropped, img_str = page_to_cropped_image(pil_page, span=annot, scale=scale)
                text = pytesseract.image_to_string(cropped, lang=_tess_lang(lang_hint))
                if fold_dashes:
                    text = fold_ocr_dashes(text)

                text_ui = _clean_spaces_keep_lines(text)

                # >>> Règle spéciale : SUBJECT = supprimer tous les espaces
                if annot.get("label") == "SUBJECT":
                    text_ui = _strip_all_whitespace(text_ui)

                # Détection de langue au premier paragraphe du doc
                if annot.get("label") == "PARAGRAPH" and doc_key and doc_key not in doc_lang_cache:
                    lang_det = _detect_lang_2letter(text_ui)
                    if lang_det:
                        doc_lang_cache[doc_key] = lang_det

                annot["image"] = img_str
                annot["text"] = text_ui
                annot["transcription"] = text_ui

                merged_meta = dict(ex.get("meta") or {})
                merged_meta.update(side)  # sidecar prioritaire
                merged_meta["tesseract_lang"] = lang_hint
                if doc_key in doc_lang_cache:
                    merged_meta["lang_detected"] = doc_lang_cache[doc_key]
                annot["meta"] = merged_meta

                text_input_fields = {
                    "field_rows": 12,
                    "field_label": "Transcript",
                    "field_id": "transcription",
                    "field_autofocus": autofocus,
                }
                annot.pop("id", None)

                yield set_hashes({**annot, **text_input_fields})

    stream = new_stream(stream, lang)

    def before_db(examples):
        # 0) Normalisations communes + propagation langue
        for eg in examples:
            t = eg.get("transcription")
            if isinstance(t, str) and eg.get("label") != "SUBJECT":
                eg["transcription"] = _normalize_to_one_paragraph(t)

            if isinstance(eg.get("text"), str):
                eg["text"] = _clean_spaces_keep_lines(eg["text"])

            if remove_base64 and isinstance(eg.get("image"), str) and eg["image"].startswith("data:"):
                del eg["image"]

            meta = eg.get("meta") or {}
            doc_key = meta.get("title")
            if doc_key and doc_key in doc_lang_cache:
                meta["lang_detected"] = doc_lang_cache[doc_key]
            eg["meta"] = meta

        # 1) Calcul des ancres (DATE)
        for eg in examples:
            label = str(eg.get("label", "")).upper()
            if label != "DATE":
                continue
            meta = eg.get("meta") or {}

            raw = eg.get("transcription") or ""  # valeur corrigée par toi
            # Langue de la zone: zone > meta > doc-wide
            lang_hint = (
                eg.get("lang") or eg.get("language")
                or meta.get("lang") or meta.get("language")
                or meta.get("lang_detected")
            )
            norm = normalize_anchor_date(raw, lang_hint)

            # Fallback: première année à 4 chiffres depuis meta.date_creation
            if not norm.get("date_norm"):
                dc = meta.get("date_creation")
                m = re.search(r"\b((18|19|20)\d{2})\b", str(dc) if dc is not None else "")
                if m:
                    y = int(m.group(1))
                    norm = {
                        "date_raw": f"{y}",
                        "date_norm": f"{y:04d}-01-01",
                        "date_precision": "year",
                        "date_imputed": True,
                        "date_rules_applied": ["FALLBACK_META_DATE_CREATION", "IMPUTE_MONTH_DAY"],
                        "anchor_date_norm": f"{y:04d}-01-01",
                        "anchor_date_lang": "unknown",
                    }
                else:
                    norm = {
                        "date_raw": raw,
                        "date_norm": None,
                        "date_precision": "unknown",
                        "date_imputed": False,
                        "date_rules_applied": ["UNPARSED", "NO_ANCHOR"],
                        "anchor_date_norm": None,
                        "anchor_date_lang": (norm.get("anchor_date_lang") or "unknown"),
                    }

            meta.update({
                "date_raw": norm.get("date_raw"),
                "date_norm": norm.get("date_norm"),
                "date_precision": norm.get("date_precision"),
                "date_imputed": norm.get("date_imputed"),
                "date_rules_applied": norm.get("date_rules_applied"),
                "anchor_date_norm": norm.get("anchor_date_norm"),
                "anchor_date_lang": norm.get("anchor_date_lang"),
            })
            eg["meta"] = meta

            if meta.get("anchor_date_norm"):
                title = meta.get("title") or meta.get("file_title")
                if title:
                    doc_anchor_cache[title] = meta["anchor_date_norm"]

        # 2) Dates internes dans PARAGRAPH (ancrées) + résumé
        # Agrégat doc → dates ISO
        doc_inline_acc: Dict[str, List[str]] = {}

        for eg in examples:
            label = str(eg.get("label", "")).upper()
            if label != "PARAGRAPH":
                continue
            meta = eg.get("meta") or {}
            title = meta.get("title") or meta.get("file_title")

            # ancre: cache > meta.anchor_date_norm > fallback meta.date_creation
            anchor = None
            if title and title in doc_anchor_cache:
                anchor = doc_anchor_cache[title]
            if not anchor:
                anchor = meta.get("anchor_date_norm")
            if not anchor:
                dc = meta.get("date_creation")
                m = re.search(r"\b((18|19|20)\d{2})\b", str(dc) if dc is not None else "")
                if m:
                    anchor = f"{int(m.group(1)):04d}-01-01"

            # langue: zone > meta > doc-wide
            lang_hint = (
                eg.get("lang") or eg.get("language")
                or meta.get("lang") or meta.get("language")
                or meta.get("lang_detected")
            )

            raw_text = eg.get("transcription") or ""
            try:
                inlines = extract_and_normalize_inline_dates(raw_text, lang_hint, anchor)
            except Exception:
                inlines = []

            # Traçabilité paragraphe
            meta["date_inline"] = inlines
            meta["date_inline_anchor"] = anchor
            meta["date_inline_lang"] = (lang_hint or None)
            eg["meta"] = meta

            # Agrégat doc
            if title:
                acc = doc_inline_acc.setdefault(title, [])
                acc.extend([d["norm"] for d in inlines if d.get("norm")])

        # 3) Résumé doc-niveau (count / first / last)
        for eg in examples:
            meta = eg.get("meta") or {}
            title = meta.get("title") or meta.get("file_title")
            if not title:
                continue
            iso_list = sorted([x for x in (doc_inline_acc.get(title) or []) if isinstance(x, str)])
            meta["date_inline_summary"] = {
                "count": len(iso_list),
                "first": iso_list[0] if iso_list else None,
                "last": iso_list[-1] if iso_list else None,
            }
            eg["meta"] = meta

        return examples

    blocks = [{"view_id": "classification"}, {"view_id": "text_input"}]

    return {
        "dataset": dataset,
        "stream": stream,
        "before_db": before_db,
        "view_id": "blocks",
        "config": {"blocks": blocks},
    }
