#!/usr/bin/env python3
"""
Master Import Script - Corpus diplomatique suisse 1940-1945
Version : 2.3.2 (Fix Relations + Ajout Résidences)
Date : 2025-10-07

Import Obsidian → Neo4j avec filtrage par dossiers
Architecture : v1.5 | Extraction : v2.6 | Entités : v2.3

Modifications v2.3.1 (Fix Critical) :
- ✅ Fix robuste pour DATE/.. (fin inconnue)
- ✅ Fix robuste pour ../DATE (début inconnu)
- ✅ Gestion stricte des espaces et variations
- ✅ 100% coverage attendu sur dates normalisées
"""

import argparse
import os
import sys
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import json

from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, AuthError


# ============================================================================
# CONFIGURATION
# ============================================================================

@dataclass
class Config:
    """Configuration du script d'import - conforme config.json réel"""
    # Champs obligatoires (sans défaut)
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str
    vault_path: str

    # Champs optionnels (avec défaut)
    neo4j_database: str = "neo4j"
    schema_version: str = "v2.3"
    strict_mode: bool = False
    provenance_required: bool = True
    vocabularies_as_nodes: List[str] = field(default_factory=list)
    vocabularies_as_properties: List[str] = field(default_factory=list)
    calculated_relations_enable: bool = True
    write_detailed_report: bool = True
    monitor_references_threshold: int = 50

    @classmethod
    def from_file(cls, config_path: str = "config.json"):
        """Charge la config depuis config.json réel"""
        if not os.path.exists(config_path):
            print(f"❌ Fichier config.json introuvable : {config_path}")
            sys.exit(1)

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"❌ Erreur parsing config.json : {e}")
            sys.exit(1)

        # Validation password
        if not data["neo4j"]["password"]:
            print("❌ Mot de passe Neo4j manquant dans config.json")
            sys.exit(1)

        return cls(
            # Champs obligatoires
            neo4j_uri=data["neo4j"]["uri"],
            neo4j_user=data["neo4j"]["user"],
            neo4j_password=data["neo4j"]["password"],
            vault_path=data["vault_path"],

            # Champs optionnels
            neo4j_database=data["neo4j"].get("database", "neo4j"),
            schema_version=data["import_options"].get("schema_version", "v2.3"),
            strict_mode=data["import_options"].get("strict_mode", False),
            provenance_required=data["import_options"].get("provenance_required", True),
            vocabularies_as_nodes=data["import_options"]["vocabularies"].get("as_nodes", []),
            vocabularies_as_properties=data["import_options"]["vocabularies"].get("as_properties", []),
            calculated_relations_enable=data.get("import_options", {}).get("calculated_relations", {}).get("enable",
                                                                                                           True),
            write_detailed_report=data["report"].get("write_detailed_report", True),
            monitor_references_threshold=data["import_options"]["validation"].get("monitor_references_threshold", 50)
        )


# ============================================================================
# EDTF DATE PARSER (FIX v2.3.1)
# ============================================================================

def parse_edtf_date(edtf_string: str) -> Dict[str, Optional[str]]:
    """
    Parse EDTF string and return normalized dates.
    Handles all EDTF patterns including open dates (..).

    ✨ FIX v2.3.1 : Gestion robuste de DATE/.. et ../DATE

    Args:
        edtf_string (str): EDTF date string
            Examples:
            - "1942-03-29/1942-04-27" → interval
            - "../1942-05-05" → open start (début inconnu)
            - "1942-03-29/.." → open end (fin inconnue)
            - ".." → totally unknown
            - "1942-03-29" → exact date
            - "1942-03-29~" → approximate
            - "1942-03-29?" → uncertain

    Returns:
        dict: {
            'date_start': str or None (normalized, no ..)
            'date_end': str or None (normalized, no ..)
            'date_precision': str (interval, open_start, open_end, exact, etc.)
            'date_edtf': str (original)
        }
    """
    if not edtf_string or edtf_string.strip() == '':
        return {
            'date_start': None,
            'date_end': None,
            'date_precision': 'unknown',
            'date_edtf': edtf_string
        }

    edtf_string = edtf_string.strip()

    # Cas 1 : Totalement inconnu
    if edtf_string == '..':
        return {
            'date_start': None,
            'date_end': None,
            'date_precision': 'unknown',
            'date_edtf': edtf_string
        }

    # Cas 2 : Intervalle (avec ou sans dates ouvertes)
    if '/' in edtf_string:
        parts = edtf_string.split('/')

        # Parser chaque partie (filtrer ".." et nettoyer)
        date_start_raw = parts[0].strip()
        date_end_raw = parts[1].strip() if len(parts) > 1 else ''

        # ✨ FIX v2.3.1 : Normalisation robuste date_start
        if not date_start_raw or date_start_raw == '..' or date_start_raw == '':
            date_start = None
        else:
            # Nettoyer marqueurs EDTF (~, ?)
            date_start = date_start_raw.replace('~', '').replace('?', '').strip()
            # Double-check après nettoyage
            if date_start == '..':
                date_start = None

        # ✨ FIX v2.3.1 : Normalisation robuste date_end
        if not date_end_raw or date_end_raw == '..' or date_end_raw == '':
            date_end = None
        else:
            date_end = date_end_raw.replace('~', '').replace('?', '').strip()
            # Double-check après nettoyage
            if date_end == '..':
                date_end = None

        # Déterminer la précision
        if date_start is None and date_end is not None:
            precision = 'open_start'  # "../1942-05-05"
        elif date_start is not None and date_end is None:
            precision = 'open_end'  # "1942-03-29/.."
        elif date_start is None and date_end is None:
            precision = 'unknown'  # "../.."
        else:
            precision = 'interval'  # "1942-03-29/1942-04-27"

        return {
            'date_start': date_start,
            'date_end': date_end,
            'date_precision': precision,
            'date_edtf': edtf_string
        }

    # Cas 3 : Date approximative (~)
    if '~' in edtf_string:
        clean_date = edtf_string.replace('~', '').strip()
        return {
            'date_start': clean_date,
            'date_end': clean_date,
            'date_precision': 'approximate',
            'date_edtf': edtf_string
        }

    # Cas 4 : Date incertaine (?)
    if '?' in edtf_string:
        clean_date = edtf_string.replace('?', '').strip()
        return {
            'date_start': clean_date,
            'date_end': clean_date,
            'date_precision': 'uncertain',
            'date_edtf': edtf_string
        }

    # Cas 5 : Date exacte (YYYY-MM-DD)
    return {
        'date_start': edtf_string,
        'date_end': edtf_string,
        'date_precision': 'exact',
        'date_edtf': edtf_string
    }


# ============================================================================
# NEO4J CLIENT
# ============================================================================

class Neo4jClient:
    """Client Neo4j avec support Aura"""

    def __init__(self, config: Config):
        self.config = config
        self.driver = None
        self.stats = {
            'entities': 0,
            'documents': 0,
            'events': 0,
            'microactions': 0,
            'relations_performed': 0,
            'relations_received': 0,
            'relations_concerns': 0,
            'relations_contains': 0,
            'relations_participated': 0,
            'relations_located_in': 0,
            'relations_is_part_of': 0,
            'relations_worked_for': 0,
            'relations_references': 0
        }

    def connect(self):
        """Connexion à Neo4j"""
        try:
            # Pour Aura (neo4j+s://) l'encryption est automatique
            self.driver = GraphDatabase.driver(
                self.config.neo4j_uri,
                auth=(self.config.neo4j_user, self.config.neo4j_password),
                max_connection_lifetime=3600,
                max_connection_pool_size=50,
                connection_acquisition_timeout=120
            )

            # Test connexion
            self.driver.verify_connectivity()
            print(f"✅ Connecté à Neo4j : {self.config.neo4j_uri}")

        except AuthError:
            print(f"❌ Erreur d'authentification Neo4j")
            sys.exit(1)
        except ServiceUnavailable:
            print(f"❌ Neo4j non disponible à {self.config.neo4j_uri}")
            sys.exit(1)
        except Exception as e:
            print(f"❌ Erreur connexion Neo4j : {e}")
            sys.exit(1)

    def close(self):
        """Fermeture connexion"""
        if self.driver:
            self.driver.close()

    def clear_database(self):
        """Efface tous les nœuds et relations"""
        print("\n🗑️  Effacement de la base...")
        with self.driver.session(database=self.config.neo4j_database) as session:
            result = session.run("MATCH (n) DETACH DELETE n")
            print(f"  ✅ Base effacée")

    def create_constraints(self):
        """Crée les contraintes d'unicité et index"""
        print("\n🔒 Création des contraintes...")

        constraints = [
            # Contraintes d'unicité
            "CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (e:Person) REQUIRE e.id IS UNIQUE",
            "CREATE CONSTRAINT org_id IF NOT EXISTS FOR (o:Organization) REQUIRE o.id IS UNIQUE",
            "CREATE CONSTRAINT gpe_id IF NOT EXISTS FOR (g:GPE) REQUIRE g.id IS UNIQUE",
            "CREATE CONSTRAINT doc_id IF NOT EXISTS FOR (d:ArchiveDocument) REQUIRE d.id IS UNIQUE",
            "CREATE CONSTRAINT event_id IF NOT EXISTS FOR (e:Event) REQUIRE e.event_id IS UNIQUE",
            "CREATE CONSTRAINT micro_id IF NOT EXISTS FOR (m:MicroAction) REQUIRE m.micro_id IS UNIQUE",

            # Index pour performance (EXISTANTS)
            "CREATE INDEX person_name IF NOT EXISTS FOR (p:Person) ON (p.prefLabel_fr)",
            "CREATE INDEX org_name IF NOT EXISTS FOR (o:Organization) ON (o.prefLabel_fr)",
            "CREATE INDEX micro_date IF NOT EXISTS FOR (m:MicroAction) ON (m.date_start)",
            "CREATE INDEX event_date IF NOT EXISTS FOR (e:Event) ON (e.date_start)",

            # NOUVEAUX INDEX (critiques pour relations calculées)
            "CREATE INDEX micro_actor IF NOT EXISTS FOR (m:MicroAction) ON (m.actor_id)",
            "CREATE INDEX micro_recipient IF NOT EXISTS FOR (m:MicroAction) ON (m.recipient_id)",
            "CREATE INDEX micro_about IF NOT EXISTS FOR (m:MicroAction) ON (m.about_id)",
            "CREATE INDEX event_victim IF NOT EXISTS FOR (e:Event) ON (e.victim_id)",
            "CREATE INDEX event_date_end IF NOT EXISTS FOR (e:Event) ON (e.date_end)",
            "CREATE INDEX person_id IF NOT EXISTS FOR (p:Person) ON (p.id)",
            "CREATE INDEX org_id_lookup IF NOT EXISTS FOR (o:Organization) ON (o.id)"
        ]

        with self.driver.session(database=self.config.neo4j_database) as session:
            for constraint in constraints:
                try:
                    session.run(constraint)
                except Exception:
                    pass  # Constraint/index existe déjà

        print(f"  ✅ Contraintes et index créés")

    def resolve_entity(self, session, entity_id: str) -> Optional[str]:
        """
        Résout une entité (Person ou Organization) par son ID.
        Retourne le type ('Person', 'Organization') ou None.
        """
        # Tester Person
        result = session.run("""
            MATCH (p:Person {id: $entity_id})
            RETURN 'Person' as type
            LIMIT 1
        """, entity_id=entity_id)

        record = result.single()
        if record:
            return record["type"]

        # Tester Organization
        result = session.run("""
            MATCH (o:Organization {id: $entity_id})
            RETURN 'Organization' as type
            LIMIT 1
        """, entity_id=entity_id)

        record = result.single()
        if record:
            return record["type"]

        return None

    def create_microaction_relations(self, session, micro_id: str,
                                     actor_id: Optional[str] = None,
                                     recipient_id: Optional[str] = None) -> Tuple[bool, bool]:
        """
        Crée les relations PERFORMED et RECEIVED pour une MicroAction.
        Retourne (performed_created, received_created)
        """
        performed_created = False
        received_created = False

        # PERFORMED (acteur → micro-action)
        if actor_id:
            entity_type = self.resolve_entity(session, actor_id)
            if entity_type:
                session.run("""
                    MATCH (m:MicroAction {micro_id: $micro_id})
                    MATCH (a) WHERE a.id = $actor_id AND (a:Person OR a:Organization)
                    MERGE (a)-[:PERFORMED]->(m)
                """, micro_id=micro_id, actor_id=actor_id)
                performed_created = True
            else:
                print(f"    ⚠️  Acteur introuvable : {actor_id}")

        # RECEIVED (micro-action → destinataire)
        if recipient_id:
            entity_type = self.resolve_entity(session, recipient_id)
            if entity_type:
                session.run("""
                    MATCH (m:MicroAction {micro_id: $micro_id})
                    MATCH (r) WHERE r.id = $recipient_id AND (r:Person OR r:Organization)
                    MERGE (m)-[:RECEIVED]->(r)
                """, micro_id=micro_id, recipient_id=recipient_id)
                received_created = True
            else:
                print(f"    ⚠️  Destinataire introuvable : {recipient_id}")

        return performed_created, received_created

    def import_entities(self, entities: List[Dict]):
        """
        Import des entités avec structures réifiées
        ✨ FIX : Ordre d'import GPE → Organization → Person
        ✨ FIX : Import en deux passes pour garantir toutes les relations
        """
        if not entities:
            print("  ⚠️  Aucune entité à importer")
            return

        print(f"\n🔥 Import de {len(entities)} entités...")

        # ✨ TRI PAR TYPE : GPE → Organization → Person
        label_order = {'GPE': 1, 'Organization': 2, 'Person': 3}
        entities_sorted = sorted(
            entities,
            key=lambda e: label_order.get(e['label'], 999)
        )

        print(f"  📋 Ordre d'import :")
        gpe_count = sum(1 for e in entities_sorted if e['label'] == 'GPE')
        org_count = sum(1 for e in entities_sorted if e['label'] == 'Organization')
        person_count = sum(1 for e in entities_sorted if e['label'] == 'Person')
        print(f"     1. {gpe_count} GPE")
        print(f"     2. {org_count} Organizations")
        print(f"     3. {person_count} Persons")

        with self.driver.session(database=self.config.neo4j_database) as session:
            # ============================================================
            # PASSE 1 : Créer tous les nœuds principaux et structures
            # ============================================================
            print(f"  📦 Passe 1/2 : Création des nœuds...")

            for entity in entities_sorted:
                label = entity['label']
                entity_id = entity['id']
                props = entity['properties']

                # Créer nœud principal
                query = f"""
                MERGE (e:{label} {{id: $id}})
                SET e += $properties
                """
                session.run(query, id=entity_id, properties=props)
                self.stats['entities'] += 1

                # Relations spécifiques (qui ne dépendent pas de structures)
                for rel_type, targets in entity.get('specific_relations', {}).items():
                    for target_id in targets:
                        if rel_type == 'LOCATED_IN':
                            session.run("""
                                MATCH (e {id: $entity_id})
                                MATCH (g:GPE {id: $target_id})
                                MERGE (e)-[:LOCATED_IN]->(g)
                            """, entity_id=entity_id, target_id=target_id)
                            self.stats['relations_located_in'] += 1

                        elif rel_type == 'IS_PART_OF':
                            session.run("""
                                MATCH (child {id: $entity_id})
                                MATCH (parent:Organization {id: $target_id})
                                MERGE (child)-[:IS_PART_OF]->(parent)
                            """, entity_id=entity_id, target_id=target_id)
                            self.stats['relations_is_part_of'] += 1

                        elif rel_type == 'WORKED_FOR':
                            session.run("""
                                MATCH (p:Person {id: $entity_id})
                                MATCH (o:Organization {id: $target_id})
                                MERGE (p)-[:WORKED_FOR]->(o)
                            """, entity_id=entity_id, target_id=target_id)
                            self.stats['relations_worked_for'] += 1

                # Relations génériques REFERENCES
                for ref_id in entity.get('generic_references', []):
                    session.run("""
                        MATCH (e {id: $entity_id})
                        MATCH (target {id: $ref_id})
                        MERGE (e)-[:REFERENCES]->(target)
                    """, entity_id=entity_id, ref_id=ref_id)
                    self.stats['relations_references'] += 1

                # Créer structures réifiées (SANS relations vers autres entités)
                for struct_name, items in entity.get('structures', {}).items():
                    for item in items:
                        self._create_reified_structure_nodes_only(
                            session, entity_id, struct_name, item
                        )

            print(f"  ✅ {self.stats['entities']} entités créées")

            # ============================================================
            # PASSE 2 : Créer relations entre structures et entités
            # ============================================================
            print(f"  🔗 Passe 2/2 : Création des relations...")

            relations_created = 0

            for entity in entities_sorted:
                entity_id = entity['id']

                for struct_name, items in entity.get('structures', {}).items():
                    for item in items:
                        count = self._create_reified_structure_relations(
                            session, entity_id, struct_name, item
                        )
                        relations_created += count

            print(f"  ✅ {relations_created} relations créées entre structures")
            print(f"  ✅ {self.stats['relations_located_in']} LOCATED_IN")
            print(f"  ✅ {self.stats['relations_is_part_of']} IS_PART_OF")
            print(f"  ✅ {self.stats['relations_worked_for']} WORKED_FOR")
            print(f"  ✅ {self.stats['relations_references']} REFERENCES")

    def _create_reified_structure_nodes_only(self, session, entity_id: str,
                                             struct_type: str, item: Dict):
        """
        Passe 1 : Crée uniquement les nœuds de structures réifiées
        SANS les relations vers d'autres entités
        """
        rid = item.get('rid')
        props = item.get('properties', {})

        if struct_type == 'occupations':
            session.run("""
                MATCH (p:Person {id: $entity_id})
                CREATE (o:Occupation)
                SET o = $properties, o.rid = $rid
                MERGE (p)-[:HAS_OCCUPATION]->(o)
            """, entity_id=entity_id, rid=rid, properties=props)

        elif struct_type == 'names':
            session.run("""
                MATCH (p:Person {id: $entity_id})
                CREATE (n:Name)
                SET n = $properties, n.rid = $rid
                MERGE (p)-[:HAS_NAME]->(n)
            """, entity_id=entity_id, rid=rid, properties=props)

        elif struct_type == 'origins':
            session.run("""
                MATCH (p:Person {id: $entity_id})
                CREATE (o:Origin)
                SET o = $properties, o.rid = $rid
                MERGE (p)-[:HAS_ORIGIN]->(o)
            """, entity_id=entity_id, rid=rid, properties=props)

        elif struct_type == 'family_relations':
            session.run("""
                MATCH (p:Person {id: $entity_id})
                CREATE (fr:FamilyRelation)
                SET fr = $properties, fr.rid = $rid
                MERGE (p)-[:HAS_FAMILY_REL]->(fr)
            """, entity_id=entity_id, rid=rid, properties=props)

        elif struct_type == 'professional_relations':
            session.run("""
                MATCH (p:Person {id: $entity_id})
                CREATE (pr:ProfessionalRelation)
                SET pr = $properties, pr.rid = $rid
                MERGE (p)-[:HAS_PROF_REL]->(pr)
            """, entity_id=entity_id, rid=rid, properties=props)

        elif struct_type == 'residences':
            session.run("""
                        MATCH (p:Person {id: $entity_id})
                        CREATE (r:Residence)
                        SET r = $properties, r.rid = $rid
                        MERGE (p)-[:HAS_RESIDENCE]->(r)
                    """, entity_id=entity_id, rid=rid, properties=props)

    def _create_reified_structure_relations(self, session, entity_id: str,
                                            struct_type: str, item: Dict) -> int:
        """
        Passe 2 : Crée les relations entre structures réifiées et autres entités
        ✨ FIX v2.3.2 : Correction props.get('target') + ajout residences
        """
        rid = item.get('rid')
        props = item.get('properties', {})
        relations_created = 0

        if struct_type == 'occupations':
            org_id = props.get('organization')
            place_id = props.get('place')

            if org_id:
                result = session.run("""
                    MATCH (o:Occupation {rid: $rid})
                    MATCH (org:Organization {id: $org_id})
                    MERGE (o)-[:AT_ORGANIZATION]->(org)
                    RETURN count(*) as created
                """, rid=rid, org_id=org_id)
                if result.single()['created'] > 0:
                    relations_created += 1

            if place_id:
                result = session.run("""
                    MATCH (o:Occupation {rid: $rid})
                    MATCH (g:GPE {id: $place_id})
                    MERGE (o)-[:AT_PLACE]->(g)
                    RETURN count(*) as created
                """, rid=rid, place_id=place_id)
                if result.single()['created'] > 0:
                    relations_created += 1

        elif struct_type == 'origins':
            place_id = props.get('place')
            if place_id:
                result = session.run("""
                    MATCH (o:Origin {rid: $rid})
                    MATCH (g:GPE {id: $place_id})
                    MERGE (o)-[:AT_PLACE]->(g)
                    RETURN count(*) as created
                """, rid=rid, place_id=place_id)
                if result.single()['created'] > 0:
                    relations_created += 1

        elif struct_type == 'family_relations':
            # ✅ FIX v2.3.2 : props.get('target')
            target_id = props.get('target')
            if target_id:
                result = session.run("""
                    MATCH (fr:FamilyRelation {rid: $rid})
                    MATCH (target:Person {id: $target_id})
                    MERGE (fr)-[:RELATES_TO]->(target)
                    RETURN count(*) as created
                """, rid=rid, target_id=target_id)
                if result.single()['created'] > 0:
                    relations_created += 1

        elif struct_type == 'professional_relations':
            # ✅ FIX v2.3.2 : props.get('target')
            target_id = props.get('target')
            if target_id:
                result = session.run("""
                    MATCH (pr:ProfessionalRelation {rid: $rid})
                    MATCH (target {id: $target_id})
                    MERGE (pr)-[:RELATES_TO]->(target)
                    RETURN count(*) as created
                """, rid=rid, target_id=target_id)
                if result.single()['created'] > 0:
                    relations_created += 1

            # ✅ FIX v2.3.2 : organization_context
            org_id = props.get('organization_context')
            if org_id:
                result = session.run("""
                    MATCH (pr:ProfessionalRelation {rid: $rid})
                    MATCH (org:Organization {id: $org_id})
                    MERGE (pr)-[:IN_CONTEXT_OF]->(org)
                    RETURN count(*) as created
                """, rid=rid, org_id=org_id)
                if result.single()['created'] > 0:
                    relations_created += 1

        elif struct_type == 'residences':
            # ✨ NOUVEAU v2.3.2 : Support résidences
            place_id = props.get('place')
            if place_id:
                result = session.run("""
                    MATCH (r:Residence {rid: $rid})
                    MATCH (g:GPE {id: $place_id})
                    MERGE (r)-[:AT_PLACE]->(g)
                    RETURN count(*) as created
                """, rid=rid, place_id=place_id)
                if result.single()['created'] > 0:
                    relations_created += 1

        return relations_created




    def import_documents(self, documents: List[Dict]):
        """Import des documents"""
        if not documents:
            print("  ⚠️  Aucun document à importer")
            return

        print(f"\n📥 Import de {len(documents)} documents...")

        with self.driver.session(database=self.config.neo4j_database) as session:
            for doc in documents:
                session.run("""
                    MERGE (d:ArchiveDocument {id: $id})
                    SET d += $properties
                """, id=doc['id'], properties=doc['properties'])

                self.stats['documents'] += 1

                # Relations REFERENCES
                for ref_id in doc.get('references', []):
                    session.run("""
                        MATCH (d:ArchiveDocument {id: $doc_id})
                        MATCH (target {id: $ref_id})
                        MERGE (d)-[:REFERENCES]->(target)
                    """, doc_id=doc['id'], ref_id=ref_id)

        print(f"  ✅ {self.stats['documents']} documents importés")

    def import_events(self, events: List[Dict]):
        """
        Import des événements avec assertions.
        ✨ FIX v2.3.1 : Parse EDTF robuste pour DATE/.. et ../DATE
        """
        if not events:
            print("  ⚠️  Aucun événement à importer")
            return

        print(f"\n📥 Import de {len(events)} événements...")

        with self.driver.session(database=self.config.neo4j_database) as session:
            for event in events:
                event_id = event['event_id']
                props = event['properties'].copy()  # Copie pour modification

                # ✨ FIX v2.3.1 : Parser date_edtf pour créer date_start et date_end
                if 'date_edtf' in props and props['date_edtf']:
                    date_info = parse_edtf_date(props['date_edtf'])
                    props['date_start'] = date_info['date_start']
                    props['date_end'] = date_info['date_end']
                    props['date_precision'] = date_info['date_precision']

                    # Calculer gap_flag correctement
                    props['gap_flag'] = (date_info['date_start'] is None or
                                         date_info['date_end'] is None)
                else:
                    # Pas de date EDTF
                    props['date_start'] = None
                    props['date_end'] = None
                    props['date_precision'] = 'unknown'
                    props['gap_flag'] = True

                # Créer Event avec MERGE (gestion doublons)
                session.run("""
                    MERGE (e:Event {event_id: $event_id})
                    SET e += $properties
                """, event_id=event_id, properties=props)

                self.stats['events'] += 1

                # Créer Assertion
                assertion = event['assertion']
                session.run("""
                    MATCH (e:Event {event_id: $event_id})
                    MATCH (d:ArchiveDocument {id: $doc_id})
                    MERGE (a:Assertion {assertion_id: $assertion_id})
                    SET a += $assertion_props
                    MERGE (d)-[:SUPPORTS]->(a)
                    MERGE (a)-[:CLAIMS]->(e)
                """,
                            event_id=event_id,
                            doc_id=assertion['doc_id'],
                            assertion_id=assertion['assertion_id'],
                            assertion_props=assertion['properties']
                            )

                # Relations spécifiques (victim, agent, place)
                if props.get('victim_id'):
                    session.run("""
                        MATCH (e:Event {event_id: $event_id})
                        MATCH (v:Person {id: $victim_id})
                        MERGE (v)-[:WAS_VICTIM_OF]->(e)
                    """, event_id=event_id, victim_id=props['victim_id'])

                if props.get('agent_id') and props['agent_id'] != 'UNKNOWN_AUTHORITY':
                    session.run("""
                        MATCH (e:Event {event_id: $event_id})
                        MATCH (a {id: $agent_id})
                        MERGE (a)-[:ACTED_AS_AGENT]->(e)
                    """, event_id=event_id, agent_id=props['agent_id'])

                if props.get('place_id'):
                    session.run("""
                        MATCH (e:Event {event_id: $event_id})
                        MATCH (p:GPE {id: $place_id})
                        MERGE (e)-[:OCCURRED_AT]->(p)
                    """, event_id=event_id, place_id=props['place_id'])

                # Relations génériques REFERENCES
                for ref_id in event.get('references', []):
                    session.run("""
                        MATCH (e:Event {event_id: $event_id})
                        MATCH (target {id: $ref_id})
                        MERGE (e)-[:REFERENCES]->(target)
                    """, event_id=event_id, ref_id=ref_id)

                self.stats['relations_participated'] += 1

        print(f"  ✅ {self.stats['events']} événements importés")

    def import_microactions(self, microactions: List[Dict]):
        """
        Import des micro-actions avec relations PERFORMED/RECEIVED/CONCERNS.
        ✨ FIX v2.3.1 : Parse EDTF robuste pour DATE/.. et ../DATE
        """
        if not microactions:
            print("  ⚠️  Aucune micro-action à importer")
            return

        print(f"\n📥 Import de {len(microactions)} micro-actions...")

        performed_count = 0
        received_count = 0

        with self.driver.session(database=self.config.neo4j_database) as session:
            for micro in microactions:
                micro_id = micro['micro_id']
                props = micro['properties'].copy()  # Copie pour modification

                # ✨ FIX v2.3.1 : Parser date_edtf pour créer date_start et date_end
                if 'date_edtf' in props and props['date_edtf']:
                    date_info = parse_edtf_date(props['date_edtf'])
                    props['date_start'] = date_info['date_start']
                    props['date_end'] = date_info['date_end']
                    props['date_precision'] = date_info['date_precision']

                    # Calculer gap_flag correctement
                    props['gap_flag'] = (date_info['date_start'] is None or
                                         date_info['date_end'] is None)
                else:
                    # Pas de date EDTF
                    props['date_start'] = None
                    props['date_end'] = None
                    props['date_precision'] = 'unknown'
                    props['gap_flag'] = True

                # Créer MicroAction avec MERGE (gestion doublons)
                session.run("""
                    MERGE (m:MicroAction {micro_id: $micro_id})
                    SET m += $properties
                """, micro_id=micro_id, properties=props)

                self.stats['microactions'] += 1

                # Créer Assertion
                assertion = micro['assertion']
                session.run("""
                    MATCH (m:MicroAction {micro_id: $micro_id})
                    MATCH (d:ArchiveDocument {id: $doc_id})
                    MERGE (a:Assertion {assertion_id: $assertion_id})
                    SET a += $assertion_props
                    MERGE (d)-[:SUPPORTS]->(a)
                    MERGE (a)-[:CLAIMS]->(m)
                """,
                            micro_id=micro_id,
                            doc_id=assertion['doc_id'],
                            assertion_id=assertion['assertion_id'],
                            assertion_props=assertion['properties']
                            )

                # Créer PERFORMED et RECEIVED
                perf, recv = self.create_microaction_relations(
                    session,
                    micro_id=micro_id,
                    actor_id=props.get('actor_id'),
                    recipient_id=props.get('recipient_id')
                )

                if perf:
                    performed_count += 1
                if recv:
                    received_count += 1

                # Créer CONCERNS (lien principal vers personne concernée)
                if props.get('about_id'):
                    try:
                        session.run("""
                            MATCH (m:MicroAction {micro_id: $micro_id})
                            MATCH (p:Person {id: $about_id})
                            MERGE (m)-[:CONCERNS]->(p)
                        """, micro_id=micro_id, about_id=props['about_id'])
                        self.stats['relations_concerns'] += 1
                    except Exception as e:
                        print(f"    ⚠️  Erreur CONCERNS pour {micro_id}: {e}")

                # Relations génériques REFERENCES
                for ref_id in micro.get('references', []):
                    session.run("""
                        MATCH (m:MicroAction {micro_id: $micro_id})
                        MATCH (target {id: $ref_id})
                        MERGE (m)-[:REFERENCES]->(target)
                    """, micro_id=micro_id, ref_id=ref_id)

        self.stats['relations_performed'] = performed_count
        self.stats['relations_received'] = received_count

        print(f"  ✅ {self.stats['microactions']} micro-actions importées")
        print(f"  ✅ {performed_count} relations PERFORMED créées")
        print(f"  ✅ {received_count} relations RECEIVED créées")
        print(f"  ✅ {self.stats['relations_concerns']} relations CONCERNS créées")


# ============================================================================
# VALIDATION
# ============================================================================

class Validator:
    """Validation centralisée"""

    def __init__(self, config: Config):
        self.config = config
        self.report = []

    def validate_all(self, driver) -> bool:
        """Exécute toutes les validations"""
        print("\n🔍 Validation de l'import...")

        with driver.session(database=self.config.neo4j_database) as session:
            checks = [
                self._check_entities(session),
                self._check_documents(session),
                self._check_events(session),
                self._check_microactions(session),
                self._check_relations_performed(session),
                self._check_relations_received(session),
                self._check_relations_concerns(session),
                self._check_dates_parsed(session)
            ]

        all_valid = all(checks)

        if all_valid:
            print("✅ Toutes les validations ont réussi")
        else:
            print("⚠️  Certaines validations ont échoué")

        return all_valid

    def _check_entities(self, session) -> bool:
        """Vérifie les entités"""
        result = session.run("""
            MATCH (e) WHERE e:Person OR e:Organization OR e:GPE
            RETURN count(e) as count
        """)
        count = result.single()["count"]

        status = "✅" if count > 0 else "❌"
        self.report.append(f"{status} Entités : {count}")
        print(f"  {status} {count} entités dans le graphe")

        return count > 0

    def _check_documents(self, session) -> bool:
        """Vérifie les documents"""
        result = session.run("MATCH (d:ArchiveDocument) RETURN count(d) as count")
        count = result.single()["count"]

        status = "✅" if count > 0 else "⚠️ "
        self.report.append(f"{status} Documents : {count}")
        print(f"  {status} {count} documents dans le graphe")

        return True

    def _check_events(self, session) -> bool:
        """Vérifie les événements"""
        result = session.run("MATCH (e:Event) RETURN count(e) as count")
        count = result.single()["count"]

        status = "✅" if count > 0 else "⚠️ "
        self.report.append(f"{status} Événements : {count}")
        print(f"  {status} {count} événements dans le graphe")

        return True

    def _check_microactions(self, session) -> bool:
        """Vérifie les micro-actions"""
        result = session.run("MATCH (m:MicroAction) RETURN count(m) as count")
        count = result.single()["count"]

        status = "✅" if count > 0 else "⚠️ "
        self.report.append(f"{status} Micro-actions : {count}")
        print(f"  {status} {count} micro-actions dans le graphe")

        return True

    def _check_relations_performed(self, session) -> bool:
        """Vérifie les relations PERFORMED"""
        result = session.run("""
            MATCH ()-[r:PERFORMED]->()
            RETURN count(r) as count
        """)
        count = result.single()["count"]

        # Vérifier cohérence
        result2 = session.run("""
            MATCH (m:MicroAction)
            WHERE m.actor_id IS NOT NULL
            RETURN count(m) as count
        """)
        expected = result2.single()["count"]

        status = "✅" if count == expected else "⚠️ "
        self.report.append(f"{status} Relations PERFORMED : {count}/{expected}")
        print(f"  {status} {count}/{expected} relations PERFORMED")

        return count == expected

    def _check_relations_received(self, session) -> bool:
        """Vérifie les relations RECEIVED"""
        result = session.run("""
            MATCH ()-[r:RECEIVED]->()
            RETURN count(r) as count
        """)
        count = result.single()["count"]

        # Vérifier cohérence
        result2 = session.run("""
            MATCH (m:MicroAction)
            WHERE m.recipient_id IS NOT NULL
            RETURN count(m) as count
        """)
        expected = result2.single()["count"]

        status = "✅" if count == expected else "⚠️ "
        self.report.append(f"{status} Relations RECEIVED : {count}/{expected}")
        print(f"  {status} {count}/{expected} relations RECEIVED")

        return count == expected

    def _check_relations_concerns(self, session) -> bool:
        """Vérifie les relations CONCERNS"""
        result = session.run("""
            MATCH ()-[r:CONCERNS]->()
            RETURN count(r) as count
        """)
        count = result.single()["count"]

        # Vérifier cohérence
        result2 = session.run("""
            MATCH (m:MicroAction)
            WHERE m.about_id IS NOT NULL
            RETURN count(m) as count
        """)
        expected = result2.single()["count"]

        status = "✅" if count == expected else "⚠️ "
        self.report.append(f"{status} Relations CONCERNS : {count}/{expected}")
        print(f"  {status} {count}/{expected} relations CONCERNS")

        return count == expected

    def _check_dates_parsed(self, session) -> bool:
        """✨ v2.3.1 : Vérifie parsing complet des dates"""
        # Compter Events avec date_edtf
        result_edtf = session.run("""
            MATCH (e:Event) 
            WHERE e.date_edtf IS NOT NULL 
            RETURN count(e) as count
        """)
        with_edtf = result_edtf.single()["count"]

        # Compter Events avec date_start OU date_end créé
        result_parsed = session.run("""
            MATCH (e:Event) 
            WHERE e.date_edtf IS NOT NULL 
              AND (e.date_start IS NOT NULL OR e.date_end IS NOT NULL)
            RETURN count(e) as count
        """)
        parsed = result_parsed.single()["count"]

        # ✨ v2.3.1 : Accepter que certains events aient date_start=null OU date_end=null
        # (dates ouvertes), mais tous doivent avoir AU MOINS une des deux
        status = "✅" if parsed == with_edtf else "⚠️ "
        pct = round(100.0 * parsed / with_edtf, 1) if with_edtf > 0 else 0
        self.report.append(f"{status} Dates parsées : {parsed}/{with_edtf} events ({pct}%)")
        print(f"  {status} {parsed}/{with_edtf} events ont date_start/date_end ({pct}%)")

        return parsed == with_edtf

    def generate_markdown_report(self, stats: Dict, output_file: str = "import_report.md"):
        """Génère un rapport Markdown"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("# Rapport d'import Neo4j\n\n")
            f.write(f"**Date :** {timestamp}\n")
            f.write(f"**Version :** 2.3.1 (Fix EDTF Parser - Dates Ouvertes Bidirectionnelles)\n\n")

            f.write("## 📊 Statistiques d'import\n\n")
            f.write("| Élément | Nombre |\n")
            f.write("|---------|--------|\n")
            f.write(f"| Entités | {stats['entities']} |\n")
            f.write(f"| Documents | {stats['documents']} |\n")
            f.write(f"| Événements | {stats['events']} |\n")
            f.write(f"| Micro-actions | {stats['microactions']} |\n")
            f.write(f"| Relations PERFORMED | {stats['relations_performed']} |\n")
            f.write(f"| Relations RECEIVED | {stats['relations_received']} |\n")
            f.write(f"| Relations CONCERNS | {stats.get('relations_concerns', 0)} |\n")
            f.write(f"| Relations LOCATED_IN | {stats['relations_located_in']} |\n")
            f.write(f"| Relations IS_PART_OF | {stats['relations_is_part_of']} |\n")
            f.write(f"| Relations WORKED_FOR | {stats['relations_worked_for']} |\n")
            f.write(f"| Relations REFERENCES | {stats['relations_references']} |\n")
            f.write("\n")

            f.write("## ✅ Validation\n\n")
            for line in self.report:
                f.write(f"- {line}\n")
            f.write("\n")

        print(f"\n📄 Rapport généré : {output_file}")




# ============================================================================
# MAIN
# ============================================================================

def main():
    """Point d'entrée principal"""
    parser = argparse.ArgumentParser(
        description="Import Obsidian → Neo4j avec filtrage par dossiers"
    )
    parser.add_argument(
        '--folders',
        nargs='+',
        help='Dossiers à importer (ex: --folders sources_md chronologie)'
    )
    parser.add_argument(
        '--config',
        default='config.json',
        help='Fichier de configuration (défaut: config.json)'
    )

    args = parser.parse_args()

    # Chargement config
    config = Config.from_file(args.config)

    print("=" * 70)
    print("IMPORT OBSIDIAN → NEO4J")
    print("Corpus diplomatique suisse 1940-1945")
    print("Version 2.3.1 (Fix EDTF - Dates Ouvertes Bidirectionnelles)")
    print("=" * 70)

    if args.folders:
        print(f"\n📁 Dossiers ciblés : {', '.join(args.folders)}")
    else:
        print(f"\n📁 Import complet du vault")

    # Import parsers depuis utils/
    try:
        from utils import EntityParser, DocumentParser, EventParser, MicroActionParser
    except ImportError as e:
        print(f"❌ Erreur import modules utils/ : {e}")
        print("   Vérifiez que les fichiers suivants existent :")
        print("   - utils/__init__.py")
        print("   - utils/entity_parser.py")
        print("   - utils/document_parser.py")
        print("   - utils/event_parser.py")
        print("   - utils/microaction_parser.py")
        sys.exit(1)

    # Parsing Obsidian
    print("\n" + "=" * 70)
    print("PHASE 1 : PARSING OBSIDIAN")
    print("=" * 70)

    vault_path = Path(config.vault_path)
    if not vault_path.exists():
        print(f"❌ Vault introuvable : {vault_path}")
        sys.exit(1)

    folders_paths = [vault_path / f for f in args.folders] if args.folders else None

    config_dict = {
        "import_options": {
            "strict_mode": config.strict_mode,
            "provenance_required": config.provenance_required
        }
    }

    entity_parser = EntityParser(vault_path, config_dict, folders_paths)
    doc_parser = DocumentParser(vault_path, config_dict, folders_paths)
    event_parser = EventParser(vault_path, config_dict, folders_paths)
    micro_parser = MicroActionParser(vault_path, config_dict, folders_paths)

    print("\n📖 Parsing des entités (toutes)...")
    entities, entity_warnings = entity_parser.parse_all()
    print(f"  ✅ {len(entities)} entités parsées")

    print(f"\n📖 Parsing des documents...")
    documents, doc_warnings = doc_parser.parse_all()
    print(f"  ✅ {len(documents)} documents parsés")

    print(f"\n📖 Parsing des événements...")
    events, event_warnings = event_parser.parse_all()
    print(f"  ✅ {len(events)} événements parsés")

    print(f"\n📖 Parsing des micro-actions...")
    microactions, micro_warnings = micro_parser.parse_all()
    print(f"  ✅ {len(microactions)} micro-actions parsées")

    # Import Neo4j
    print("\n" + "=" * 70)
    print("PHASE 2 : IMPORT NEO4J")
    print("=" * 70)

    client = Neo4jClient(config)

    try:
        client.connect()
        client.clear_database()
        client.create_constraints()

        # Import par ordre de dépendances
        client.import_entities(entities)
        client.import_documents(documents)
        client.import_events(events)
        client.import_microactions(microactions)

        # PHASE 2.5 : Relations calculées
        if config.calculated_relations_enable:
            print("\n" + "=" * 70)
            print("PHASE 2.5 : RELATIONS CALCULÉES")
            print("=" * 70)

            from utils.relation_calculator import RelationCalculator

            calculator = RelationCalculator(config.__dict__)

            with client.driver.session(database=config.neo4j_database) as session:
                print("\n🔗 Calcul des relations...")

                count_replies = calculator.calculate_replies_to(session)
                print(f"  ✅ {count_replies} REPLIES_TO créées")

                count_chain = calculator.calculate_next_in_chain(session)
                print(f"  ✅ {count_chain} NEXT_IN_COMMUNICATION_CHAIN créées")

                count_context = calculator.calculate_acted_in_context(session)
                print(f"  ✅ {count_context} ACTED_IN_CONTEXT_OF créées")

                count_timeline = calculator.calculate_case_timeline(session)
                print(f"  ✅ {count_timeline} FOLLOWS_IN_CASE créées")

        # Validation
        print("\n" + "=" * 70)
        print("PHASE 3 : VALIDATION")
        print("=" * 70)

        validator = Validator(config)
        validator.validate_all(client.driver)

        if config.write_detailed_report:
            validator.generate_markdown_report(client.stats)

            # ✨ NOUVEAU : PHASE 3.5 - ENRICHISSEMENT REFERENCES
            print("\n" + "=" * 70)
            print("PHASE 3.5 : ENRICHISSEMENT REFERENCES")
            print("=" * 70)

            with client.driver.session(database=config.neo4j_database) as session:
                print("\n🔗 Enrichissement relations REFERENCES...")

                result = session.run("""
                        MATCH (source)-[r:REFERENCES]->(target)
                        WHERE r.entity_prefLabel IS NULL

                        WITH source, r, target
                        SET r.entity_prefLabel = target.prefLabel_fr,
                            r.entity_type = labels(target)[0]

                        RETURN count(r) as enriched
                    """)

                enriched_count = result.single()['enriched']
                print(f"  ✅ {enriched_count} relations REFERENCES enrichies")

        print("\n" + "=" * 70)
        print("✅ IMPORT TERMINÉ AVEC SUCCÈS")
        print("=" * 70)
        print(f"\n📊 Résumé :")
        print(f"  - {client.stats['entities']} entités")
        print(f"  - {client.stats['documents']} documents")
        print(f"  - {client.stats['events']} événements")
        print(f"  - {client.stats['microactions']} micro-actions")
        print(f"  - {client.stats['relations_performed']} PERFORMED")
        print(f"  - {client.stats['relations_received']} RECEIVED")
        print(f"  - {client.stats['relations_concerns']} CONCERNS")

    except Exception as e:
        print(f"\n❌ ERREUR : {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    finally:
        client.close()


if __name__ == "__main__":
    main()