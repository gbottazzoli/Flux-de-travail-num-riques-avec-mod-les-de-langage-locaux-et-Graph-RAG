# utils/microaction_parser.py
"""
Parser pour micro-actions depuis documents
"""

import re
import hashlib
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from .wikilink_extractor import WikilinkExtractor, WikilinkWarnings
from .edtf_parser import EDTFParser


class MicroActionParser:
    """Parse les micro-actions depuis documents Obsidian"""

    MICRO_BLOCK_RE = re.compile(
        r'(?m)^#micro_id:\s*(.+?)\s*$([\s\S]*?)(?=^#(?:event_id|micro_id):|^---|\Z)',
        re.MULTILINE
    )
    KV_RE = re.compile(r'^\s*-\s*([A-Za-z0-9_]+)\s*:\s*(.+?)\s*$')

    REPLY_DATE_PATTERNS = [
        (r'Schreiben\s+vom\s+(\d{4}-\d{2}-\d{2})', 'iso'),
        (r'vom\s+(\d{1,2})\.\s*(\w+)\s+(\d{4})', 'de_long'),
        (r'Telegramm\s+(?:Nr\.\s*\d+\s+)?vom\s+(\d{2}\.\d{2}\.\d{4})', 'de_dot'),
        (r'lettre\s+du\s+(\d{1,2})\s+(\w+)\s+(\d{4})', 'fr_long'),
        (r'télégramme\s+du\s+(\d{2}\.\d{2}\.\d{4})', 'fr_dot')
    ]

    MONTH_NAMES = {
        'januar': 1, 'februar': 2, 'märz': 3, 'april': 4,
        'mai': 5, 'juni': 6, 'juli': 7, 'august': 8, 'september': 9,
        'oktober': 10, 'november': 11, 'dezember': 12,
        'janvier': 1, 'février': 2, 'mars': 3, 'avril': 4, 'mai': 5,
        'juin': 6, 'juillet': 7, 'août': 8, 'septembre': 9, 'octobre': 10,
        'novembre': 11, 'décembre': 12
    }

    def __init__(self, vault_path: Path, config: dict, folders: Optional[List[Path]] = None):
        self.vault_path = vault_path
        self.config = config
        self.folders = folders

    def _should_process_file(self, file_path: Path) -> bool:
        """Vérifie si le fichier doit être parsé selon les dossiers sélectionnés"""
        if not self.folders:
            return True

        return any(file_path.is_relative_to(folder) for folder in self.folders)

    def parse_all(self) -> Tuple[List[Dict[str, Any]], WikilinkWarnings]:
        """Parse toutes les micro-actions"""
        microactions = []
        warnings = WikilinkWarnings()

        for file_path in self.vault_path.rglob("*.md"):
            if not self._should_process_file(file_path):
                continue

            try:
                doc_micros = self._parse_microactions_from_file(file_path, warnings)
                microactions.extend(doc_micros)
            except Exception as e:
                warnings.log_parse_error(str(file_path), f"{type(e).__name__}: {str(e)}")

        return microactions, warnings

    def _parse_microactions_from_file(self, file_path: Path, warnings: WikilinkWarnings) -> List[Dict[str, Any]]:
        """Parse micro-actions depuis un fichier"""
        text = file_path.read_text(encoding='utf-8')

        doc_id = self._build_document_id_from_path(file_path)

        microactions = []

        for match in self.MICRO_BLOCK_RE.finditer(text):
            raw_id = match.group(1).strip()
            block_content = match.group(2)

            micro = self._parse_micro_block(raw_id, block_content, doc_id, str(file_path), warnings)
            if micro:
                microactions.append(micro)

        return microactions

    def _parse_micro_block(self, raw_id: str, content: str, doc_id: str,
                           file_path: str, warnings: WikilinkWarnings) -> Optional[Dict[str, Any]]:
        """Parse un bloc micro-action"""
        micro_id = self._canonicalize_micro_id(raw_id)

        data = {'id': raw_id}
        specific_entities = set()

        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("**"):
                continue

            kv = self.KV_RE.match(line)
            if kv:
                key, val = kv.group(1), kv.group(2).strip()

                if key in ['actor', 'recipient', 'about']:
                    entity_id = self._extract_entity_id(val, warnings, file_path, 0)
                    if entity_id:
                        data[f"{key}_id"] = entity_id
                        specific_entities.add(entity_id)
                else:
                    data[key] = val

        # Extraire wikilinks
        all_links = set()
        for field in ['description', 'summary', 'abstract', 'observations']:
            text = data.get(field, '')
            if text:
                all_links.update(WikilinkExtractor.extract_all_wikilinks(
                    text, warnings, file_path
                ))

        # Validation about
        person_refs = [r for r in all_links if '/id/person/' in r]
        if person_refs and not data.get('about_id'):
            warnings.log_missing_about(file_path, micro_id)

        generic_refs = all_links - specific_entities

        # Parse dates
        date_edtf = data.get('date_edtf')
        if date_edtf:
            date_start, date_end, date_precision = EDTFParser.parse(date_edtf)
        else:
            date_start, date_end, date_precision = None, None, 'unknown'

        # Extraction in_reply_to_date
        in_reply_to_date = data.get('in_reply_to_date')
        link_type = data.get('link_type', '')

        if not in_reply_to_date:
            if 'acknowledges_receipt' in link_type or 'replies_to' in link_type:
                full_text = ' '.join([
                    data.get('description', ''),
                    data.get('observations', '')
                ])
                in_reply_to_date = self._extract_reply_date(full_text)

                if in_reply_to_date:
                    warnings.log_in_reply_to_date_extracted(file_path, micro_id, in_reply_to_date)
                else:
                    warnings.log_reply_missing_anchor_date(file_path, micro_id)

        # Normalisation confidence
        confidence_raw = data.get('confidence', '').strip().lower()
        uncertainty_flag = confidence_raw == 'low'
        gap_flag = date_edtf and ('..' in date_edtf)

        properties = {
            'micro_id': micro_id,
            'action_type': data.get('action_type'),
            'tags': data.get('tags', ''),
            'link_type': data.get('link_type'),
            'delivery_channel': data.get('delivery_channel'),
            'date_edtf': date_edtf,
            'date_start': date_start,
            'date_end': date_end,
            'date_precision': date_precision,
            'date_source': data.get('date_source'),
            'in_reply_to_date': in_reply_to_date,
            'actor_id': data.get('actor_id'),
            'recipient_id': data.get('recipient_id'),
            'about_id': data.get('about_id'),
            'place_id': data.get('place_id'),
            'summary': data.get('summary'),
            'description': data.get('description'),
            'abstract': data.get('abstract'),
            'observations': data.get('observations'),
            'uncertainty_flag': uncertainty_flag,
            'gap_flag': gap_flag
        }

        assertion = {
            'assertion_id': f"{micro_id}::assertion",
            'doc_id': doc_id,
            'properties': {
                'type': 'MICROACTION_ASSERTION',
                'confidence': data.get('confidence', 'medium'),
                'evidence_type': data.get('evidence_type', 'reported'),
                'source_quote': data.get('source_quote', ''),
                'page': data.get('page')
            }
        }

        return {
            'micro_id': micro_id,
            'properties': properties,
            'assertion': assertion,
            'references': generic_refs
        }

    def _extract_reply_date(self, text: str) -> Optional[str]:
        """Extrait date de référence depuis texte"""
        for pattern, date_type in self.REPLY_DATE_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                if date_type == 'iso':
                    return match.group(1)
                elif date_type in ['de_long', 'fr_long']:
                    day, month_str, year = match.groups()
                    month = self.MONTH_NAMES.get(month_str.lower(), 0)
                    if month:
                        return f"{year}-{month:02d}-{int(day):02d}"
                elif date_type in ['de_dot', 'fr_dot']:
                    date_str = match.group(1)
                    parts = date_str.split('.')
                    if len(parts) == 3:
                        return f"{parts[2]}-{parts[1]}-{parts[0]}"
        return None

    def _extract_entity_id(self, wikilink: str, warnings: WikilinkWarnings,
                           file_path: str, line_num: int) -> Optional[str]:
        """Extrait ID depuis wikilink"""
        if not wikilink.startswith('[['):
            warnings.log_invalid(file_path, line_num, wikilink, "Not a wikilink")
            return wikilink

        try:
            return WikilinkExtractor.clean_id(wikilink, warnings, file_path, line_num)
        except ValueError:
            return None

    def _canonicalize_micro_id(self, raw_id: str) -> str:
        """Canonicalise micro_id"""
        if raw_id.startswith('/id/microaction/'):
            return raw_id
        return f"/id/microaction/{hashlib.sha1(raw_id.encode('utf-8')).hexdigest()}"

    def _build_document_id_from_path(self, file_path: Path) -> str:
        """Génère doc_id depuis nom fichier (cohérent avec document_parser)"""
        file_name = file_path.name
        h = hashlib.sha1(file_name.encode('utf-8')).hexdigest()
        return f"/id/document/{h}"