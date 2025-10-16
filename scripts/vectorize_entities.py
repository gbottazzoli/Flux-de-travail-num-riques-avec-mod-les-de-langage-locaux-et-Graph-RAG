"""
Vectorisation des entités avec Gemini Embeddings
Version: 2.0 - Vertex AI Native
"""

import json
import re
import time
from pathlib import Path
from typing import Dict, List, Optional
from neo4j import GraphDatabase
from google.cloud import aiplatform
from vertexai.language_models import TextEmbeddingModel


class EntityVectorizerGemini:
    """Vectorise les entités du graphe avec Gemini"""

    def __init__(self, config_path: str = "config.json"):
        """Initialise avec config Neo4j et Vertex AI"""
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)

        # Neo4j
        neo4j_config = self.config['neo4j']
        self.driver = GraphDatabase.driver(
            neo4j_config['uri'],
            auth=(neo4j_config['user'], neo4j_config['password'])
        )

        # Vertex AI
        gcp_config = self.config['gcp']
        aiplatform.init(
            project=gcp_config['project_id'],
            location=gcp_config.get('location', 'us-central1')
        )

        # Model
        model_name = self.config.get('embedding_model', 'text-multilingual-embedding-002')
        self.embedding_model = TextEmbeddingModel.from_pretrained(model_name)
        self.dimensions = 768

        print(f"✅ Gemini model loaded: {model_name}")

        # Stats
        self.stats = {
            'entities_processed': 0,
            'chunks_created': 0,
            'embeddings_generated': 0,
            'describes_relations': 0,
            'mentions_relations': 0,
            'narrative_sections_found': 0,
            'occupations_found': 0,
            'origins_found': 0,
            'family_relations_found': 0,
            'errors': []
        }

    def close(self):
        """Ferme connexion Neo4j"""
        self.driver.close()

    def run(self):
        """Lance vectorisation complète"""
        print("\n" + "=" * 70)
        print("ENTITY VECTORIZATION v2.0 - Gemini Embeddings Native")
        print("=" * 70)

        # Vectoriser chaque type d'entité
        for label in ['Person', 'Organization', 'GPE']:
            self._vectorize_entities_by_label(label)

        # Rapport final
        self._print_report()

    def _vectorize_entities_by_label(self, label: str):
        """Vectorise toutes les entités d'un type"""
        print(f"\n📋 Processing {label} entities...")

        with self.driver.session() as session:
            result = session.run(f"""
                MATCH (e:{label})
                RETURN e.id as id, 
                       e.prefLabel_fr as prefLabel_fr,
                       e.prefLabel_de as prefLabel_de,
                       labels(e) as labels
                ORDER BY e.prefLabel_fr
            """)

            entities = list(result)
            print(f"  Found {len(entities)} {label} entities")

            for entity in entities:
                self._vectorize_single_entity(session, entity['id'], label)

        print(f"  ✅ Completed {label}")

    def _vectorize_single_entity(self, session, entity_id: str, label: str):
        """Vectorise une entité unique"""
        try:
            # 1. Assembler texte
            text = self._assemble_entity_text(session, entity_id, label)

            if not text or len(text.strip()) < 20:
                self.stats['errors'].append(f"Empty text for {entity_id}")
                return

            # 2. Générer embedding via Gemini
            embedding = self._generate_embedding_gemini(text)

            if not embedding:
                self.stats['errors'].append(f"Embedding failed for {entity_id}")
                return

            # 3. Créer chunk
            chunk_id = f"{entity_id}::entity_summary"
            self._create_chunk(session, chunk_id, text, embedding, entity_id, label)

            # 4. Créer relation DESCRIBES_ENTITY
            self._create_describes_entity_relation(session, chunk_id, entity_id)

            # 5. MENTIONS
            self._create_mentions_relations(session, chunk_id, text)

            self.stats['entities_processed'] += 1
            self.stats['chunks_created'] += 1
            self.stats['embeddings_generated'] += 1
            self.stats['describes_relations'] += 1

            if self.stats['entities_processed'] % 10 == 0:
                print(f"    Processed {self.stats['entities_processed']} entities...")

        except Exception as e:
            self.stats['errors'].append(f"{entity_id}: {str(e)}")

    def _assemble_entity_text(self, session, entity_id: str, label: str) -> str:
        """Assemble texte depuis Neo4j + markdown + structures réifiées"""
        parts = []

        # === PARTIE 1 : DEPUIS NEO4J ===

        if label == 'Person':
            result = session.run("""
                MATCH (e:Person {id: $id})
                RETURN e.prefLabel_fr as prefLabel_fr,
                       e.prefLabel_de as prefLabel_de,
                       e.aliases as aliases,
                       e.notice_bio as notice_bio,
                       e.status as status
            """, id=entity_id)

        elif label == 'Organization':
            result = session.run("""
                MATCH (e:Organization {id: $id})
                OPTIONAL MATCH (e)-[:LOCATED_IN]->(g:GPE)
                RETURN e.prefLabel_fr as prefLabel_fr,
                       e.prefLabel_de as prefLabel_de,
                       e.aliases as aliases,
                       e.notice_institutionnelle as notice_institutionnelle,
                       e.type as type,
                       g.prefLabel_fr as gpe_name
            """, id=entity_id)

        elif label == 'GPE':
            result = session.run("""
                MATCH (e:GPE {id: $id})
                RETURN e.prefLabel_fr as prefLabel_fr,
                       e.prefLabel_de as prefLabel_de,
                       e.aliases as aliases,
                       e.notice_geo as notice_geo,
                       e.coordinates_lat as lat,
                       e.coordinates_lon as lon
            """, id=entity_id)

        else:
            return ""

        entity = result.single()
        if not entity:
            return ""

        # Identité
        prefLabel_fr = entity.get('prefLabel_fr') or ""
        prefLabel_de = entity.get('prefLabel_de') or ""

        if prefLabel_fr:
            parts.append(prefLabel_fr)
            if prefLabel_de and prefLabel_de != prefLabel_fr:
                parts.append(f"({prefLabel_de})")
        elif prefLabel_de:
            parts.append(prefLabel_de)

        # Aliases
        aliases = entity.get('aliases', [])
        if aliases and isinstance(aliases, list) and len(aliases) > 0:
            parts.append(f"Alias: {', '.join(aliases[:3])}")

        # Notice
        if label == 'Person':
            notice = entity.get('notice_bio')
        elif label == 'Organization':
            notice = entity.get('notice_institutionnelle')
        elif label == 'GPE':
            notice = entity.get('notice_geo')
        else:
            notice = None

        if notice:
            parts.append(f"\n\n{notice}")

        # Type (Organisation)
        if label == 'Organization' and entity.get('type'):
            parts.append(f"\n\nType: {entity['type']}")

        # Localisation (Organization)
        if label == 'Organization':
            gpe_name = entity.get('gpe_name')
            if gpe_name:
                parts.append(f"\n\nLocalisation: {gpe_name}")

        # Coordonnées (GPE)
        if label == 'GPE':
            lat = entity.get('lat')
            lon = entity.get('lon')
            if lat is not None and lon is not None:
                parts.append(f"\n\nCoordonnées: {lat}, {lon}")

        # Hiérarchie (Organization)
        if label == 'Organization':
            try:
                hierarchy_result = session.run("""
                    MATCH (o:Organization {id: $id})-[:IS_PART_OF]->(parent:Organization)
                    RETURN parent.prefLabel_fr as parent_name
                    LIMIT 1
                """, id=entity_id)
                hierarchy_record = hierarchy_result.single()
                if hierarchy_record:
                    parts.append(f"\n\nFait partie de: {hierarchy_record['parent_name']}")
            except:
                pass

        # Sources
        try:
            sources_result = session.run("""
                MATCH (d:ArchiveDocument)-[:REFERENCES]->(e {id: $entity_id})
                RETURN DISTINCT d.cote as cote
                LIMIT 3
            """, entity_id=entity_id)
            sources = [r['cote'] for r in sources_result if r['cote']]
            if sources:
                parts.append(f"\n\nSources: {', '.join(sources)}")
        except:
            pass

        # === PARTIE 2 : DEPUIS MARKDOWN ===

        markdown_sections = self._extract_narrative_sections(entity_id)

        if markdown_sections.get('lieux_residence'):
            parts.append(f"\n\nLieux de résidence: {markdown_sections['lieux_residence']}")
            self.stats['narrative_sections_found'] += 1

        if markdown_sections.get('notes_recherche'):
            parts.append(f"\n\nNotes de recherche: {markdown_sections['notes_recherche']}")
            self.stats['narrative_sections_found'] += 1

        if markdown_sections.get('contexte_relationnel'):
            parts.append(f"\n\nContexte relationnel: {markdown_sections['contexte_relationnel']}")
            self.stats['narrative_sections_found'] += 1

        if markdown_sections.get('sources_principales'):
            parts.append(f"\n\nSources principales: {markdown_sections['sources_principales']}")
            self.stats['narrative_sections_found'] += 1

        # === PARTIE 3 : STRUCTURES RÉIFIÉES (Person) ===

        if label == 'Person':
            occupations = self._get_occupations(session, entity_id)
            if occupations:
                parts.append(f"\n\nOccupations: {occupations}")
                self.stats['occupations_found'] += 1

            origins = self._get_origins(session, entity_id)
            if origins:
                parts.append(f"\n\nOrigines: {origins}")
                self.stats['origins_found'] += 1

            family_rels = self._get_family_relations(session, entity_id)
            if family_rels:
                parts.append(f"\n\nRelations familiales: {family_rels}")
                self.stats['family_relations_found'] += 1

        return " ".join(parts)

    def _get_occupations(self, session, entity_id: str) -> str:
        """Extrait occupations depuis graphe"""
        try:
            result = session.run("""
                MATCH (p:Person {id: $id})-[:HAS_OCCUPATION]->(occ:Occupation)
                OPTIONAL MATCH (occ)-[:AT_ORGANIZATION]->(org:Organization)
                OPTIONAL MATCH (occ)-[:AT_PLACE]->(gpe:GPE)
                RETURN occ.type_activity as type_activity,
                       occ.position_title as position_title,
                       org.prefLabel_fr as org_name,
                       org.id as org_id,
                       gpe.prefLabel_fr as place_name,
                       gpe.id as place_id,
                       occ.interval as interval
                ORDER BY occ.interval DESC
                LIMIT 5
            """, id=entity_id)

            occupations = []
            for record in result:
                parts = []

                if record['position_title']:
                    parts.append(record['position_title'])
                elif record['type_activity']:
                    activity = record['type_activity'].replace('#type_activity/', '')
                    parts.append(activity)

                if record['org_name']:
                    parts.append(f"à {record['org_name']}")
                    if record['org_id']:
                        parts.append(record['org_id'])

                if record['place_name']:
                    parts.append(f"à {record['place_name']}")
                    if record['place_id']:
                        parts.append(record['place_id'])

                if record['interval']:
                    parts.append(f"({record['interval']})")

                if parts:
                    occupations.append(" ".join(parts))

            return "; ".join(occupations) if occupations else ""

        except Exception:
            return ""

    def _get_origins(self, session, entity_id: str) -> str:
        """Extrait origines depuis graphe"""
        try:
            result = session.run("""
                MATCH (p:Person {id: $id})-[:HAS_ORIGIN]->(orig:Origin)
                OPTIONAL MATCH (orig)-[:AT_PLACE]->(gpe:GPE)
                RETURN orig.mode as mode,
                       gpe.prefLabel_fr as place_name,
                       gpe.id as place_id,
                       orig.interval as interval,
                       orig.note as note
                ORDER BY orig.interval
                LIMIT 3
            """, id=entity_id)

            origins = []
            for record in result:
                parts = []

                if record['mode']:
                    mode = record['mode'].replace('#origin_mode/', '')
                    parts.append(mode)

                if record['place_name']:
                    parts.append(record['place_name'])
                    if record['place_id']:
                        parts.append(record['place_id'])

                if record['interval']:
                    parts.append(f"({record['interval']})")

                if parts:
                    origins.append(" ".join(parts))

            return "; ".join(origins) if origins else ""

        except Exception:
            return ""

    def _get_family_relations(self, session, entity_id: str) -> str:
        """Extrait relations familiales depuis graphe"""
        try:
            result = session.run("""
                MATCH (p:Person {id: $id})-[:HAS_FAMILY_REL]->(fr:FamilyRelation)
                OPTIONAL MATCH (target:Person {id: fr.target})
                RETURN fr.relation_type as relation_type,
                       target.prefLabel_fr as target_name,
                       target.id as target_id,
                       fr.interval as interval,
                       fr.note as note
                ORDER BY fr.interval
                LIMIT 5
            """, id=entity_id)

            relations = []
            for record in result:
                parts = []

                if record['relation_type']:
                    rel_type = record['relation_type'].replace('#relation_type/', '').replace('_', ' ')
                    parts.append(rel_type)

                if record['target_name']:
                    parts.append(f"de {record['target_name']}")
                    if record['target_id']:
                        parts.append(record['target_id'])

                if record['interval']:
                    parts.append(f"({record['interval']})")

                if parts:
                    relations.append(" ".join(parts))

            return "; ".join(relations) if relations else ""

        except Exception:
            return ""

    def _extract_narrative_sections(self, entity_id: str) -> dict:
        """Extrait sections narratives depuis fichier markdown"""
        sections = {}

        try:
            parts = entity_id.strip('/').split('/')
            if len(parts) != 3:
                return sections

            _, entity_type, uuid = parts

            vault_path = Path(self.config['vault_path'])
            folder_path = vault_path / 'id' / entity_type

            if not folder_path.exists():
                return sections

            markdown_file = None
            for md_file in folder_path.glob(f"{uuid}*.md"):
                markdown_file = md_file
                break

            if not markdown_file:
                return sections

            content = markdown_file.read_text(encoding='utf-8')

            sections['lieux_residence'] = self._extract_section(content, "Lieux de résidence")
            sections['notes_recherche'] = self._extract_section(content, "Notes de recherche")
            sections['contexte_relationnel'] = self._extract_section(content, "Contexte relationnel")
            sections['sources_principales'] = self._extract_section(content, "Sources principales")

        except Exception:
            pass

        return sections

    def _extract_section(self, content: str, section_title: str) -> str:
        """Extrait contenu d'une section markdown"""
        pattern = rf'##\s+{re.escape(section_title)}\s*\n(.*?)(?=\n##|\Z)'

        match = re.search(pattern, content, re.DOTALL)
        if not match:
            return ""

        section_content = match.group(1).strip()

        section_content = re.sub(r'\n{3,}', '\n\n', section_content)
        section_content = re.sub(r'\[\[(/id/[^\]|]+)\|([^\]]+)\]\]', r'\2 \1', section_content)
        section_content = re.sub(r'\[\[(/id/[^\]]+)\]\]', r'\1', section_content)
        section_content = re.sub(r'\[\[([^\]]+)\]\]', r'\1', section_content)
        section_content = re.sub(r'  +', ' ', section_content)

        if len(section_content) > 1000:
            section_content = section_content[:1000] + "..."

        return section_content

    def _generate_embedding_gemini(self, text: str) -> Optional[List[float]]:
        """Génère embedding via Gemini avec retry et rate limiting"""
        max_retries = 5
        base_delay = 1.0  # Délai de base entre requêtes

        for attempt in range(max_retries):
            try:
                # Rate limiting : attendre un peu entre chaque requête
                time.sleep(base_delay)

                embeddings = self.embedding_model.get_embeddings([text])
                return embeddings[0].values

            except Exception as e:
                error_str = str(e)

                # Si c'est une erreur de quota (429)
                if "429" in error_str or "Quota exceeded" in error_str:
                    wait_time = base_delay * (2 ** attempt)  # Exponential backoff
                    print(f"    ⏳ Quota exceeded, waiting {wait_time:.1f}s...")
                    time.sleep(wait_time)
                    continue

                # Autre erreur : retry avec délai plus court
                elif attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                else:
                    return None

        return None

    def _create_chunk(self, session, chunk_id: str, text: str,
                      embedding: List[float], entity_id: str, entity_type: str):
        """Crée nœud Chunk dans Neo4j"""
        session.run("""
            MERGE (c:Chunk {id: $chunk_id})
            SET c.text = $text,
                c.chunk_type = 'entity_summary',
                c.embedding = $embedding,
                c.embedding_model = $embedding_model,
                c.embedding_provider = $embedding_provider,
                c.entity_id = $entity_id,
                c.entity_type = $entity_type,
                c.char_count = $char_count
        """,
                    chunk_id=chunk_id,
                    text=text,
                    embedding=embedding,
                    embedding_model='text-multilingual-embedding-002',
                    embedding_provider='vertex-ai',
                    entity_id=entity_id,
                    entity_type=entity_type,
                    char_count=len(text)
                    )

    def _create_describes_entity_relation(self, session, chunk_id: str, entity_id: str):
        """Crée relation DESCRIBES_ENTITY"""
        session.run("""
            MATCH (c:Chunk {id: $chunk_id})
            MATCH (e {id: $entity_id})
            MERGE (c)-[:DESCRIBES_ENTITY {method: 'assembled'}]->(e)
        """,
                    chunk_id=chunk_id,
                    entity_id=entity_id
                    )

    def _create_mentions_relations(self, session, chunk_id: str, text: str):
        """Crée relations MENTIONS pour entités référencées dans texte"""
        pattern = r'/id/(person|org|gpe)/[0-9a-fA-F-]{36}'
        matches = re.finditer(pattern, text)
        found_ids = set()

        for match in matches:
            entity_id = match.group(0)
            if entity_id not in found_ids:
                found_ids.add(entity_id)

                try:
                    result = session.run("""
                        MATCH (e {id: $entity_id})
                        RETURN e.id as id
                    """, entity_id=entity_id)

                    if result.single():
                        session.run("""
                            MATCH (c:Chunk {id: $chunk_id})
                            MATCH (e {id: $entity_id})
                            MERGE (c)-[:MENTIONS {source: 'text'}]->(e)
                        """,
                                    chunk_id=chunk_id,
                                    entity_id=entity_id
                                    )
                        self.stats['mentions_relations'] += 1
                except:
                    pass

    def _print_report(self):
        """Affiche rapport final"""
        print("\n" + "=" * 70)
        print("ENTITY VECTORIZATION REPORT v2.0 - Gemini Embeddings")
        print("=" * 70)

        print(f"\n📊 STATISTICS")
        print("-" * 70)
        print(f"Entities processed: {self.stats['entities_processed']}")
        print(f"Chunks created: {self.stats['chunks_created']}")
        print(f"Embeddings generated (Gemini): {self.stats['embeddings_generated']}")
        print(f"Narrative sections found: {self.stats['narrative_sections_found']}")
        print(f"Occupations found: {self.stats['occupations_found']}")
        print(f"Origins found: {self.stats['origins_found']}")
        print(f"Family relations found: {self.stats['family_relations_found']}")

        if self.stats['chunks_created'] > 0:
            avg_sections = self.stats['narrative_sections_found'] / self.stats['chunks_created']
            avg_occupations = self.stats['occupations_found'] / self.stats['chunks_created']
            print(f"  → Average {avg_sections:.1f} narrative sections per entity")
            print(f"  → Average {avg_occupations:.1f} occupations per entity")

        print(f"\n🔗 RELATIONS")
        print("-" * 70)
        print(f"DESCRIBES_ENTITY: {self.stats['describes_relations']}")
        print(f"MENTIONS: {self.stats['mentions_relations']}")

        if self.stats['errors']:
            print(f"\n⚠️ ERRORS ({len(self.stats['errors'])})")
            print("-" * 70)
            for error in self.stats['errors'][:10]:
                print(f"  • {error}")
            if len(self.stats['errors']) > 10:
                print(f"  ... and {len(self.stats['errors']) - 10} more")

        print("\n" + "=" * 70)
        if self.stats['chunks_created'] > 0:
            print(f"✅ SUCCESS: {self.stats['chunks_created']} entity chunks created!")
            print(f"   Plus {self.stats['mentions_relations']} MENTIONS relations")
            print(f"   🚀 Using Gemini embeddings for Claude agent")
        else:
            print("⚠️ WARNING: No chunks created")
        print("=" * 70)


def main():
    """Point d'entrée principal"""
    import sys

    config_path = "config.json"
    if len(sys.argv) > 1:
        config_path = sys.argv[1]

    vectorizer = EntityVectorizerGemini(config_path)

    try:
        vectorizer.run()
    finally:
        vectorizer.close()


if __name__ == "__main__":
    main()