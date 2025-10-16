# utils/validator.py
"""
Validateur pour données avant import Neo4j
"""

from typing import List, Dict, Any
from pathlib import Path
import datetime


class Validator:
    """Valide les données extraites avant import Neo4j"""

    def __init__(self, config: dict):
        self.config = config
        self.strict_mode = config['import_options']['strict_mode']
        self.provenance_required = config['import_options']['provenance_required']

        # Agrégation warnings
        from .wikilink_extractor import WikilinkWarnings
        self.aggregated_warnings = WikilinkWarnings()

        # Compteurs
        self.invalid_uuid_count = 0
        self.events_missing_quote = 0
        self.events_missing_tags = 0
        self.event_type_conflict = 0
        self.reply_missing_anchor_date = 0
        self.in_reply_to_date_extracted = 0
        self.microaction_missing_about = 0
        self.structure_missing_provenance = 0
        self.is_part_of_in_body = 0
        self.missing_prefLabel_both = 0
        self.missing_prefLabel_fr = 0
        self.missing_prefLabel_de = 0
        self.missing_date_precision = 0

        # Parse errors
        self.parse_errors = []

    def merge_warnings(self, warnings):
        """Agrège warnings d'un parser"""
        self.aggregated_warnings.invalid_wikilinks.extend(warnings.invalid_wikilinks)
        self.aggregated_warnings.auto_corrected_slashes.extend(warnings.auto_corrected_slashes)
        self.aggregated_warnings.frontmatter_unquoted.extend(warnings.frontmatter_unquoted)
        self.aggregated_warnings.document_id_collisions.extend(warnings.document_id_collisions)

        # Compteurs spécifiques
        if hasattr(warnings, 'reply_missing_anchor_date_list'):
            self.reply_missing_anchor_date += len(warnings.reply_missing_anchor_date_list)
        if hasattr(warnings, 'in_reply_to_date_extracted_list'):
            self.in_reply_to_date_extracted += len(warnings.in_reply_to_date_extracted_list)
        if hasattr(warnings, 'microaction_missing_about_list'):
            self.microaction_missing_about += len(warnings.microaction_missing_about_list)
        if hasattr(warnings, 'is_part_of_in_body_list'):
            self.is_part_of_in_body += len(warnings.is_part_of_in_body_list)
        if hasattr(warnings, 'parse_errors'):
            self.parse_errors.extend(warnings.parse_errors)

    def get_warning_counts(self) -> Dict[str, int]:
        """Retourne compteurs globaux"""
        return {
            'invalid_wikilinks_ignored': len(self.aggregated_warnings.invalid_wikilinks),
            'wikilinks_slash_auto_corrected': len(self.aggregated_warnings.auto_corrected_slashes),
            'frontmatter_unquoted_link': len(self.aggregated_warnings.frontmatter_unquoted),
            'invalid_uuid_v4': self.invalid_uuid_count,
            'events_missing_quote': self.events_missing_quote,
            'events_missing_tags': self.events_missing_tags,
            'event_type_conflict': self.event_type_conflict,
            'reply_missing_anchor_date': self.reply_missing_anchor_date,
            'in_reply_to_date_extracted': self.in_reply_to_date_extracted,
            'microaction_missing_about': self.microaction_missing_about,
            'structure_missing_provenance': self.structure_missing_provenance,
            'is_part_of_in_body': self.is_part_of_in_body,
            'missing_prefLabel_both': self.missing_prefLabel_both,
            'missing_prefLabel_fr': self.missing_prefLabel_fr,
            'missing_prefLabel_de': self.missing_prefLabel_de,
            'document_id_collisions': len(self.aggregated_warnings.document_id_collisions),
            'parse_errors': len(self.parse_errors),
            'missing_date_precision': self.missing_date_precision
        }

    def write_report(self, path: Path):
        """Génère rapport Markdown détaillé"""
        counts = self.get_warning_counts()

        with path.open('w', encoding='utf-8') as f:
            f.write(f"# Import Warnings Report\n")
            f.write(f"**Date**: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"**Vault**: {self.config.get('vault_path', 'N/A')}\n\n")
            f.write("---\n\n")

            # Résumé
            f.write("## 📊 Résumé\n\n")
            f.write("| Category | Count |\n")
            f.write("|----------|-------|\n")
            for key, value in counts.items():
                label = key.replace('_', ' ').title()
                f.write(f"| {label} | {value} |\n")
            f.write(f"\n**Total warnings**: {sum(counts.values())}\n\n")
            f.write("---\n\n")

            # Invalid wikilinks
            if self.aggregated_warnings.invalid_wikilinks:
                f.write("## ⚠️ Invalid Wikilinks\n\n")
                f.write("| File | Line | Raw Link | Error |\n")
                f.write("|------|------|----------|-------|\n")
                for file, line, raw, error in self.aggregated_warnings.invalid_wikilinks:
                    f.write(f"| `{file}` | {line} | `{raw}` | {error} |\n")
                f.write("\n---\n\n")

            # Slash auto-corrected
            if self.aggregated_warnings.auto_corrected_slashes:
                f.write("## 🔧 Slash Auto-Corrected\n\n")
                f.write("| File | Line | Original Link |\n")
                f.write("|------|------|---------------|\n")
                for file, line, raw in self.aggregated_warnings.auto_corrected_slashes:
                    f.write(f"| `{file}` | {line} | `{raw}` |\n")
                f.write("\n---\n\n")

            # Frontmatter unquoted
            if self.aggregated_warnings.frontmatter_unquoted:
                f.write("## 📝 Frontmatter Unquoted Links\n\n")
                f.write("| File | Field | Link |\n")
                f.write("|------|-------|------|\n")
                for file, field, link in self.aggregated_warnings.frontmatter_unquoted:
                    f.write(f"| `{file}` | `{field}` | `{link}` |\n")
                f.write("\n---\n\n")

            # Document collisions
            if self.aggregated_warnings.document_id_collisions:
                f.write("## 🔀 Document ID Collisions\n\n")
                f.write("| Filename | Original Path | Current Path |\n")
                f.write("|----------|---------------|-------------|\n")
                for fname, orig, curr in self.aggregated_warnings.document_id_collisions:
                    f.write(f"| `{fname}` | `{orig}` | `{curr}` |\n")
                f.write("\n---\n\n")

            # Parse errors
            if self.parse_errors:
                f.write("## ❌ Parse Errors\n\n")
                f.write("| File | Error |\n")
                f.write("|------|-------|\n")
                for file, error in self.parse_errors:
                    f.write(f"| `{file}` | {error} |\n")
                f.write("\n---\n\n")

            # Recommendations
            f.write("## ✅ Recommendations\n\n")
            if self.aggregated_warnings.invalid_wikilinks:
                f.write("- **Invalid wikilinks**: Review files listed above, correct UUID formats\n")
            if self.aggregated_warnings.frontmatter_unquoted:
                f.write("- **Frontmatter syntax**: Add quotes around wikilinks in frontmatter\n")
            if self.events_missing_quote > 0:
                f.write("- **Missing quotes**: Add `source_quote` to Events lacking provenance\n")
            if self.structure_missing_provenance > 0:
                f.write("- **Missing provenance**: Complete `provenance` blocks in entity structures\n")
            f.write("\n---\n\n")
            f.write("*Report generated by master_import.py v1.3*\n")

    def report_warning(self, code: str, payload: str):
        """Interface publique warnings"""
        if code == 'invalid_uuid_v4':
            self.invalid_uuid_count += 1
        elif code == 'events_missing_quote':
            self.events_missing_quote += 1
        elif code == 'events_missing_tags':
            self.events_missing_tags += 1
        elif code == 'event_type_conflict':
            self.event_type_conflict += 1
        elif code == 'structure_missing_provenance':
            self.structure_missing_provenance += 1
        elif code == 'missing_prefLabel_both':
            self.missing_prefLabel_both += 1
        elif code == 'missing_prefLabel_fr':
            self.missing_prefLabel_fr += 1
        elif code == 'missing_prefLabel_de':
            self.missing_prefLabel_de += 1
        elif code == 'missing_date_precision':
            self.missing_date_precision += 1

    def log_parse_error(self, file: str, error: str):
        """Enregistre erreur parsing"""
        self.parse_errors.append((file, error))

    def validate_entities(self, entities: List[Dict]) -> List[Dict]:
        """Valide liste d'entités"""
        for entity in entities:
            self._validate_uuid_v4(entity['id'])
            self._validate_labels(entity)
            self._validate_structures(entity)
        return entities

    def validate_documents(self, documents: List[Dict]) -> List[Dict]:
        """Valide liste de documents"""
        return documents

    def validate_events(self, events: List[Dict]) -> List[Dict]:
        """Valide liste d'événements"""
        for event in events:
            self._validate_event_taxonomy(event)
            self._validate_event_quote(event)
        return events

    def validate_microactions(self, microactions: List[Dict]) -> List[Dict]:
        """Valide liste de micro-actions"""
        return microactions

    def _validate_uuid_v4(self, entity_id: str):
        """Vérifie UUID v4"""
        import uuid
        try:
            uuid_str = entity_id.split('/')[-1]
            parsed = uuid.UUID(uuid_str)
            if parsed.version != 4:
                self.report_warning('invalid_uuid_v4', entity_id)
                if self.strict_mode:
                    raise ValueError(f"Invalid UUID version: {entity_id}")
        except (ValueError, AttributeError):
            self.report_warning('invalid_uuid_v4', entity_id)
            if self.strict_mode:
                raise

    def _validate_labels(self, entity):
        """Valide labels linguistiques"""
        fr = entity['properties'].get('prefLabel_fr')
        de = entity['properties'].get('prefLabel_de')

        if not fr and not de:
            self.report_warning('missing_prefLabel_both', entity['id'])
        elif not fr:
            self.report_warning('missing_prefLabel_fr', entity['id'])
        elif not de:
            self.report_warning('missing_prefLabel_de', entity['id'])

    def _validate_structures(self, entity):
        """Valide structures réifiées"""
        for struct_name in ['names', 'occupations', 'origins', 'family_relations', 'professional_relations']:
            if struct_name in entity.get('structures', {}):
                for item in entity['structures'][struct_name]:
                    prov = item.get('properties', {})
                    if not prov.get('doc') or not prov.get('confidence'):
                        self.report_warning('structure_missing_provenance', f"{entity['id']}:{struct_name}")
                        if self.strict_mode:
                            raise ValueError(f"Missing provenance: {entity['id']}:{struct_name}")

    def _validate_event_taxonomy(self, event):
        """Valide taxonomie event"""
        tags = event['properties'].get('tags', '')
        event_type = event['properties'].get('event_type')

        if not tags:
            self.report_warning('events_missing_tags', event['event_id'])

        if not event_type and tags:
            event['properties']['event_type'] = tags.split('/')[-1]
        elif tags and event_type and not tags.endswith(event_type):
            self.report_warning('event_type_conflict', event['event_id'])

    def _validate_event_quote(self, event):
        """Valide source_quote"""
        assertion = event.get('assertion', {})
        quote = assertion.get('properties', {}).get('source_quote', '')
        if not quote or quote.strip() == '':
            self.report_warning('events_missing_quote', event['event_id'])