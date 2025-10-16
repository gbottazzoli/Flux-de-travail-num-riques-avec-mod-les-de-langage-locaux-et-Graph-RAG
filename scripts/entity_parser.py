# utils/entity_parser.py
"""
Parser pour entités Obsidian (Person, Org, GPE)
Version: 2.4.0 - Structures réifiées depuis markdown + frontmatter
"""

import yaml
import re
from pathlib import Path
from typing import Dict, List, Any, Set, Tuple, Optional
from .entity_parser_markdown import parse_structures_from_markdown
from .wikilink_extractor import WikilinkExtractor, WikilinkWarnings
from .edtf_parser import EDTFParser


class EntityParser:
    """Parse les notes d'entités depuis Obsidian"""

    ENTITY_FOLDERS = ["id/gpe", "id/person", "id/org", "id/place"]

    def __init__(self, vault_path: Path, config: dict, folders: Optional[List[Path]] = None):
        self.vault_path = vault_path
        self.config = config
        self.folders = folders

    def _should_process_file(self, file_path: Path) -> bool:
        """Les entités sont toujours importées si folders spécifié pour sources"""
        return True  # ← Désactive le filtrage pour entités

    def parse_all(self) -> Tuple[List[Dict[str, Any]], WikilinkWarnings]:
        """Parse toutes les entités du vault"""
        entities = []
        warnings = WikilinkWarnings()

        for folder in self.ENTITY_FOLDERS:
            folder_path = self.vault_path / folder
            if not folder_path.exists():
                continue

            for file_path in folder_path.rglob("*.md"):
                if not self._should_process_file(file_path):
                    continue

                try:
                    entity = self._parse_entity_file(file_path, warnings)
                    if entity:
                        entities.append(entity)
                except Exception as e:
                    warnings.log_parse_error(str(file_path), f"{type(e).__name__}: {str(e)}")

        return entities, warnings

    def _parse_entity_file(self, file_path: Path, warnings: WikilinkWarnings) -> Optional[Dict[str, Any]]:
        """Parse un fichier entité"""
        text = file_path.read_text(encoding='utf-8')

        frontmatter_text, body = self._split_frontmatter_raw(text)
        frontmatter = yaml.safe_load(frontmatter_text) if frontmatter_text else {}

        if not frontmatter or 'id' not in frontmatter:
            return None

        label = self._get_label(file_path)
        if label == "Entity":
            return None

        entity_id = WikilinkExtractor.clean_id(frontmatter['id'], warnings, str(file_path))

        # Validation frontmatter syntax
        if frontmatter_text:
            WikilinkExtractor.validate_frontmatter_syntax(frontmatter_text, warnings, str(file_path))

        # Détecter is_part_of dans corps
        if 'is_part_of' in body.lower():
            warnings.log_is_part_of_in_body(str(file_path), entity_id)

        # Extraire wikilinks
        all_links_text = WikilinkExtractor.extract_all_wikilinks(body, warnings, str(file_path))
        all_links_fm = WikilinkExtractor.extract_from_dict(
            frontmatter,
            WikilinkExtractor.FRONTMATTER_BLACKLIST,
            warnings,
            str(file_path)
        )
        all_links = all_links_text | all_links_fm

        specific_links = set()
        specific_relations = {}

        # LOCATED_IN
        if 'gpe' in frontmatter and frontmatter['gpe']:
            try:
                gpe_id = WikilinkExtractor.clean_id(frontmatter['gpe'], warnings, str(file_path))
                specific_links.add(gpe_id)
                specific_relations['LOCATED_IN'] = [gpe_id]
            except (ValueError, TypeError):
                pass

        # IS_PART_OF
        if 'is_part_of' in frontmatter and frontmatter['is_part_of']:
            parts = frontmatter['is_part_of']
            if isinstance(parts, str):
                parts = [parts]
            elif not isinstance(parts, list):
                parts = []

            parent_ids = []
            for part in parts:
                try:
                    parent_id = WikilinkExtractor.clean_id(part, warnings, str(file_path))
                    specific_links.add(parent_id)
                    parent_ids.append(parent_id)
                except (ValueError, TypeError):
                    pass

            if parent_ids:
                specific_relations['IS_PART_OF'] = parent_ids

        # ============================================================================
        # STRUCTURES RÉIFIÉES - Phase 1 : Frontmatter (legacy)
        # ============================================================================
        structures = {}

        if label == "Person":
            if 'occupations' in frontmatter and isinstance(frontmatter.get('occupations'), list):
                occs, worked_for_ids = self._parse_occupations(frontmatter['occupations'], warnings, str(file_path))
                structures['occupations'] = occs
                specific_links.update(worked_for_ids)
                if worked_for_ids:
                    specific_relations['WORKED_FOR'] = list(worked_for_ids)

            if 'names' in frontmatter and isinstance(frontmatter.get('names'), list):
                structures['names'] = self._parse_names(frontmatter['names'], entity_id)

            if 'origins' in frontmatter and isinstance(frontmatter.get('origins'), list):
                structures['origins'] = self._parse_origins(frontmatter['origins'], warnings, str(file_path))

            if 'relations_family' in frontmatter and isinstance(frontmatter.get('relations_family'), list):
                rels, family_ids = self._parse_family_relations(frontmatter['relations_family'], warnings,
                                                                str(file_path))
                structures['family_relations'] = rels
                specific_links.update(family_ids)

            if 'professional_relations' in frontmatter and isinstance(frontmatter.get('professional_relations'), list):
                rels, prof_ids = self._parse_professional_relations(frontmatter['professional_relations'], warnings,
                                                                    str(file_path))
                structures['professional_relations'] = rels
                specific_links.update(prof_ids)

        # ============================================================================
        # STRUCTURES RÉIFIÉES - Phase 2 : Corps Markdown (NEW!)
        # ============================================================================

        # ✨ NOUVEAU : Parser structures depuis sections markdown niveau 2/3
        markdown_structures = parse_structures_from_markdown(
            label, body, warnings, str(file_path)
        )

        # Fusionner structures frontmatter + markdown
        for struct_key, items in markdown_structures.items():
            if struct_key not in structures:
                structures[struct_key] = []
            structures[struct_key].extend(items)

            # Extraire IDs pour relations spécifiques
            if struct_key == 'occupations':
                for item in items:
                    org_id = item['properties'].get('organization')
                    if org_id:
                        specific_links.add(org_id)
                        if 'WORKED_FOR' not in specific_relations:
                            specific_relations['WORKED_FOR'] = []
                        if org_id not in specific_relations['WORKED_FOR']:
                            specific_relations['WORKED_FOR'].append(org_id)

            elif struct_key == 'family_relations':
                for item in items:
                    target_id = item.get('target_id')
                    if target_id:
                        specific_links.add(target_id)

            elif struct_key == 'professional_relations':
                for item in items:
                    target_id = item.get('target_id')
                    if target_id:
                        specific_links.add(target_id)

            elif struct_key == 'origins':
                for item in items:
                    place_id = item['properties'].get('place')
                    if place_id:
                        specific_links.add(place_id)

        # ============================================================================
        # RELATIONS GÉNÉRIQUES
        # ============================================================================
        _, generic_refs = WikilinkExtractor.categorize_links(all_links, specific_links, entity_id)

        # ============================================================================
        # PROPRIÉTÉS DE BASE
        # ============================================================================
        properties = {
            'prefLabel_fr': frontmatter.get('prefLabel_fr', ''),
            'prefLabel_de': frontmatter.get('prefLabel_de', ''),
            'aliases': frontmatter.get('aliases', []),
            'sameAs': frontmatter.get('sameAs', []),
            'status': frontmatter.get('status', 'active')
        }

        # ✨ Extraire notices du corps markdown
        if label == "Person":
            notice_bio = self._extract_notice_section(body, "Notice biographique")
            if notice_bio:
                properties['notice_bio'] = notice_bio

        elif label == "Organization":
            notice_inst = self._extract_notice_section(body, "Notice institutionnelle")
            if notice_inst:
                properties['notice_institutionnelle'] = notice_inst

            properties['type'] = frontmatter.get('type', '')

        elif label == "GPE":
            notice_geo = self._extract_notice_section(body, "Notice géographique")
            if notice_geo:
                properties['notice_geo'] = notice_geo

        # Type pour Organisation
        if label == "Organization":
            properties['type'] = frontmatter.get('type', '')

        # ✨ FIX v2.3.2 : Support format liste Obsidian-friendly pour coordonnées GPE
        if label == "GPE":
            if 'coordinates' in frontmatter and frontmatter['coordinates']:
                coords = frontmatter['coordinates']

                if isinstance(coords, list):
                    # Parser format: ['system WGS84', 'lat 53.8655', 'lon 10.6866']
                    for item in coords:
                        if isinstance(item, str):
                            item_lower = item.lower().strip()
                            if item_lower.startswith('lat '):
                                try:
                                    lat_str = item.split(None, 1)[1]  # Split sur whitespace
                                    properties['coordinates_lat'] = float(lat_str)
                                except (ValueError, IndexError):
                                    pass
                            elif item_lower.startswith('lon '):
                                try:
                                    lon_str = item.split(None, 1)[1]
                                    properties['coordinates_lon'] = float(lon_str)
                                except (ValueError, IndexError):
                                    pass

                elif isinstance(coords, dict):
                    # Support ancien format dictionnaire (backward compatible)
                    properties['coordinates_lat'] = coords.get('lat')
                    properties['coordinates_lon'] = coords.get('lon')

            properties['geonames_id'] = frontmatter.get('geonames_id')

        return {
            'label': label,
            'id': entity_id,
            'properties': properties,
            'structures': structures,
            'specific_relations': specific_relations,
            'generic_references': generic_refs
        }

    def _split_frontmatter_raw(self, text: str) -> Tuple[str, str]:
        """Sépare frontmatter brut et corps"""
        if not text.startswith('---'):
            return '', text

        parts = text.split('---', 2)
        if len(parts) < 3:
            return '', text

        return parts[1], parts[2].lstrip('\n')

    def _get_label(self, path: Path) -> str:
        """Détermine le label Neo4j depuis le chemin"""
        parts = path.parts
        if 'id' in parts:
            idx = parts.index('id')
            if idx + 1 < len(parts):
                folder = parts[idx + 1]
                if folder == 'person':
                    return 'Person'
                elif folder == 'org':
                    return 'Organization'
                elif folder in ('gpe', 'place'):
                    return 'GPE'
        return 'Entity'

    def _extract_notice_section(self, body: str, section_title: str) -> Optional[str]:
        """
        ✨ NOUVEAU : Extrait le contenu d'une section markdown

        Args:
            body: Corps du fichier markdown (après frontmatter)
            section_title: Titre de la section à extraire (ex: "Notice biographique")

        Returns:
            Contenu de la section nettoyé, ou None si non trouvé
        """
        # Pattern pour trouver ## Section jusqu'à la prochaine section ##
        pattern = rf'##\s+{re.escape(section_title)}\s*\n(.*?)(?=\n##|\Z)'

        match = re.search(pattern, body, re.DOTALL)
        if match:
            content = match.group(1).strip()

            # Nettoyer :
            # - Enlever excès de sauts de ligne
            content = re.sub(r'\n{3,}', '\n\n', content)

            # - Enlever wikilinks mais garder le texte
            content = re.sub(r'\[\[/id/[^\]]+\]\]', '', content)
            content = re.sub(r'\[\[([^\]|]+)\|([^\]]+)\]\]', r'\2', content)
            content = re.sub(r'\[\[([^\]]+)\]\]', r'\1', content)

            # - Nettoyer espaces multiples
            content = re.sub(r'  +', ' ', content)

            return content if len(content) > 10 else None

        return None

    def _parse_occupations(self, occs_data: List[Dict], warnings: WikilinkWarnings, file_path: str) -> Tuple[
        List[Dict], Set[str]]:
        """Parse occupations avec extraction org_id"""
        occupations = []
        org_ids = set()

        for occ in occs_data:
            org_raw = occ.get('organization')
            org_id = None
            if org_raw:
                try:
                    org_id = WikilinkExtractor.clean_id(org_raw, warnings, file_path)
                    org_ids.add(org_id)
                except (ValueError, TypeError):
                    pass

            interval = occ.get('interval', '')
            date_start, date_end, precision = EDTFParser.parse(interval)

            provenance = occ.get('provenance', {}) or {}

            occupations.append({
                'rid': occ.get('rid'),
                'properties': {
                    'type_activity': occ.get('type_activity'),
                    'organization': org_id,
                    'position_title': occ.get('position_title'),
                    'interval': interval,
                    'date_start': date_start,
                    'date_end': date_end,
                    'date_precision': precision,
                    'doc': provenance.get('doc'),
                    'page': provenance.get('page'),
                    'quote': provenance.get('quote'),
                    'evidence_type': provenance.get('evidence_type'),
                    'confidence': provenance.get('confidence')
                }
            })

        return occupations, org_ids

    def _parse_names(self, names_data: List[Dict], entity_id: str) -> List[Dict]:
        """Parse names"""
        names = []

        for name in names_data:
            interval = name.get('interval', '')
            date_start, date_end, precision = EDTFParser.parse(interval)

            parts = name.get('parts', {}) or {}
            provenance = name.get('provenance', {}) or {}

            names.append({
                'rid': name.get('rid'),
                'properties': {
                    'display': name.get('display'),
                    'parts_family': parts.get('family'),
                    'parts_given': parts.get('given'),
                    'parts_particle': parts.get('particle'),
                    'lang': name.get('lang'),
                    'interval': interval,
                    'date_start': date_start,
                    'date_end': date_end,
                    'date_precision': precision,
                    'type': name.get('type'),
                    'doc': provenance.get('doc'),
                    'quote': provenance.get('quote'),
                    'evidence_type': provenance.get('evidence_type'),
                    'confidence': provenance.get('confidence')
                }
            })

        return names

    def _parse_origins(self, origins_data: List[Dict], warnings: WikilinkWarnings, file_path: str) -> List[Dict]:
        """Parse origins"""
        origins = []

        for origin in origins_data:
            place_raw = origin.get('place')
            place_id = None
            if place_raw:
                try:
                    place_id = WikilinkExtractor.clean_id(place_raw, warnings, file_path)
                except (ValueError, TypeError):
                    pass

            interval = origin.get('interval', '')
            date_start, date_end, precision = EDTFParser.parse(interval)

            provenance = origin.get('provenance', {}) or {}

            origins.append({
                'rid': origin.get('rid'),
                'properties': {
                    'mode': origin.get('mode'),
                    'place': place_id,
                    'interval': interval,
                    'date_start': date_start,
                    'date_end': date_end,
                    'date_precision': precision,
                    'is_primary': origin.get('is_primary', False),
                    'doc': provenance.get('doc'),
                    'quote': provenance.get('quote'),
                    'evidence_type': provenance.get('evidence_type'),
                    'confidence': provenance.get('confidence')
                }
            })

        return origins

    def _parse_family_relations(self, rels_data: List[Dict], warnings: WikilinkWarnings, file_path: str) -> Tuple[
        List[Dict], Set[str]]:
        """Parse family relations"""
        relations = []
        target_ids = set()

        for rel in rels_data:
            target_raw = rel.get('target')
            target_id = None
            if target_raw:
                try:
                    target_id = WikilinkExtractor.clean_id(target_raw, warnings, file_path)
                    target_ids.add(target_id)
                except (ValueError, TypeError):
                    pass

            interval = rel.get('interval', '')
            date_start, date_end, precision = EDTFParser.parse(interval)

            provenance = rel.get('provenance', {}) or {}

            relations.append({
                'rid': rel.get('rid'),
                'target_id': target_id,
                'properties': {
                    'relation_type': rel.get('relation_type'),
                    'interval': interval,
                    'date_start': date_start,
                    'date_end': date_end,
                    'date_precision': precision,
                    'doc': provenance.get('doc'),
                    'quote': provenance.get('quote'),
                    'evidence_type': provenance.get('evidence_type'),
                    'confidence': provenance.get('confidence')
                }
            })

        return relations, target_ids

    def _parse_professional_relations(self, rels_data: List[Dict], warnings: WikilinkWarnings, file_path: str) -> Tuple[
        List[Dict], Set[str]]:
        """Parse professional relations"""
        relations = []
        target_ids = set()

        for rel in rels_data:
            target_raw = rel.get('target')
            target_id = None
            if target_raw:
                try:
                    target_id = WikilinkExtractor.clean_id(target_raw, warnings, file_path)
                    target_ids.add(target_id)
                except (ValueError, TypeError):
                    pass

            org_raw = rel.get('organization_context')
            org_id = None
            if org_raw:
                try:
                    org_id = WikilinkExtractor.clean_id(org_raw, warnings, file_path)
                except (ValueError, TypeError):
                    pass

            interval = rel.get('interval', '')
            date_start, date_end, precision = EDTFParser.parse(interval)

            provenance = rel.get('provenance', {}) or {}

            relations.append({
                'rid': rel.get('rid'),
                'target_id': target_id,
                'properties': {
                    'relation_type': rel.get('relation_type'),
                    'organization_context': org_id,
                    'interval': interval,
                    'date_start': date_start,
                    'date_end': date_end,
                    'date_precision': precision,
                    'doc': provenance.get('doc'),
                    'quote': provenance.get('quote'),
                    'evidence_type': provenance.get('evidence_type'),
                    'confidence': provenance.get('confidence')
                }
            })

        return relations, target_ids