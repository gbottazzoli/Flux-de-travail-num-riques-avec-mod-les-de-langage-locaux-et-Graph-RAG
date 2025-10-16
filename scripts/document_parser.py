# utils/document_parser.py
"""
Parser pour documents d'archives
"""

import yaml
import hashlib
import re
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from .wikilink_extractor import WikilinkExtractor, WikilinkWarnings
from .edtf_parser import EDTFParser


class DocumentParser:
    """Parse les documents d'archives depuis Obsidian"""

    ARCHIVE_KEYS = {"archive_ref", "cote", "fonds", "reference", "versement", "shelfmark"}

    def __init__(self, vault_path: Path, config: dict, folders: Optional[List[Path]] = None):
        self.vault_path = vault_path
        self.config = config
        self.folders = folders
        self._doc_id_index = {}

    def _should_process_file(self, file_path: Path) -> bool:
        """Vérifie si le fichier doit être parsé selon les dossiers sélectionnés"""
        if not self.folders:
            return True

        return any(file_path.is_relative_to(folder) for folder in self.folders)

    def parse_all(self) -> Tuple[List[Dict[str, Any]], WikilinkWarnings]:
        """Parse tous les documents d'archives"""
        documents = []
        warnings = WikilinkWarnings()

        for file_path in self.vault_path.rglob("*.md"):
            if not self._should_process_file(file_path):
                continue

            try:
                doc = self._parse_document_file(file_path, warnings)
                if doc:
                    documents.append(doc)
            except Exception as e:
                warnings.log_parse_error(str(file_path), f"{type(e).__name__}: {str(e)}")

        return documents, warnings

    def _parse_document_file(self, file_path: Path, warnings: WikilinkWarnings) -> Optional[Dict[str, Any]]:
        """Parse un fichier document"""
        text = file_path.read_text(encoding='utf-8')

        frontmatter, body = self._split_frontmatter(text)

        if not self._is_archive_doc(frontmatter):
            return None

        rel_path = str(file_path.relative_to(self.vault_path))
        doc_id = self._build_document_id(file_path, warnings)

        # Extraire wikilinks
        all_links = WikilinkExtractor.extract_all_wikilinks(text, warnings, str(file_path))
        all_links.update(WikilinkExtractor.extract_from_dict(
            frontmatter,
            WikilinkExtractor.FRONTMATTER_BLACKLIST,
            warnings,
            str(file_path)
        ))

        # Parse date
        date_norm = frontmatter.get('date_norm') or frontmatter.get('date')
        if date_norm:
            date_start, date_end, _ = EDTFParser.parse(date_norm)
        else:
            date_start, date_end = None, None


        properties = {
            'title': file_path.stem,
            'file_path': rel_path,
            'source_path': rel_path,
            'content': self._extract_narrative_text(self._clean_markdown(body)),
            'date_norm': date_norm,
            'date_start': date_start,
            'date_end': date_end,
            'cote': frontmatter.get('cote'),
            'reference': frontmatter.get('reference') or frontmatter.get('archive_ref'),
            'fonds': frontmatter.get('fonds'),
            'versement': frontmatter.get('versement'),
            'shelfmark': frontmatter.get('shelfmark')
        }

        return {
            'id': doc_id,
            'properties': properties,
            'references': all_links - {doc_id}
        }

    def _build_document_id(self, file_path: Path, warnings: WikilinkWarnings) -> str:
        """Génère ID document depuis nom fichier uniquement"""
        file_name = file_path.name
        base_id = f"/id/document/{hashlib.sha1(file_name.encode('utf-8')).hexdigest()}"

        if base_id in self._doc_id_index:
            self._doc_id_index[base_id]["count"] += 1
            n = self._doc_id_index[base_id]["count"]
            warnings.log_document_id_collision(
                file_name,
                self._doc_id_index[base_id]["original_path"],
                str(file_path)
            )
            return f"{base_id}::{n}"
        else:
            self._doc_id_index[base_id] = {"count": 0, "original_path": str(file_path)}
            return base_id

    def _split_frontmatter(self, text: str) -> Tuple[Dict, str]:
        """Sépare frontmatter et corps"""
        if not text.startswith('---'):
            return {}, text

        parts = text.split('---', 2)
        if len(parts) < 3:
            return {}, text

        try:
            fm = yaml.safe_load(parts[1]) or {}
            body = parts[2].lstrip('\n')
            return fm, body
        except yaml.YAMLError:
            return {}, text

    def _is_archive_doc(self, frontmatter: Dict) -> bool:
        """Vérifie si c'est un document d'archive"""
        return any(key in frontmatter for key in self.ARCHIVE_KEYS)

    def _extract_narrative_text(self, body: str) -> str:
        """
        Extrait le texte narratif en excluant les métadonnées structurées

        Garde :
        - Texte entre highlights ==...==
        - Paragraphes narratifs

        Exclut :
        - Lignes Sender:/Recipient:/Place:/Date:/Concerns:
        - Blocs micro-actions (#micro_id:)
        - Commentaires Obsidian %% ... %%
        """
        # Séparer sur le dernier --- (début blocs micro-actions)
        parts = body.split('\n---\n')
        if len(parts) > 1:
            # Prendre tout AVANT le dernier ---
            narrative_part = parts[0]
        else:
            narrative_part = body

        # Enlever les métadonnées structurées du début
        lines = narrative_part.split('\n')
        cleaned_lines = []
        skip_metadata = True

        for line in lines:
            stripped = line.strip()

            # Skip métadonnées structurées
            if skip_metadata:
                if stripped.startswith(('Sender:', 'Recipient:', 'Place:', 'Date:', 'Concerns:')):
                    continue
                elif stripped == '':
                    continue
                else:
                    # Début du texte narratif
                    skip_metadata = False

            # Garder le texte narratif
            if not skip_metadata:
                # Enlever commentaires Obsidian
                line = re.sub(r'%%[^%]*%%', '', line)

                # Enlever highlights (garder le contenu)
                line = re.sub(r'==([^=]+)==', r'\1', line)

                if line.strip():
                    cleaned_lines.append(line)

        narrative_text = '\n'.join(cleaned_lines)

        # Si le texte est trop court, retourner le body original (fallback)
        if len(narrative_text.strip()) < 50:
            return body

        return narrative_text

    def _clean_markdown(self, md: str) -> str:
        """Nettoie markdown"""
        md = re.sub(
            r'\[\[/?(id/(?:person|org|gpe|place)/[0-9a-fA-F-]{36})\|([^\]]+)\]\]',
            r'\2 (/\1)',
            md
        )
        md = re.sub(
            r'\[\[/?(id/(?:person|org|gpe|place)/[0-9a-fA-F-]{36})\]\]',
            r'(/\1)',
            md
        )
        return md