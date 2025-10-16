# 📄 Guide Requêtes Neo4j v3.2

**Version** : 3.2  
**Date** : 2025-10-11  
**Statut** : ✅ Production - Requêtes testées et validées

---

## 📋 TABLE DES MATIÈRES

1. [Vue d'Ensemble](#vue-densemble)
2. [Fondamentaux](#fondamentaux)
3. [Validation du Graphe](#validation-du-graphe)
4. [Analyses](#analyses)
5. [Recherche RAG](#recherche-rag)

---

## 🎯 Vue d'Ensemble

### Nœuds Principaux

```cypher
:Person          // 48 personnes
:Organization    // 29 organisations
:GPE             // 23 lieux géopolitiques

:ArchiveDocument // 55 documents sources
:Assertion       // 264 assertions

:Event           // 92 événements historiques
:MicroAction     // 202 communications diplomatiques

:Occupation, :Name, :Origin, :FamilyRelation, :ProfessionalRelation

:Chunk           // 325 chunks vectorisés (768D)
````

### Index Disponibles

```cypher
// Contraintes d'unicité
person_id, org_id, gpe_id, doc_id, event_id, micro_id, chunk_id

// Index de performance
person_name, org_name, event_date, micro_date
micro_actor, micro_recipient, event_victim
chunk_type

// Index vectoriel
chunk_embeddings (768D, cosine)
```

---

## ⚡ Fondamentaux

### Pattern 1 : Event → Person (Deux méthodes)

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

### Pattern 2 : MicroAction → Acteurs

```cypher
// Communications diplomatiques
MATCH (actor:Organization)-[:PERFORMED]->(m:MicroAction)-[:RECEIVED]->(recipient:Organization)
WHERE actor.prefLabel_fr = "Consulat Suisse Paris"
OPTIONAL MATCH (m)-[:CONCERNS]->(p:Person)
RETURN m.date_start, recipient.prefLabel_fr, p.prefLabel_fr, m.link_type
ORDER BY m.date_start;
```

### Pattern 3 : Provenance

```cypher
// Remonter à la source d'un événement
MATCH (e:Event {event_id: "/id/event/..."})
MATCH (a:Assertion)-[:CLAIMS]->(e)
MATCH (d:ArchiveDocument)-[:SUPPORTS]->(a)
RETURN d.cote, d.date_norm, a.source_quote, a.confidence;
```

### Pattern 4 : Person avec Structures Réifiées

```cypher
MATCH (p:Person {prefLabel_fr: "Müller Elisabeth"})

// Occupations
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

### ⚠️ Erreurs Courantes

#### Erreur 1 : Filtrer sur date_edtf

```cypher
// ❌ FAUX - date_edtf contient format EDTF étendu (1942/.., 1942~)
WHERE e.date_edtf >= date('1942-01-01')
// Erreur : "Cannot parse '1942/..' as a Date"

// ✅ CORRECT - Utiliser date_start (normalisé)
WHERE e.date_start >= date('1942-01-01')
```

#### Erreur 2 : Oublier les dates NULL

```cypher
// ❌ Exclut les événements sans date
WHERE e.date_start > date('1942-01-01')

// ✅ Gérer les NULL
WHERE e.date_start IS NULL OR e.date_start > date('1942-01-01')
```

#### Erreur 3 : Confondre types de chunks

```cypher
// ❌ Chercher documents dans entity_summary
MATCH (c:Chunk {chunk_type: 'entity_summary'})-[:CHUNK_OF]->(d:ArchiveDocument)

// ✅ Spécifier le bon type
MATCH (c:Chunk {chunk_type: 'quote_centered'})-[:CHUNK_OF]->(d:ArchiveDocument)
```

---

## ✅ Validation du Graphe

### Test 1 : Inventaire

```cypher
MATCH (n)
RETURN labels(n)[0] AS type, count(*) AS count
ORDER BY count DESC;
```

### Test 2 : Structures Réifiées

```cypher
MATCH (o:Occupation) RETURN count(o) AS occupations;
MATCH (n:Name) RETURN count(n) AS names;
MATCH (orig:Origin) RETURN count(orig) AS origins;
MATCH (fr:FamilyRelation) RETURN count(fr) AS family_rels;
MATCH (pr:ProfessionalRelation) RETURN count(pr) AS prof_rels;
```

### Test 3 : Relations Secondaires

```cypher
MATCH ()-[r:AT_ORGANIZATION]->() RETURN count(r);
MATCH ()-[r:AT_PLACE]->() RETURN count(r);
MATCH ()-[r:RELATES_TO]->() RETURN count(r);
MATCH ()-[r:IN_CONTEXT_OF]->() RETURN count(r);
```

### Test 4 : Relations Géographiques

```cypher
MATCH (o:Organization)-[:LOCATED_IN]->(g:GPE) 
RETURN o.prefLabel_fr, g.prefLabel_fr
LIMIT 10;
```

### Test 5 : WAS_VICTIM_OF

```cypher
MATCH (p:Person)-[:WAS_VICTIM_OF]->(e:Event)
RETURN p.prefLabel_fr, e.description
LIMIT 5;
```

### Test 6 : Relations PERFORMED/RECEIVED/CONCERNS

```cypher
MATCH ()-[r:PERFORMED]->() RETURN count(r) AS performed;
MATCH ()-[r:RECEIVED]->() RETURN count(r) AS received;
MATCH ()-[r:CONCERNS]->() RETURN count(r) AS concerns;
```

### Test 7 : Dates Normalisées

```cypher
// Tous les Events avec date_edtf doivent avoir date_start/date_end
MATCH (e:Event)
WHERE e.date_edtf IS NOT NULL
  AND (e.date_start IS NOT NULL OR e.date_end IS NOT NULL)
RETURN count(e) AS events_parsed;

MATCH (e:Event)
WHERE e.date_edtf IS NOT NULL
RETURN count(e) AS events_with_edtf;
```

### Test 8 : RAG Hybride

```cypher
// Distribution chunks
MATCH (c:Chunk)
RETURN c.chunk_type, count(*) AS count;
// quote_centered: 225, entity_summary: 100

// Embeddings valides
MATCH (c:Chunk)
WHERE c.embedding IS NOT NULL AND size(c.embedding) = 768
RETURN count(*);
// 325

// Relations DESCRIBES
MATCH ()-[r:DESCRIBES_EVENT]->() RETURN count(r);      // 75
MATCH ()-[r:DESCRIBES_ACTION]->() RETURN count(r);     // 150
MATCH ()-[r:DESCRIBES_ENTITY]->() RETURN count(r);     // 100
MATCH ()-[r:MENTIONS]->() RETURN count(r);             // 1072
```

---

## 📊 Analyses

### Timeline Enrichie

```cypher
// Parcours complet avec contexte
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
  occ.position_title AS fonction,
  a.source_quote AS citation,
  d.cote AS document

ORDER BY e.date_start;
```

### Gaps Temporels

```cypher
// Identifier périodes sans information
MATCH (p:Person {prefLabel_fr: "Müller Elisabeth"})
MATCH (p)-[:WAS_VICTIM_OF]->(e:Event)
WHERE e.date_start IS NOT NULL

WITH e
ORDER BY e.date_start

WITH collect({
  date: e.date_start,
  tags: e.tags
}) AS events

UNWIND range(0, size(events)-2) AS i

WITH 
  events[i].date AS date1,
  events[i+1].date AS date2,
  events[i].tags AS tags1,
  events[i+1].tags AS tags2

WITH 
  date1, date2, tags1, tags2,
  duration.inDays(date(date1), date(date2)).days AS gap_days

WHERE gap_days > 30

RETURN 
  date1 AS date_debut_gap,
  date2 AS date_fin_gap,
  gap_days AS jours_sans_info,
  tags1 AS dernier_evenement_avant,
  tags2 AS premier_evenement_apres
  
ORDER BY gap_days DESC;
```

### Chaînes de Communication

```cypher
// Suivre une communication de bout en bout
MATCH (start:MicroAction)
WHERE NOT ()-[:NEXT_IN_COMMUNICATION_CHAIN]->(start)
  AND (start)-[:CONCERNS]->(:Person {prefLabel_fr: "Müller Elisabeth"})

MATCH path = (start)-[:NEXT_IN_COMMUNICATION_CHAIN*]->(end)
WHERE NOT (end)-[:NEXT_IN_COMMUNICATION_CHAIN]->()

RETURN [n IN nodes(path) | {
  date: n.date_start,
  actor: n.actor_id,
  recipient: n.recipient_id,
  type: n.link_type
}] AS chain_sequence
ORDER BY length(path) DESC
LIMIT 1;
```

### Réactivité Diplomatique

```cypher
// Délai événement → première action
MATCH (p:Person {prefLabel_fr: "Müller Elisabeth"})
MATCH (p)-[:WAS_VICTIM_OF]->(e:Event)
WHERE e.date_start IS NOT NULL

OPTIONAL MATCH (m:MicroAction)-[:CONCERNS]->(p)
WHERE m.date_start IS NOT NULL
  AND m.date_start >= e.date_start

WITH e, m
ORDER BY m.date_start
WITH e, collect(m)[0] AS premiere_action

WHERE premiere_action IS NOT NULL

WITH e, premiere_action,
     duration.inDays(date(e.date_start), date(premiere_action.date_start)).days AS delai

RETURN 
  e.date_start AS date_evenement,
  e.tags AS type_evenement,
  premiere_action.date_start AS date_premiere_reaction,
  delai AS jours_delai,
  CASE 
    WHEN delai = 0 THEN '⚡ Immédiat'
    WHEN delai <= 7 THEN '🏃 Rapide'
    WHEN delai <= 30 THEN '📅 Normal'
    ELSE '🦥 Lent'
  END AS categorie

ORDER BY delai;
```

### Réseau de Communication

```cypher
// Qui communique avec qui
MATCH (source:Organization)-[:PERFORMED]->(m:MicroAction)-[:RECEIVED]->(target:Organization)

RETURN DISTINCT
  source.prefLabel_fr AS de,
  target.prefLabel_fr AS vers,
  count(m) AS nb_messages
ORDER BY nb_messages DESC
LIMIT 15;
```

### Distribution Temporelle

```cypher
// Chronologie du corpus
MATCH (e:Event)
WHERE e.date_start IS NOT NULL

WITH date(e.date_start).year AS annee,
     date(e.date_start).month AS mois,
     count(e) AS nb_events

RETURN 
  annee,
  mois,
  toString(annee) + '-' + 
    CASE WHEN mois < 10 THEN '0' + toString(mois) 
         ELSE toString(mois) END AS periode,
  nb_events

ORDER BY annee, mois;
```

---

## 🔍 Recherche RAG

### Recherche par Mots-Clés (Documents)

```cypher
// "Où était détenue Müller ?"
MATCH (c:Chunk {chunk_type: 'quote_centered'})
WHERE toLower(c.text) CONTAINS "détenue" 
   OR toLower(c.text) CONTAINS "zuchthaus"

OPTIONAL MATCH (c)-[:DESCRIBES_EVENT]->(e:Event)
WHERE e.tags CONTAINS "detention"

OPTIONAL MATCH (p:Person)-[:WAS_VICTIM_OF]->(e)

OPTIONAL MATCH (lieu:GPE)
WHERE e.place_id = lieu.id

RETURN 
  LEFT(c.text, 200) AS passage,
  e.date_start AS date,
  lieu.prefLabel_fr AS lieu,
  e.tags AS type,
  p.prefLabel_fr AS personne

ORDER BY e.date_start
LIMIT 5;
```

### Recherche Biographique (Entités)

```cypher
// "Qui est Elisabeth Müller ?"
MATCH (c:Chunk {chunk_type: 'entity_summary'})-[:DESCRIBES_ENTITY]->(p:Person)
WHERE p.prefLabel_fr = "Müller Elisabeth"

// Événements clés
OPTIONAL MATCH (p)-[:WAS_VICTIM_OF]->(e:Event)
WHERE e.date_start IS NOT NULL

WITH p, c, e
ORDER BY e.date_start

WITH p, c, collect({
  date: e.date_start,
  type: e.tags,
  description: e.description
})[0..5] AS principaux_evenements

RETURN {
  biographie: c.text,
  identite: {
    nom: p.prefLabel_fr,
    aliases: p.aliases,
    status: p.status
  },
  chronologie: principaux_evenements,
  longueur: c.char_count
} AS profile_complet;
```

### Recherche Vectorielle (Production)

```cypher
// Avec embedding réel (768D) depuis Ollama
CALL db.index.vector.queryNodes(
  'chunk_embeddings',
  10,
  $query_embedding  // Vector 768D depuis Ollama
)
YIELD node AS chunk, score
WHERE score >= 0.7

// Documents
OPTIONAL MATCH (chunk {chunk_type: 'quote_centered'})-[:DESCRIBES_EVENT]->(e:Event)
OPTIONAL MATCH (p_doc:Person)-[:WAS_VICTIM_OF]->(e)
OPTIONAL MATCH (lieu:GPE) WHERE e.place_id = lieu.id

// Entités
OPTIONAL MATCH (chunk {chunk_type: 'entity_summary'})-[:DESCRIBES_ENTITY]->(entity)

RETURN 
  chunk.text, 
  chunk.chunk_type, 
  e.date_start, 
  lieu.prefLabel_fr, 
  entity.prefLabel_fr,
  score
ORDER BY score DESC
LIMIT 5;
```

**Génération embedding** :

```bash
curl -X POST http://localhost:11434/api/embeddings \
  -H "Content-Type: application/json" \
  -d '{"model": "nomic-embed-text", "prompt": "Où était détenue Müller?"}'
```

### Enrichissement Contextuel

```cypher
// Partir d'un chunk → explorer le graphe
MATCH (c:Chunk {chunk_type: 'quote_centered'})-[:DESCRIBES_EVENT]->(e:Event)
WHERE e.tags CONTAINS "detention"

WITH e, c
ORDER BY e.date_start
LIMIT 1

// Toute la timeline de la personne
MATCH (p:Person)-[:WAS_VICTIM_OF]->(e)
MATCH (p)-[:WAS_VICTIM_OF]->(other:Event)
WHERE other.date_start IS NOT NULL

OPTIONAL MATCH (a:Assertion)-[:CLAIMS]->(other)

WITH c, p, other, a
ORDER BY other.date_start

WITH c, p, collect({
  date: other.date_start,
  type: other.tags,
  description: other.description,
  citation: LEFT(a.source_quote, 80)
}) AS timeline

RETURN 
  LEFT(c.text, 150) AS chunk_initial,
  p.prefLabel_fr AS personne,
  timeline;
```

---

## 🎓 Bonnes Pratiques

### Dates

- ✅ Toujours filtrer sur `date_start` / `date_end` (normalisé)
- ❌ Jamais filtrer sur `date_edtf` (format EDTF étendu)

### Relations Event ↔ Person

- ✅ `WAS_VICTIM_OF` (relation) et `victim_id` (propriété) existent tous deux
- ✅ Les deux méthodes sont valides

### Structures Réifiées

- ✅ Existent : Occupation, Name, Origin, FamilyRelation, ProfessionalRelation
- ✅ Relations secondaires : AT_ORGANIZATION, AT_PLACE, RELATES_TO, IN_CONTEXT_OF

### RAG

- ✅ `quote_centered` : documents (225 chunks)
- ✅ `entity_summary` : entités (100 chunks)
- ✅ Distinguer les deux types dans les requêtes

### NULL

- ✅ Toujours gérer les valeurs NULL dans les filtres
- ✅ Utiliser `OPTIONAL MATCH` pour relations non garanties

---

**FIN GUIDE REQUÊTES v3.2**
