# utils/entity_parser_markdown.py
"""
Parser pour structures réifiées depuis corps markdown
Complète entity_parser.py existant
✨ FIX v2.4.1 : Extraction robuste wikilinks + debug logging
"""

import re
from typing import Dict, List, Optional, Tuple
from .wikilink_extractor import WikilinkExtractor, WikilinkWarnings


class MarkdownStructureParser:
    """Parse structures réifiées depuis sections markdown niveau 2 et 3"""

    # Mapping sections → types de structures
    SECTION_MAPPING = {
        'Person': {
            '## Appellations': ('names', 'NAME'),
            '## Origines': ('origins', 'ORIG'),
            '## Lieux de résidence': ('residences', 'RES'),
            '## Occupations': ('occupations', 'OCC'),
            '## Relations familiales': ('family_relations', 'FAMREL'),
            '## Relations professionnelles': ('professional_relations', 'PROFREL'),
        },
        'Organization': {
            '## Appellations institutionnelles': ('names', 'ORGNAME'),
        },
        'GPE': {
            '## Appellations géographiques': ('gpe_names', 'GPENAME'),
        }
    }

    def __init__(self, label: str, body: str, warnings: WikilinkWarnings, file_path: str):
        self.label = label
        self.body = body
        self.warnings = warnings
        self.file_path = file_path
        self.sections_config = self.SECTION_MAPPING.get(label, {})

    def parse_all_structures(self) -> Dict[str, List[Dict]]:
        """Parse toutes les structures depuis le corps markdown"""
        structures = {}

        for section_title, (struct_key, rid_type) in self.sections_config.items():
            items = self._parse_section(section_title)
            if items:
                structures[struct_key] = items

        return structures

    def _parse_section(self, section_title: str) -> List[Dict]:
        """Parse une section niveau 2 (ex: ## Appellations)"""
        # Trouver la section
        pattern = rf'^{re.escape(section_title)}\s*$'
        match = re.search(pattern, self.body, re.MULTILINE)

        if not match:
            return []

        start_pos = match.end()

        # Trouver fin de section (prochaine section ## ou fin de fichier)
        next_section = re.search(r'\n##(?!#)', self.body[start_pos:])
        end_pos = start_pos + next_section.start() if next_section else len(self.body)

        section_content = self.body[start_pos:end_pos]

        # Extraire tous les items niveau 3
        return self._parse_items_level3(section_content)

    def _parse_items_level3(self, section_content: str) -> List[Dict]:
        """Parse tous les items ### dans une section"""
        items = []

        # Split par ### (items niveau 3)
        item_pattern = r'\n###\s+(.+?)(?=\n###|\Z)'

        for match in re.finditer(item_pattern, section_content, re.DOTALL):
            item_title = match.group(1).split('\n')[0].strip()
            item_content = match.group(1)

            item_data = self._parse_item_properties(item_content)

            if item_data and 'rid' in item_data.get('properties', {}):
                items.append(item_data)

        return items

    def _parse_item_properties(self, item_content: str) -> Optional[Dict]:
        """Parse les propriétés d'un item (liste markdown)"""
        properties = {}
        provenance = {}

        lines = item_content.split('\n')
        in_provenance = False

        for line in lines:
            line = line.strip()

            # Skip lignes vides et titre
            if not line or line.startswith('###'):
                continue

            # Détecter début bloc Provenance
            if line == '- **Provenance** :':
                in_provenance = True
                continue

            # Propriétés Provenance (indentées)
            if in_provenance:
                if line.startswith('- '):
                    # Fin du bloc provenance
                    in_provenance = False
                elif line.startswith('  - '):
                    # Sous-propriété provenance
                    prov_match = re.match(r'^\s*-\s*(.+?)\s*:\s*(.+)$', line)
                    if prov_match:
                        key = prov_match.group(1).lower().replace(' ', '_')
                        value = prov_match.group(2).strip()

                        # Nettoyer wikilinks dans valeurs
                        if key == 'doc':
                            value = self._extract_doc_link(value)
                        elif key == 'quote':
                            value = value.strip('"')
                        elif key in ['evidence', 'confidence']:
                            # Garder format tag
                            pass

                        provenance[key] = value
                continue

            # Propriétés principales
            prop_match = re.match(r'^-\s*\*\*(.+?)\*\*\s*:\s*(.+)$', line)
            if prop_match:
                key = prop_match.group(1).strip()
                value = prop_match.group(2).strip()

                # Mapping clés markdown → clés structure
                key_normalized = self._normalize_property_key(key)

                if key_normalized:
                    # Parser selon type
                    parsed_value = self._parse_property_value(key_normalized, value)
                    properties[key_normalized] = parsed_value

        # Ajouter provenance aux propriétés
        if provenance:
            properties['provenance'] = provenance

        if not properties:
            return None

        # Extraire RID pour identifiant
        rid = properties.get('rid')

        return {
            'rid': rid,
            'properties': properties
        }

    def _normalize_property_key(self, key: str) -> Optional[str]:
        """Normalise les clés markdown vers clés attendues par le code"""
        key_mapping = {
            'RID': 'rid',
            'Type': 'type',
            'Type de relation': 'relation_type',
            "Type d'activité": 'type_activity',
            'Display': 'display',
            'Parts': 'parts',
            'Lang': 'lang',
            'Intervalle': 'interval',
            'Spouse': 'spouse',
            'Mode': 'mode',
            'Lieu': 'place',
            'Organisation': 'organization',
            'Titre du poste': 'position_title',
            'Cible': 'target',
            'Organisation contexte': 'organization_context',
            'Note': 'note',
        }

        return key_mapping.get(key)

    def _parse_property_value(self, key: str, value: str):
        """Parse une valeur selon le type de propriété"""
        value = value.strip()

        # Tags (garder tel quel)
        if value.startswith('#'):
            return value

        # Wikilinks → extraire ID
        if key in ['place', 'organization', 'target', 'organization_context']:
            return self._extract_wikilink_id(value)

        # Parts (sous-dict)
        if key == 'parts':
            return self._parse_parts(value)

        # Valeurs vides
        if not value or value == 'null' or value == '':
            return None

        # Valeur par défaut
        return value

    def _parse_parts(self, parts_text: str) -> Dict[str, Optional[str]]:
        """Parse le bloc Parts (indentation markdown)"""
        parts = {}

        # Pattern: - family : Nom
        for match in re.finditer(r'-\s*(\w+)\s*:\s*(.+)', parts_text):
            part_key = match.group(1).strip()
            part_value = match.group(2).strip()

            parts[part_key] = part_value if part_value else None

        return parts

    def _extract_wikilink_id(self, text: str) -> Optional[str]:
        """
        ✨ FIX v2.4.2 : Support UUIDs v4 ET slugs textuels

        Extrait ID depuis wikilink [[/id/type/uuid]] ou [[/id/type/slug]]

        Supporte :
        - UUIDs v4 : /id/person/d69babce-b1c2-4f46-ae27-5655ad9d6027
        - Slugs textuels : /id/gpe/geneve, /id/gpe/cossonay-vd
        """
        # ✨ DEBUG : Log le texte brut
        print(f"       🔍 Extracting from: '{text}'")

        # ✨ Pattern strict : UUIDs v4 (36 caractères hex)
        match = re.search(r'\[\[(/id/\w+/[a-fA-F0-9-]{36})(?:\|[^\]]+)?\]\]', text)
        if match:
            extracted_id = match.group(1)
            print(f"       ✅ Extracted (UUID v4): {extracted_id}")
            return extracted_id

        # ✨ Pattern fallback : Slugs textuels (lettres + tirets + chiffres)
        # Accepte : geneve, cossonay-vd, bale-ville, etc.
        match_slug = re.search(r'\[\[(/id/\w+/[a-zA-Z0-9_-]+)(?:\|[^\]]+)?\]\]', text)
        if match_slug:
            extracted_id = match_slug.group(1)
            print(f"       ✅ Extracted (slug): {extracted_id}")
            return extracted_id

        print(f"       ❌ No match found!")
        return None

    def _extract_doc_link(self, text: str) -> Optional[str]:
        """Extrait nom document depuis [[nom-doc]]"""
        match = re.search(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]', text)
        if match:
            return match.group(1)
        return None


def parse_structures_from_markdown(label: str, body: str,
                                   warnings: WikilinkWarnings,
                                   file_path: str) -> Dict[str, List[Dict]]:
    """
    Fonction utilitaire pour parser structures depuis markdown

    Args:
        label: Type d'entité (Person, Organization, GPE)
        body: Corps du fichier markdown (après frontmatter)
        warnings: Collecteur de warnings
        file_path: Chemin fichier pour logs

    Returns:
        Dict de structures parsées, format compatible avec entity_parser.py
    """
    parser = MarkdownStructureParser(label, body, warnings, file_path)
    return parser.parse_all_structures()