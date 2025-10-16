# utils/event_parser.py
"""
Parser pour événements depuis documents
"""

import re
import hashlib
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from .wikilink_extractor import WikilinkExtractor, WikilinkWarnings
from .edtf_parser import EDTFParser


class EventParser:
    """Parse les événements depuis documents Obsidian"""

    EVENT_BLOCK_RE = re.compile(
        r'(?m)^#event_id:\s*(.+?)\s*$([\s\S]*?)(?=^#(?:event_id|micro_id):|^---|\Z)',
        re.MULTILINE
    )
    KV_RE = re.compile(r'^\s*-\s*([A-Za-z0-9_]+)\s*:\s*(.+?)\s*$')
    DESC_PATTERN = re.compile(r'^\*\*\s*Description\s*:?\s*$', re.IGNORECASE)
    OBS_PATTERN = re.compile(r'^\*\*\s*Observations?\s*:?\s*$', re.IGNORECASE)

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
        """Parse tous les événements"""
        events = []
        warnings = WikilinkWarnings()

        for file_path in self.vault_path.rglob("*.md"):
            if not self._should_process_file(file_path):
                continue

            try:
                doc_events = self._parse_events_from_file(file_path, warnings)
                events.extend(doc_events)
            except Exception as e:
                warnings.log_parse_error(str(file_path), f"{type(e).__name__}: {str(e)}")

        return events, warnings

    def _parse_events_from_file(self, file_path: Path, warnings: WikilinkWarnings) -> List[Dict[str, Any]]:
        """Parse événements depuis un fichier"""
        text = file_path.read_text(encoding='utf-8')

        doc_id = self._build_document_id_from_path(file_path)

        events = []

        for match in self.EVENT_BLOCK_RE.finditer(text):
            raw_id = match.group(1).strip()
            block_content = match.group(2)

            event = self._parse_event_block(raw_id, block_content, doc_id, str(file_path), warnings)
            if event:
                events.append(event)

        return events

    def _parse_event_block(self, raw_id: str, content: str, doc_id: str,
                           file_path: str, warnings: WikilinkWarnings) -> Optional[Dict[str, Any]]:
        """Parse un bloc événement"""
        event_id = self._canonicalize_event_id(raw_id)

        data = {'id': raw_id}
        description_text = ""
        observation_text = ""
        in_description = False
        in_observation = False

        specific_entities = set()

        for line in content.splitlines():
            line_stripped = line.strip()

            if self.DESC_PATTERN.match(line_stripped):
                in_description = True
                in_observation = False
                continue
            elif self.OBS_PATTERN.match(line_stripped):
                in_observation = True
                in_description = False
                continue
            elif line_stripped.startswith("**") or line_stripped.startswith("---"):
                in_description = False
                in_observation = False

            if in_description:
                description_text += line + "\n"
            elif in_observation:
                observation_text += line + "\n"

            if not line_stripped or line_stripped.startswith("**"):
                continue

            kv = self.KV_RE.match(line)
            if kv:
                key, val = kv.group(1), kv.group(2).strip()

                if key in ['victim', 'agent', 'place']:
                    entity_id = self._extract_entity_id(val, warnings, file_path, 0)
                    if entity_id:
                        data[f"{key}_id"] = entity_id
                        specific_entities.add(entity_id)
                else:
                    data[key] = val

        if description_text.strip():
            data['description'] = description_text.strip()
        if observation_text.strip():
            data['observation'] = observation_text.strip()

        # Extraire wikilinks
        all_links = set()
        if data.get('description'):
            all_links.update(WikilinkExtractor.extract_all_wikilinks(
                data['description'], warnings, file_path
            ))
        if data.get('observation'):
            all_links.update(WikilinkExtractor.extract_all_wikilinks(
                data['observation'], warnings, file_path
            ))

        generic_refs = all_links - specific_entities

        # Parse dates
        date_edtf = data.get('date_edtf')
        if date_edtf:
            date_start, date_end, date_precision = EDTFParser.parse(date_edtf)
        else:
            date_start, date_end, date_precision = None, None, 'unknown'

        # Normalisation confidence
        conf_raw = str(data.get('confidence', '')).strip().lower()
        uncertainty_flag = (conf_raw == 'low') or conf_raw.endswith('/low')
        gap_flag = date_edtf and ('..' in date_edtf)
        unknown_agent = data.get('agent_id') in [None, 'UNKNOWN_AUTHORITY']

        properties = {
            'event_id': event_id,
            'tags': data.get('tags', ''),
            'event_type': data.get('event_type'),
            'date_edtf': date_edtf,
            'date_start': date_start,
            'date_end': date_end,
            'date_precision': date_precision,
            'date_source': data.get('date_source'),
            'victim_id': data.get('victim_id'),
            'agent_id': data.get('agent_id') or 'UNKNOWN_AUTHORITY',
            'agent_precision': data.get('agent_precision'),
            'agent_role': data.get('agent_role'),
            'place_id': data.get('place_id'),
            'place_precision': data.get('place_precision'),
            'description': data.get('description'),
            'observation': data.get('observation'),
            'uncertainty_flag': uncertainty_flag,
            'gap_flag': gap_flag,
            'unknown_agent': unknown_agent
        }

        assertion = {
            'assertion_id': f"{event_id}::assertion",
            'doc_id': doc_id,
            'properties': {
                'type': 'EVENT_ASSERTION',
                'confidence': data.get('confidence', 'medium'),
                'evidence_type': data.get('evidence_type', 'reported'),
                'source_quote': data.get('source_quote', ''),
                'page': data.get('page')
            }
        }

        return {
            'event_id': event_id,
            'properties': properties,
            'assertion': assertion,
            'references': generic_refs
        }

    def _extract_entity_id(self, wikilink: str, warnings: WikilinkWarnings,
                           file_path: str, line_num: int) -> Optional[str]:
        """Extrait ID depuis wikilink"""
        if wikilink == 'UNKNOWN_AUTHORITY':
            return 'UNKNOWN_AUTHORITY'

        try:
            return WikilinkExtractor.clean_id(wikilink, warnings, file_path, line_num)
        except ValueError:
            if 'UNKNOWN' in wikilink.upper():
                return 'UNKNOWN_AUTHORITY'
            return None

    def _canonicalize_event_id(self, raw_id: str) -> str:
        """Canonicalise event_id"""
        if raw_id.startswith('/id/event/'):
            return raw_id
        return f"/id/event/{hashlib.sha1(raw_id.encode('utf-8')).hexdigest()}"

    def _build_document_id_from_path(self, file_path: Path) -> str:
        """Génère doc_id depuis nom fichier (cohérent avec document_parser)"""
        file_name = file_path.name
        h = hashlib.sha1(file_name.encode('utf-8')).hexdigest()
        return f"/id/document/{h}"