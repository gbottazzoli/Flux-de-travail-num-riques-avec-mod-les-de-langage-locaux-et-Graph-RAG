# Architecture d'Import Neo4j v2.1

**Version** : 2.1  
**Date** : 2025-10-11  
**Statut** : ✅ Production - Testé et validé

---

## 📋 TABLE DES MATIÈRES

1. [Vue d'Ensemble](#vue-densemble)
2. [Modèle de Données](#modèle-de-données)
3. [Relations](#relations)
4. [Ordre d'Import](#ordre-dimport)
5. [Patterns de Requêtes](#patterns-de-requêtes)
6. [Index & Contraintes](#index--contraintes)
7. [Validation](#validation)

---

## 🎯 Vue d'Ensemble

### Architecture en 5 Couches

```

COUCHE 1 : ENTITÉS FONDAMENTALES ├── Person (48) ├── Organization (29) └── GPE (23)

COUCHE 2 : STRUCTURES RÉIFIÉES ├── Name (198) ├── Occupation (156) ├── Origin (87) ├── FamilyRelation (43) └── ProfessionalRelation (29)

COUCHE 3 : ÉVÉNEMENTS & ACTIONS ├── Event (92) └── MicroAction (202)

COUCHE 4 : PROVENANCE ├── ArchiveDocument (55) └── Assertion (264)

COUCHE 5 : RAG └── Chunk (325) ├── quote_centered (225) └── entity_summary (100)

````

---

## 🗂️ Modèle de Données

### Person

```cypher
Person {
  id: "/id/person/{uuid}",
  prefLabel_fr: "Müller Elisabeth",
  prefLabel_de: "Müller Elisabeth",
  aliases: ["Elisabet", "Mme Muller"],
  notice_bio: string,
  status: "validated" | "provisional"
}

Relations sortantes:
- [:HAS_NAME] → Name
- [:HAS_OCCUPATION] → Occupation
- [:HAS_ORIGIN] → Origin
- [:HAS_FAMILY_REL] → FamilyRelation
- [:HAS_PROF_REL] → ProfessionalRelation
- [:WORKED_FOR] → Organization
- [:WAS_VICTIM_OF] → Event

Relations entrantes:
- [:CONCERNS] ← MicroAction
- [:RELATES_TO] ← FamilyRelation, ProfessionalRelation
````

### Organization

```cypher
Organization {
  id: "/id/org/{uuid}",
  prefLabel_fr: "Consulat Suisse Paris",
  prefLabel_de: string,
  type: "diplomatic_representation" | "government_agency",
  notice_institutionnelle: string
}

Relations:
- [:LOCATED_IN] → GPE
- [:IS_PART_OF] → Organization
- [:PERFORMED] → MicroAction
- [:RECEIVED] ← MicroAction
```

### GPE (Geopolitical Entity)

```cypher
GPE {
  id: "/id/gpe/{uuid}",
  prefLabel_fr: "Paris",
  prefLabel_de: "Paris",
  aliases: ["Paname"],
  notice_geo: string,
  coordinates_lat: float,
  coordinates_lon: float,
  geonames_id: string
}

Relations entrantes:
- [:LOCATED_IN] ← Organization
- [:AT_PLACE] ← Occupation, Origin
- [:OCCURRED_AT] ← Event
```

---

### Structures Réifiées

#### Occupation

```cypher
Occupation {
  rid: string,
  type_activity: "consul" | "diplomate",
  position_title: "Consul honoraire",
  interval: "1935-1941",
  date_start: date,
  date_end: date,
  organization: string,  // ID Organization
  place: string,         // ID GPE
  doc: string,
  quote: string,
  evidence_type: string,
  confidence: string
}

Relations:
- ← [:HAS_OCCUPATION] (Person)
- → [:AT_ORGANIZATION] (Organization)
- → [:AT_PLACE] (GPE)
```

#### Name

```cypher
Name {
  rid: string,
  display: "Müller, Elisabeth",
  parts_family: "Müller",
  parts_given: "Elisabeth",
  parts_particle: null,
  lang: "de" | "fr",
  interval: string,
  type: "birth_name" | "married_name",
  doc: string,
  quote: string
}

Relations:
- ← [:HAS_NAME] (Person)
```

#### Origin

```cypher
Origin {
  rid: string,
  mode: "birth" | "residence" | "nationality",
  place: string,  // ID GPE
  interval: string,
  is_primary: boolean,
  doc: string,
  quote: string
}

Relations:
- ← [:HAS_ORIGIN] (Person)
- → [:AT_PLACE] (GPE)
```

#### FamilyRelation

```cypher
FamilyRelation {
  rid: string,
  relation_type: "mère" | "père" | "enfant" | "conjoint",
  target: string,  // ID Person
  interval: string,
  description: string,
  doc: string,
  quote: string
}

Relations:
- ← [:HAS_FAMILY_REL] (Person)
- → [:RELATES_TO] (Person)
```

#### ProfessionalRelation

```cypher
ProfessionalRelation {
  rid: string,
  relation_type: "collègue" | "supérieur" | "collaborateur",
  target: string,              // ID Person
  organization_context: string, // ID Organization
  interval: string,
  description: string,
  doc: string,
  quote: string
}

Relations:
- ← [:HAS_PROF_REL] (Person)
- → [:RELATES_TO] (Person)
- → [:IN_CONTEXT_OF] (Organization)
```

---

### Event

```cypher
Event {
  event_id: "/id/event/{sha1}",
  victim_id: "/id/person/{uuid}",    // Propriété + relation WAS_VICTIM_OF
  place_id: "/id/gpe/{uuid}",
  agent_id: "/id/org/{uuid}",
  agent_role: "arresting" | "sentencing" | "detaining",
  agent_precision: string,
  tags: ["#persecution/legal/arrest"],
  description: string,
  date_start: date,        // Date normalisée (pour filtres)
  date_end: date,
  date_edtf: string,       // Format EDTF original
  date_precision: "day" | "month" | "year",
  confidence: "high" | "medium" | "low",
  gap_flag: boolean,
  uncertainty_flag: boolean,
  unknown_agent: boolean
}

Relations:
- ← [:WAS_VICTIM_OF] (Person)
- ← [:ACTED_AS_AGENT] (Organization)
- → [:OCCURRED_AT] (GPE)
- ← [:CLAIMS] (Assertion)
```

### MicroAction

```cypher
MicroAction {
  micro_id: "/id/microaction/{sha1}",
  actor_id: "/id/org/{uuid}",      // Propriété + relation PERFORMED
  recipient_id: "/id/org/{uuid}",  // Propriété + relation RECEIVED
  about_id: "/id/person/{uuid}",   // Propriété + relation CONCERNS
  action_type: "administrative/correspondence",
  link_type: "informs" | "requests" | "acknowledges_receipt",
  date_start: date,
  date_edtf: string,
  in_reply_to_date: string,
  confidence: "high" | "medium" | "low"
}

Relations:
- ← [:PERFORMED] (Organization)
- → [:RECEIVED] (Organization)
- → [:CONCERNS] (Person)
- ← [:CLAIMS] (Assertion)
```

### ArchiveDocument

```cypher
ArchiveDocument {
  id: "/id/document/{sha1}",
  cote: "E2001E#1000/1571#5682*",
  reference: "dodis.ch/...",
  date_norm: "1942-04-27",
  content: string,
  source_path: "sources_md/doc-001.md"
}

Relations:
- → [:SUPPORTS] (Assertion)
- ← [:CHUNK_OF] (Chunk)
```

### Assertion

```cypher
Assertion {
  assertion_id: string,
  source_quote: string,
  confidence: "high" | "medium" | "low",
  evidence_type: "direct_observation" | "reported" | "inferred",
  type: string
}

Relations:
- ← [:SUPPORTS] (ArchiveDocument)
- → [:CLAIMS] (Event | MicroAction)
```

### Chunk (RAG)

```cypher
Chunk {
  id: string,
  text: string,
  chunk_type: "quote_centered" | "entity_summary",
  embedding: [float],  // 768D
  
  // quote_centered
  start_char: integer,
  end_char: integer,
  doc_id: string,
  year: integer,
  assertion_id: string,
  match_method: "exact" | "fuzzy",
  
  // entity_summary
  entity_id: string,
  entity_type: "Person" | "Organization" | "GPE",
  char_count: integer
}

Relations:
- → [:CHUNK_OF] (ArchiveDocument)       // Documents uniquement
- → [:DESCRIBES_EVENT] (Event)
- → [:DESCRIBES_ACTION] (MicroAction)
- → [:DESCRIBES_ENTITY] (Person/Org/GPE) // Entités uniquement
- → [:MENTIONS] (Person/Org/GPE)
```

---

## 🔗 Relations

### Relations Structurelles

```cypher
// Person → Structures
(Person)-[:HAS_OCCUPATION]->(Occupation)
(Person)-[:HAS_NAME]->(Name)
(Person)-[:HAS_ORIGIN]->(Origin)
(Person)-[:HAS_FAMILY_REL]->(FamilyRelation)
(Person)-[:HAS_PROF_REL]->(ProfessionalRelation)

// Structures → Contexte
(Occupation)-[:AT_ORGANIZATION]->(Organization)
(Occupation)-[:AT_PLACE]->(GPE)
(Origin)-[:AT_PLACE]->(GPE)
(FamilyRelation)-[:RELATES_TO]->(Person)
(ProfessionalRelation)-[:RELATES_TO]->(Person)
(ProfessionalRelation)-[:IN_CONTEXT_OF]->(Organization)
```

### Relations Géographiques & Hiérarchiques

```cypher
(Organization)-[:LOCATED_IN]->(GPE)
(Organization)-[:IS_PART_OF]->(Organization)
(Person)-[:WORKED_FOR]->(Organization)
```

### Relations Événements

```cypher
(Person)-[:WAS_VICTIM_OF]->(Event)
(Organization)-[:ACTED_AS_AGENT]->(Event)
(Event)-[:OCCURRED_AT]->(GPE)
```

### Relations Communications

```cypher
(Organization)-[:PERFORMED]->(MicroAction)
(MicroAction)-[:RECEIVED]->(Organization)
(MicroAction)-[:CONCERNS]->(Person)
```

### Relations Provenance

```cypher
(ArchiveDocument)-[:SUPPORTS]->(Assertion)
(Assertion)-[:CLAIMS]->(Event)
(Assertion)-[:CLAIMS]->(MicroAction)
```

### Relations RAG

```cypher
// Documents
(Chunk {chunk_type: 'quote_centered'})-[:CHUNK_OF]->(ArchiveDocument)
(Chunk)-[:DESCRIBES_EVENT]->(Event)
(Chunk)-[:DESCRIBES_ACTION]->(MicroAction)
(Chunk)-[:MENTIONS]->(Person|Organization|GPE)

// Entités
(Chunk {chunk_type: 'entity_summary'})-[:DESCRIBES_ENTITY]->(Person|Organization|GPE)
```

### Relations Calculées (computed: true)

```cypher
(MicroAction)-[:NEXT_IN_COMMUNICATION_CHAIN]->(MicroAction)
(MicroAction)-[:REPLIES_TO]->(MicroAction)
(Event)-[:FOLLOWS_IN_CASE]->(Event)
(MicroAction)-[:ACTED_IN_CONTEXT_OF]->(Event)
```

---

## ⚠️ Ordre d'Import CRITIQUE

Les relations nécessitent que les nœuds cibles existent AVANT.

### Ordre Correct

```python
# Dans master_import.py
ENTITY_FOLDERS = ["id/gpe", "id/person", "id/org"]
#                  ↑ GPE EN PREMIER !
```

### Flux d'Import

```
1. GPE (23 nœuds)
   ↓
2. Person (48 nœuds)
   ↓ Crée structures réifiées
   ↓ HAS_OCCUPATION → Occupation
   ↓ HAS_ORIGIN → Origin (référence GPE)
   
3. Organization (29 nœuds)
   ↓ Crée LOCATED_IN → GPE ✅ (GPE existe déjà)
   
4. Documents (55)
   ↓
5. Events & MicroActions (294)
   ↓ Référencent Person, Organization, GPE
   
6. Relations calculées
```

---

## 🎯 Patterns de Requêtes

### Pattern 1 : Event → Person (Deux méthodes valides)

```cypher
// Méthode 1 : Via relation WAS_VICTIM_OF
MATCH (p:Person)-[:WAS_VICTIM_OF]->(e:Event)
WHERE p.prefLabel_fr = "Müller Elisabeth"
RETURN e;

// Méthode 2 : Via propriété victim_id
MATCH (p:Person {prefLabel_fr: "Müller Elisabeth"})
MATCH (e:Event)
WHERE e.victim_id = p.id
RETURN e;

// Les deux fonctionnent !
```

### Pattern 2 : Person avec Structures Réifiées

```cypher
MATCH (p:Person {prefLabel_fr: "Müller Elisabeth"})

// Occupations avec contexte
OPTIONAL MATCH (p)-[:HAS_OCCUPATION]->(occ:Occupation)
OPTIONAL MATCH (occ)-[:AT_ORGANIZATION]->(org:Organization)
OPTIONAL MATCH (occ)-[:AT_PLACE]->(place:GPE)

// Origines
OPTIONAL MATCH (p)-[:HAS_ORIGIN]->(orig:Origin)
OPTIONAL MATCH (orig)-[:AT_PLACE]->(birth_place:GPE)

// Relations familiales
OPTIONAL MATCH (p)-[:HAS_FAMILY_REL]->(fam:FamilyRelation)
OPTIONAL MATCH (fam)-[:RELATES_TO]->(relative:Person)

// Relations professionnelles
OPTIONAL MATCH (p)-[:HAS_PROF_REL]->(prof:ProfessionalRelation)
OPTIONAL MATCH (prof)-[:RELATES_TO]->(colleague:Person)
OPTIONAL MATCH (prof)-[:IN_CONTEXT_OF]->(context_org:Organization)

RETURN p, 
       collect(DISTINCT occ) AS occupations,
       collect(DISTINCT orig) AS origins,
       collect(DISTINCT fam) AS family,
       collect(DISTINCT prof) AS professional;
```

### Pattern 3 : Timeline Enrichie

```cypher
MATCH (p:Person {prefLabel_fr: "Müller Elisabeth"})
MATCH (p)-[:WAS_VICTIM_OF]->(e:Event)

// Occupations à la date de l'événement
OPTIONAL MATCH (p)-[:HAS_OCCUPATION]->(occ:Occupation)
WHERE (occ.date_start IS NULL OR date(occ.date_start) <= e.date_start)
  AND (occ.date_end IS NULL OR date(occ.date_end) >= e.date_start)

// Provenance
OPTIONAL MATCH (a:Assertion)-[:CLAIMS]->(e)
OPTIONAL MATCH (d:ArchiveDocument)-[:SUPPORTS]->(a)

RETURN 
  e.date_start AS date,
  e.description AS evenement,
  occ.position_title AS fonction_a_cette_date,
  a.source_quote AS citation,
  d.cote AS document

ORDER BY e.date_start;
```

### Pattern 4 : Communications Diplomatiques

```cypher
MATCH (actor:Organization)-[:PERFORMED]->(m:MicroAction)-[:RECEIVED]->(recipient:Organization)
WHERE actor.prefLabel_fr = "Consulat Suisse Paris"
OPTIONAL MATCH (m)-[:CONCERNS]->(p:Person)
RETURN m.date_start, recipient.prefLabel_fr, p.prefLabel_fr, m.link_type
ORDER BY m.date_start;
```

### Pattern 5 : Provenance Complète

```cypher
MATCH (e:Event {event_id: "/id/event/..."})
MATCH (a:Assertion)-[:CLAIMS]->(e)
MATCH (d:ArchiveDocument)-[:SUPPORTS]->(a)
RETURN 
  d.cote AS document,
  d.date_norm AS date_document,
  a.source_quote AS citation_exacte,
  a.confidence AS niveau_confiance;
```

### Pattern 6 : Recherche RAG (Documents)

```cypher
MATCH (c:Chunk {chunk_type: 'quote_centered'})-[:DESCRIBES_EVENT]->(e:Event)
WHERE toLower(c.text) CONTAINS "détenue"
OPTIONAL MATCH (p:Person)-[:WAS_VICTIM_OF]->(e)
RETURN c.text, e.date_start, p.prefLabel_fr
LIMIT 5;
```

### Pattern 7 : Recherche Biographique (Entités)

```cypher
MATCH (c:Chunk {chunk_type: 'entity_summary'})-[:DESCRIBES_ENTITY]->(p:Person)
WHERE p.prefLabel_fr = "Müller Elisabeth"
RETURN c.text AS biographie_complete;
```

---

## 📇 Index & Contraintes

### Contraintes d'Unicité

```cypher
CREATE CONSTRAINT person_id IF NOT EXISTS 
FOR (p:Person) REQUIRE p.id IS UNIQUE;

CREATE CONSTRAINT org_id IF NOT EXISTS 
FOR (o:Organization) REQUIRE o.id IS UNIQUE;

CREATE CONSTRAINT gpe_id IF NOT EXISTS 
FOR (g:GPE) REQUIRE g.id IS UNIQUE;

CREATE CONSTRAINT doc_id IF NOT EXISTS 
FOR (d:ArchiveDocument) REQUIRE d.id IS UNIQUE;

CREATE CONSTRAINT event_id IF NOT EXISTS 
FOR (e:Event) REQUIRE e.event_id IS UNIQUE;

CREATE CONSTRAINT micro_id IF NOT EXISTS 
FOR (m:MicroAction) REQUIRE m.micro_id IS UNIQUE;

CREATE CONSTRAINT chunk_id IF NOT EXISTS 
FOR (c:Chunk) REQUIRE c.id IS UNIQUE;
```

### Index de Performance

```cypher
CREATE INDEX person_name IF NOT EXISTS 
FOR (p:Person) ON (p.prefLabel_fr);

CREATE INDEX org_name IF NOT EXISTS 
FOR (o:Organization) ON (o.prefLabel_fr);

CREATE INDEX event_date IF NOT EXISTS 
FOR (e:Event) ON (e.date_start);

CREATE INDEX micro_date IF NOT EXISTS 
FOR (m:MicroAction) ON (m.date_start);

CREATE INDEX micro_actor IF NOT EXISTS 
FOR (m:MicroAction) ON (m.actor_id);

CREATE INDEX micro_recipient IF NOT EXISTS 
FOR (m:MicroAction) ON (m.recipient_id);

CREATE INDEX event_victim IF NOT EXISTS 
FOR (e:Event) ON (e.victim_id);

CREATE INDEX chunk_type IF NOT EXISTS 
FOR (c:Chunk) ON (c.chunk_type);
```

### Index Vectoriel (RAG)

```cypher
CREATE VECTOR INDEX chunk_embeddings IF NOT EXISTS
FOR (c:Chunk) ON (c.embedding)
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 768,
    `vector.similarity_function`: 'cosine'
  }
};
```

---

## ✅ Validation

### Tests Exécutés sur Corpus Réel

#### Test 1 : Structures Réifiées Créées

```cypher
MATCH (o:Occupation) RETURN count(o);  // 156
MATCH (n:Name) RETURN count(n);        // 198
MATCH (orig:Origin) RETURN count(orig); // 87
MATCH (fr:FamilyRelation) RETURN count(fr); // 43
MATCH (pr:ProfessionalRelation) RETURN count(pr); // 29
```

#### Test 2 : Relations Secondaires Créées

```cypher
MATCH ()-[r:AT_ORGANIZATION]->() RETURN count(r);
MATCH ()-[r:AT_PLACE]->() RETURN count(r);
MATCH ()-[r:RELATES_TO]->() RETURN count(r);
MATCH ()-[r:IN_CONTEXT_OF]->() RETURN count(r);
```

#### Test 3 : Relations Géographiques

```cypher
MATCH (o:Organization)-[:LOCATED_IN]->(g:GPE) RETURN count(*); // 29
```

#### Test 4 : WAS_VICTIM_OF

```cypher
MATCH (p:Person)-[:WAS_VICTIM_OF]->(e:Event)
RETURN count(*) AS total;
// Doit retourner > 0
```

#### Test 5 : Dates Normalisées

```cypher
MATCH (e:Event)
WHERE e.date_edtf IS NOT NULL
  AND (e.date_start IS NOT NULL OR e.date_end IS NOT NULL)
RETURN count(e);
// Doit égaler le nombre total d'Events avec date_edtf
```

#### Test 6 : RAG Hybride

```cypher
MATCH (c:Chunk)
RETURN c.chunk_type, count(*) AS count;
// quote_centered: 225
// entity_summary: 100
```

---

## 🎓 Pour les Développeurs

### Règles d'Or

1. **Ordre import** : TOUJOURS GPE → Person → Organization
2. **Event → Person** : Utiliser victim_id (propriété) OU WAS_VICTIM_OF (relation)
3. **Structures réifiées** : Accès via HAS_OCCUPATION, HAS_ORIGIN, etc.
4. **Dates** : Filtrer sur date_start/date_end (normalisé), PAS date_edtf
5. **RAG** : Distinguer chunk_type: quote_centered vs entity_summary

### Checklist Import Réussi

```bash
# 1. Vérifier ordre dossiers
grep "ENTITY_FOLDERS" entity_parser.py
# Doit contenir: ["id/gpe", "id/person", "id/org"]

# 2. Lancer import
python master_import.py --folders sources_md

# 3. Vérifier résultats
# Dans Neo4j Browser, exécuter tests ci-dessus
```

---

**FIN DOCUMENTATION ARCHITECTURE v2.1**