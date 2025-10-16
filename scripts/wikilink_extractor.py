# utils/wikilink_extractor.py
"""
Extraction et nettoyage des wikilinks Obsidian
"""

import re
from typing import Set, Tuple, Optional


class WikilinkWarnings:
    """Collecteur de warnings d'extraction"""

    def __init__(self):
        self.invalid_wikilinks = []  # [(file, line, raw_link, error)]
        self.auto_corrected_slashes = []  # [(file, line, raw_link)]
        self.frontmatter_unquoted = []  # [(file, field, raw_link)]
        self.document_id_collisions = []  # [(file_name, original_path, current_path)]
        self.parse_errors = []  # [(file, error)]

        # Listes spécifiques micro-actions/entités
        self.reply_missing_anchor_date_list = []
        self.in_reply_to_date_extracted_list = []
        self.microaction_missing_about_list = []
        self.is_part_of_in_body_list = []

    def log_invalid(self, file, line, raw_link, error):
        self.invalid_wikilinks.append((file, line, raw_link, error))

    def log_slash_correction(self, file, line, raw_link):
        self.auto_corrected_slashes.append((file, line, raw_link))

    def log_unquoted_frontmatter(self, file, field, raw_link):
        self.frontmatter_unquoted.append((file, field, raw_link))

    def log_document_id_collision(self, file_name, original_path, current_path):
        self.document_id_collisions.append((file_name, original_path, current_path))

    def log_parse_error(self, file, error):
        self.parse_errors.append((file, error))

    def log_reply_missing_anchor_date(self, file, micro_id):
        self.reply_missing_anchor_date_list.append((file, micro_id))

    def log_in_reply_to_date_extracted(self, file, micro_id, date):
        self.in_reply_to_date_extracted_list.append((file, micro_id, date))

    def log_missing_about(self, file, micro_id):
        self.microaction_missing_about_list.append((file, micro_id))

    def log_is_part_of_in_body(self, file, entity_id):
        self.is_part_of_in_body_list.append((file, entity_id))

    def get_counts(self):
        return {
            'invalid_wikilinks_ignored': len(self.invalid_wikilinks),
            'wikilinks_slash_auto_corrected': len(self.auto_corrected_slashes),
            'frontmatter_unquoted_link': len(self.frontmatter_unquoted),
            'document_id_collisions': len(self.document_id_collisions)
        }


class WikilinkExtractor:
    """Extrait et nettoie les wikilinks depuis markdown Obsidian"""

    WIKILINK_PATTERN = re.compile(
        r'\[\[/?'
        r'(id/(?:person|org|gpe|place)/[0-9a-fA-F-]{36})'
        r'(?:\|[^\]]+)?'
        r'\]\]'
    )

    ID_PATTERN = re.compile(r'^/id/(person|org|gpe|place)/[0-9a-fA-F-]{36}$')

    FRONTMATTER_BLACKLIST = {
        'quote', 'source_quote', 'note', 'doc', 'page'
    }

    @staticmethod
    def clean_id(raw_link: str, warnings: Optional[WikilinkWarnings] = None,
                 file_path: Optional[str] = None, line_num: Optional[int] = None) -> str:
        """Nettoie et normalise un ID d'entité"""
        cleaned = raw_link.strip('[]')

        if '|' in cleaned:
            cleaned = cleaned.split('|')[0]

        # Correction slash
        if not cleaned.startswith('/'):
            if warnings and file_path:
                warnings.log_slash_correction(file_path, line_num or 0, raw_link)
            cleaned = '/' + cleaned

        # Validation
        if not WikilinkExtractor.ID_PATTERN.match(cleaned):
            error = f"Invalid ID format: {cleaned}"
            if warnings and file_path:
                warnings.log_invalid(file_path, line_num or 0, raw_link, error)
            raise ValueError(error)

        return cleaned

    @staticmethod
    def extract_all_wikilinks(text: str, warnings: Optional[WikilinkWarnings] = None,
                              file_path: Optional[str] = None) -> Set[str]:
        """Extrait tous les IDs depuis un texte"""
        ids = set()

        for match in WikilinkExtractor.WIKILINK_PATTERN.finditer(text):
            raw_id = match.group(1)
            line_num = text[:match.start()].count('\n') + 1 if text else 0

            try:
                clean_id = WikilinkExtractor.clean_id(
                    raw_id, warnings, file_path, line_num
                )
                ids.add(clean_id)
            except ValueError:
                continue

        return ids

    @staticmethod
    def extract_from_dict(data: dict, blacklist_fields: Optional[Set[str]] = None,
                          warnings: Optional[WikilinkWarnings] = None,
                          file_path: Optional[str] = None) -> Set[str]:
        """Extrait récursivement wikilinks depuis structure YAML"""
        if blacklist_fields is None:
            blacklist_fields = set()

        ids = set()

        def scan_value(val, parent_key=None):
            if parent_key and parent_key in blacklist_fields:
                return

            if parent_key and ('.' in str(parent_key) and
                               any(bl in str(parent_key) for bl in blacklist_fields)):
                return

            if isinstance(val, str):
                ids.update(WikilinkExtractor.extract_all_wikilinks(
                    val, warnings, file_path
                ))
            elif isinstance(val, dict):
                for k, v in val.items():
                    new_key = f"{parent_key}.{k}" if parent_key else k
                    scan_value(v, new_key)
            elif isinstance(val, list):
                for item in val:
                    scan_value(item, parent_key)

        scan_value(data)
        return ids

    @staticmethod
    def validate_frontmatter_syntax(raw_yaml_text: str,
                                    warnings: Optional[WikilinkWarnings] = None,
                                    file_path: Optional[str] = None) -> bool:
        """Vérifie que les wikilinks dans frontmatter sont entre guillemets"""
        unquoted_pattern = r'(?<!")(\[\[/id/[^\]]+\]\])(?!")'

        for match in re.finditer(unquoted_pattern, raw_yaml_text):
            raw_link = match.group(1)
            line_num = raw_yaml_text[:match.start()].count('\n') + 1

            line_start = raw_yaml_text.rfind('\n', 0, match.start()) + 1
            line_text = raw_yaml_text[line_start:match.start()]
            field = line_text.split(':')[0].strip() if ':' in line_text else 'unknown'

            if warnings and file_path:
                warnings.log_unquoted_frontmatter(file_path, field, raw_link)

        return True

    @staticmethod
    def categorize_links(all_links: Set[str],
                         specific_links: Set[str],
                         entity_id: str) -> Tuple[Set[str], Set[str]]:
        """Catégorise les liens en spécifiques vs génériques"""
        generic_refs = all_links - specific_links - {entity_id}
        return specific_links, generic_refs