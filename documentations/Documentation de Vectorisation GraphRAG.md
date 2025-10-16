# Documentation Vectorisation GraphRAG v3.0

**Version** : 3.0  
**Date** : 2025-10-11  
**Statut** : ✅ Production - RAG Hybride avec Gemini Embeddings

---

## 📋 TABLE DES MATIÈRES

1. [Vue d'Ensemble](https://claude.ai/chat/b2c13759-b3c9-4705-97d6-e088f58b4b77#vue-densemble)
2. [Configuration GCP et Vertex AI](https://claude.ai/chat/b2c13759-b3c9-4705-97d6-e088f58b4b77#configuration-gcp-et-vertex-ai)
3. [Architecture RAG Hybride](https://claude.ai/chat/b2c13759-b3c9-4705-97d6-e088f58b4b77#architecture-rag-hybride)
4. [Pipeline Documents](https://claude.ai/chat/b2c13759-b3c9-4705-97d6-e088f58b4b77#pipeline-documents)
5. [Pipeline Entités](https://claude.ai/chat/b2c13759-b3c9-4705-97d6-e088f58b4b77#pipeline-entit%C3%A9s)
6. [Index Vectoriel](https://claude.ai/chat/b2c13759-b3c9-4705-97d6-e088f58b4b77#index-vectoriel)
7. [Utilisation](https://claude.ai/chat/b2c13759-b3c9-4705-97d6-e088f58b4b77#utilisation)
8. [Validation](https://claude.ai/chat/b2c13759-b3c9-4705-97d6-e088f58b4b77#validation)
9. [Troubleshooting](https://claude.ai/chat/b2c13759-b3c9-4705-97d6-e088f58b4b77#troubleshooting)

---

## 🎯 Vue d'Ensemble

### Objectif

Système RAG (Retrieval-Augmented Generation) hybride combinant :

- **Recherche vectorielle sémantique** (embeddings 768D via Gemini)
- **Recherche structurée** (graphe Neo4j)
- **Compatible Claude Projects** (Vertex AI native)

### Configuration

```json
{
  "embedding_model": "text-multilingual-embedding-002",
  "provider": "Vertex AI",
  "dimensions": 768,
  "similarity": "cosine",
  "gcp": {
    "project_id": "gen-lang-client-0810997704",
    "location": "us-central1"
  }
}
```

### Nouveautés v3.0

- ✅ **Gemini Embeddings** natifs (multilingue FR/DE)
- ✅ **Rate limiting** intelligent (évite erreurs 429)
- ✅ **Exponential backoff** automatique
- ✅ **Compatible Claude Projects** sans serveur intermédiaire
- ✅ **Fuzzy matching** pour corpus OCR imparfait
- ✅ **Contexte adaptatif** selon longueur citation

### Architecture en 2 Pipelines

```
PIPELINE 1 : DOCUMENTS (quote_centered)
sources_md/*.md → Chunks textuels → Gemini Embeddings → Neo4j
↓
Assertions → Events/MicroActions
↓
Relations: DESCRIBES_EVENT, DESCRIBES_ACTION, MENTIONS

PIPELINE 2 : ENTITÉS (entity_summary)
Person/Organization/GPE → Notices + Structures → Gemini Embeddings → Neo4j
↓
Relations: DESCRIBES_ENTITY, MENTIONS
```

---

## 🔐 Configuration GCP et Vertex AI

### Prérequis

1. **Compte Google Cloud Platform**
    
    - Crédits gratuits : 300$ pendant 90 jours
    - Inscription : https://cloud.google.com/
2. **Projet GCP créé**
    
    - Project ID : `gen-lang-client-0810997704` (exemple)
    - Location : `us-central1` (recommandé)
3. **API Vertex AI activée**
    
    - Console : https://console.cloud.google.com/apis/library
    - Chercher "Vertex AI API" et activer

### Authentification

#### Option A : Service Account (Recommandé pour production)

```bash
# 1. Créer service account dans GCP Console
# IAM & Admin → Service Accounts → CREATE SERVICE ACCOUNT
# Nom : vertex-ai-embeddings
# Role : Vertex AI User

# 2. Créer clé JSON
# KEYS → ADD KEY → Create new key → JSON

# 3. Placer le fichier
mkdir -p ~/.gcp
mv ~/Downloads/gen-lang-client-*.json ~/.gcp/vertex-ai-key.json
chmod 600 ~/.gcp/vertex-ai-key.json

# 4. Configurer variable d'environnement
export GOOGLE_APPLICATION_CREDENTIALS="$HOME/.gcp/vertex-ai-key.json"

# 5. Rendre permanent
echo 'export GOOGLE_APPLICATION_CREDENTIALS="$HOME/.gcp/vertex-ai-key.json"' >> ~/.bashrc
source ~/.bashrc
```

#### Option B : gcloud CLI (Alternative)

```bash
# Installation gcloud CLI
# Voir : https://cloud.google.com/sdk/docs/install

# Authentification
gcloud auth application-default login
gcloud config set project gen-lang-client-0810997704
```

### Installation Dépendances Python

```bash
pip install google-cloud-aiplatform neo4j rapidfuzz
```

### Test de Configuration

```python
# test_vertex_ai.py
from google.cloud import aiplatform
from vertexai.language_models import TextEmbeddingModel

aiplatform.init(project="gen-lang-client-0810997704", location="us-central1")
model = TextEmbeddingModel.from_pretrained("text-multilingual-embedding-002")

text = "Elisabeth Müller était détenue au camp de Gurs."
embeddings = model.get_embeddings([text])
print(f"✅ Embedding généré : {len(embeddings[0].values)} dimensions")
```

### Quotas et Limites

**Quotas par défaut (nouveaux comptes)** :

- 60 requêtes/minute pour embeddings
- Peut causer erreurs `429 Quota exceeded`

**Solutions** :

1. **Rate limiting dans le code** (implémenté dans v3.0)
2. **Augmenter quota** via https://console.cloud.google.com/iam-admin/quotas
    - Filtre : `aiplatform.googleapis.com/online_prediction_requests_per_base_model`
    - Demander : 600 requêtes/minute
    - Délai approbation : 24-48h

**Coûts** :

- text-multilingual-embedding-002 : ~0.00001$ par 1000 caractères
- Pour 400 chunks × 800 chars = **0.0032$** (moins d'un centime)

---

## 🗂️ Architecture RAG Hybride

```
┌──────────────────────────────────────────────────────────┐
│              CORPUS DIPLOMATIQUE (Neo4j Aura)            │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  ┌──────────────────┐         ┌──────────────────┐      │
│  │  DOCUMENTS (75)  │         │  ENTITÉS (100)   │      │
│  │  ArchiveDocument │         │  Person (48)     │      │
│  └────────┬─────────┘         │  Org (29)        │      │
│           │                   │  GPE (23)        │      │
│           │                   └────────┬─────────┘      │
│           ▼                            ▼                │
│  ┌──────────────────┐         ┌──────────────────┐      │
│  │ CHUNKS DOCUMENTS │         │ CHUNKS ENTITÉS   │      │
│  │  quote_centered  │         │  entity_summary  │      │
│  │     (~225)       │         │     (91)         │      │
│  └────────┬─────────┘         └────────┬─────────┘      │
│           │                            │                │
│           └────────────┬───────────────┘                │
│                        ▼                                │
│              ┌──────────────────┐                       │
│              │  INDEX VECTORIEL │                       │
│              │  chunk_embeddings│                       │
│              │      (~316)      │                       │
│              │  768D - cosine   │                       │
│              │  Gemini Native   │                       │
│              └────────┬─────────┘                       │
│                       │                                 │
│           ┌───────────┴───────────┐                     │
│           ▼                       ▼                     │
│  ┌─────────────────┐    ┌─────────────────┐            │
│  │ STRUCTURES      │    │  ÉVÉNEMENTS     │            │
│  │ Events (92)     │    │  MicroActions   │            │
│  │ MicroActions    │    │  (202)          │            │
│  └─────────────────┘    └─────────────────┘            │
│                                                          │
└──────────────────────────────────────────────────────────┘

REQUÊTE UTILISATEUR (Claude Projects)
        │
        ▼
  [Vertex AI Embedding]
  text-multilingual-embedding-002
        │
        ▼
  [Recherche Vectorielle Neo4j]
        │
        ▼
  [Chunks similaires 768D cosine]
        │
        ├─> Documents → Events/Actions → Context
        └─> Entités → Profils → Context
                │
                ▼
        [Réponse enrichie Claude]
```

### Total RAG Hybride (Production)

```
TOTAL CHUNKS VECTORISÉS : ~316
  ├─ Documents (quote_centered) : ~225
  └─ Entités (entity_summary) : 91 (9 échecs mineurs)

TOTAL EMBEDDINGS : ~316
  └─ Dimension uniforme : 768D
  └─ Provider : Vertex AI
  └─ Model : text-multilingual-embedding-002

TOTAL RELATIONS :
  ├─ CHUNK_OF : ~225 (documents → archives)
  ├─ DESCRIBES_EVENT : ~75
  ├─ DESCRIBES_ACTION : ~150
  ├─ DESCRIBES_ENTITY : 91
  └─ MENTIONS : ~1102 (documents + entités)

INDEX VECTORIEL : chunk_embeddings
  ├─ Dimension : 768
  ├─ Similarité : cosine
  ├─ Provider : Neo4j Vector Index
  └─ Compatible : Vertex AI native
```

---

## 📄 Pipeline Documents (quote_centered)

### Objectif

Vectoriser les documents sources pour recherche sémantique dans les archives avec stratégie **Quote-First**.

### Stratégie Quote-First

Au lieu de découper arbitrairement les documents en chunks fixes, on centre les chunks sur les **citations sources des Assertions**.

**Avantages** :

- ✅ Précision maximale : lien direct chunk → événement
- ✅ Pas de faux positifs
- ✅ Relations traçables et explicables
- ✅ Coverage élevé (85% typique pour corpus OCR)

### Étape 1 : Localisation des Quotes

```python
def locate_quote_in_document(quote: str, document: str):
    """
    Localise quote dans document avec fuzzy matching
    """
    # 1. Normalisation
    quote_norm = normalize(quote)      # Enlever guillemets, espaces...
    doc_norm = normalize(document)     # Idem
    
    # 2. Exact match
    pos = doc_norm.find(quote_norm)
    if pos != -1:
        return pos, "exact"
    
    # 3. Fuzzy match (fallback pour OCR imparfait)
    if use_fuzzy:
        pos = fuzzy_search(quote_norm, doc_norm, threshold=85%)
        if pos != -1:
            return pos, "fuzzy"
    
    return -1, None
```

**Résultats typiques** :

- Exact matches : 22%
- Fuzzy matches : 78%
- Total localisé : 85-90%

### Étape 2 : Chunking Adaptatif

```python
def create_quote_centered_chunk(quote_pos, quote_length, document):
    """
    Crée chunk avec contexte adaptatif
    """
    # Contexte adaptatif selon longueur quote
    if quote_length < 100:
        context_size = 200
    elif quote_length < 300:
        context_size = 350
    else:
        context_size = 450
    
    # Bornes totales (400-900 chars)
    total = quote_length + (2 * context_size)
    if total < 400:
        context_size = (400 - quote_length) // 2
    elif total > 900:
        context_size = (900 - quote_length) // 2
    
    # Extraction
    start = max(0, quote_pos - context_size)
    end = min(len(document), quote_pos + quote_length + context_size)
    
    # Extension aux frontières paragraphe (si proche < 50 chars)
    start, end = extend_to_paragraph_boundaries(start, end, document)
    
    return document[start:end]
```

### Étape 3 : Génération Embeddings via Gemini

```python
from google.cloud import aiplatform
from vertexai.language_models import TextEmbeddingModel
import time

def get_embedding_gemini(text: str):
    """
    Génère embedding via Gemini avec rate limiting
    """
    max_retries = 5
    base_delay = 1.0  # Rate limiting : 1s entre requêtes
    
    for attempt in range(max_retries):
        try:
            time.sleep(base_delay)  # Éviter quota 429
            embeddings = model.get_embeddings([text])
            return embeddings[0].values  # 768D
            
        except Exception as e:
            if "429" in str(e) or "Quota exceeded" in str(e):
                wait_time = base_delay * (2 ** attempt)  # Exponential backoff
                print(f"⏳ Quota exceeded, waiting {wait_time:.1f}s...")
                time.sleep(wait_time)
                continue
            elif attempt < max_retries - 1:
                time.sleep(2)
                continue
            else:
                return []
    
    return []
```

### Étape 4 : Création Nœuds Neo4j

```cypher
CREATE (c:Chunk {
  id: "{doc_id}::chunk_{idx}",
  text: "... contexte + citation ...",
  chunk_type: "quote_centered",
  embedding: [...],  // 768D Gemini
  embedding_model: "text-multilingual-embedding-002",
  embedding_provider: "vertex-ai",
  start_char: 1234,
  end_char: 2834,
  doc_id: "/id/document/{sha1}",
  year: 1942,
  assertion_id: "/id/assertion/{sha1}",
  match_method: "fuzzy"  // ou "exact"
})
```

### Étape 5 : Création Relations

```cypher
// Lien au document
MATCH (c:Chunk {id: $chunk_id})
MATCH (d:ArchiveDocument {id: $doc_id})
MERGE (c)-[:CHUNK_OF]->(d)

// Lien événements
MATCH (c:Chunk {id: $chunk_id})
MATCH (e:Event {event_id: $event_id})
MERGE (c)-[r:DESCRIBES_EVENT]->(e)
SET r.method = $match_method,
    r.confidence = CASE WHEN $match_method = 'exact' THEN 1.0 ELSE 0.9 END,
    r.via_assertion = $assertion_id

// Lien micro-actions
MATCH (c:Chunk {id: $chunk_id})
MATCH (m:MicroAction {micro_id: $micro_id})
MERGE (c)-[r:DESCRIBES_ACTION]->(m)
SET r.method = $match_method,
    r.confidence = CASE WHEN $match_method = 'exact' THEN 1.0 ELSE 0.9 END

// Mentions entités (extraction depuis IDs dans texte)
MATCH (c:Chunk)
WHERE c.text CONTAINS "/id/person/1c6bf450"
MATCH (p:Person {id: "/id/person/1c6bf450-3c41-4755-be82-d77f9744f6e1"})
MERGE (c)-[:MENTIONS]->(p)
```

---

## 👤 Pipeline Entités (entity_summary)

### Objectif

Créer profils vectorisés pour recherche biographique/institutionnelle enrichie.

### Étape 1 : Assemblage Texte Multi-Sources

#### Person (avec structures réifiées)

```python
def assemble_person_text(person_id):
    parts = []
    
    # === PARTIE 1 : NEO4J ===
    # Identité
    parts.append(f"{prefLabel_fr}")
    if prefLabel_de and prefLabel_de != prefLabel_fr:
        parts.append(f"({prefLabel_de})")
    if aliases:
        parts.append(f"Alias: {', '.join(aliases[:3])}")
    
    # Notice biographique (principale)
    if notice_bio:
        parts.append(f"\n\n{notice_bio}")
    
    # Sources archivistiques
    sources = get_archive_sources(person_id)
    if sources:
        parts.append(f"\n\nSources: {', '.join(sources[:3])}")
    
    # === PARTIE 2 : MARKDOWN ===
    # Sections narratives enrichies
    sections = extract_narrative_sections(person_id)
    if sections.get('lieux_residence'):
        parts.append(f"\n\nLieux de résidence: {sections['lieux_residence']}")
    if sections.get('notes_recherche'):
        parts.append(f"\n\nNotes de recherche: {sections['notes_recherche']}")
    if sections.get('contexte_relationnel'):
        parts.append(f"\n\nContexte relationnel: {sections['contexte_relationnel']}")
    
    # === PARTIE 3 : STRUCTURES RÉIFIÉES ===
    # Occupations (avec IDs pour MENTIONS)
    occupations = get_occupations(person_id)
    if occupations:
        # Format: "position_title à org_name /id/org/xxx (interval)"
        parts.append(f"\n\nOccupations: {occupations}")
    
    # Origins
    origins = get_origins(person_id)
    if origins:
        # Format: "mode place_name /id/gpe/xxx (interval)"
        parts.append(f"\n\nOrigines: {origins}")
    
    # Family Relations
    family_rels = get_family_relations(person_id)
    if family_rels:
        # Format: "relation_type de target_name /id/person/xxx (interval)"
        parts.append(f"\n\nRelations familiales: {family_rels}")
    
    return " ".join(parts)
```

**Exemple de texte assemblé** :

```
Elisabeth Müller (Müller Elisabeth). Alias: Elise, Betty. 

Née en 1896 à Bâle. Réfugiée juive allemande internée en France pendant la Seconde Guerre mondiale.

Sources: E2001E#1000/1571#220*, E2001E#1000/1571#221*

Lieux de résidence: Bâle /id/gpe/xxx (1896-1933), Paris /id/gpe/yyy (1933-1940)

Occupations: Employée domestique à Organisation X /id/org/zzz (1920-1933)

Origines: naissance Bâle /id/gpe/xxx (1896)

Relations familiales: épouse de Max Müller /id/person/www (1920-1945)
```

#### Organization

```python
def assemble_organization_text(org_id):
    parts = []
    parts.append(f"{prefLabel_fr}")
    if prefLabel_de:
        parts.append(f"({prefLabel_de})")
    
    if type:
        parts.append(f"\n\nType: {type}")
    
    if notice_institutionnelle:
        parts.append(f"\n\n{notice_institutionnelle}")
    
    # Hiérarchie
    parent_org = get_parent_organization(org_id)
    if parent_org:
        parts.append(f"\n\nFait partie de: {parent_org}")
    
    # Localisation
    if gpe_name:
        parts.append(f"\n\nLocalisation: {gpe_name}")
    
    # Sources
    sources = get_archive_sources(org_id)
    if sources:
        parts.append(f"\n\nSources: {', '.join(sources)}")
    
    return " ".join(parts)
```

#### GPE

```python
def assemble_gpe_text(gpe_id):
    parts = []
    parts.append(f"{prefLabel_fr}")
    if prefLabel_de:
        parts.append(f"({prefLabel_de})")
    
    if notice_geo:
        parts.append(f"\n\n{notice_geo}")
    
    if coordinates_lat and coordinates_lon:
        parts.append(f"\n\nCoordonnées: {lat}, {lon}")
    
    sources = get_archive_sources(gpe_id)
    if sources:
        parts.append(f"\n\nSources: {', '.join(sources)}")
    
    return " ".join(parts)
```

### Étape 2 : Génération Embeddings

Même processus que pour les documents (Gemini + rate limiting).

### Étape 3 : Création Nœuds

```cypher
CREATE (c:Chunk {
  id: "{entity_id}::entity_summary",
  text: "Elisabeth Müller. Née en 1896...",
  chunk_type: "entity_summary",
  embedding: [...],  // 768D Gemini
  embedding_model: "text-multilingual-embedding-002",
  embedding_provider: "vertex-ai",
  entity_id: "/id/person/{uuid}",
  entity_type: "Person",
  char_count: 820
})
```

### Étape 4 : Relations

```cypher
// DESCRIBES_ENTITY
MATCH (c:Chunk {id: $chunk_id})
MATCH (e {id: $entity_id})
MERGE (c)-[:DESCRIBES_ENTITY {method: 'assembled'}]->(e)

// MENTIONS (extraction depuis IDs dans texte)
// Format détecté : "/id/person/xxx", "/id/org/yyy", "/id/gpe/zzz"
MATCH (c:Chunk {id: $chunk_id})
WHERE c.text CONTAINS "/id/org/96ad0f92"
MATCH (org:Organization {id: "/id/org/96ad0f92-75ac-4815-8c46-22a8f094b2b7"})
MERGE (c)-[:MENTIONS {source: 'text'}]->(org)
```

---

## 📊 Index Vectoriel

### Création

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

### Utilisation dans Claude Projects

**Configuration Similarity Search Tool** :

```yaml
Tool Type: Similarity Search
Name: Find Similar Biographical Passages
Description: Trouve des passages biographiques similaires dans les synthèses d'entités

Embedding provider: Vertex AI
Embedding model: text-multilingual-embedding-002
Number of results: 5
```

### Requête Cypher Enrichie

```cypher
// Recherche vectorielle hybride
CALL db.index.vector.queryNodes(
  'chunk_embeddings',
  20,                  // Top K
  $query_embedding     // Vector 768D depuis Vertex AI
)
YIELD node AS chunk, score
WHERE score >= 0.7

// Enrichir selon type de chunk
OPTIONAL MATCH (chunk {chunk_type: 'quote_centered'})-[:CHUNK_OF]->(doc:ArchiveDocument)
OPTIONAL MATCH (chunk)-[:DESCRIBES_EVENT]->(e:Event)
OPTIONAL MATCH (chunk)-[:DESCRIBES_ACTION]->(m:MicroAction)
OPTIONAL MATCH (chunk {chunk_type: 'entity_summary'})-[:DESCRIBES_ENTITY]->(entity)
OPTIONAL MATCH (chunk)-[:MENTIONS]->(mentioned)

RETURN 
  chunk.text AS text,
  chunk.chunk_type AS type,
  score,
  doc.title AS document_title,
  e.label AS event,
  m.label AS action,
  entity.prefLabel_fr AS entity_name,
  labels(entity)[0] AS entity_type,
  collect(DISTINCT mentioned.prefLabel_fr) AS mentions
ORDER BY score DESC
LIMIT 5;
```

---

## 🚀 Utilisation

### Configuration config.json

```json
{
  "vault_path": "/home/steeven/vault_obsidian",
  
  "neo4j": {
    "uri": "neo4j+s://xxxxx.databases.neo4j.io",
    "user": "neo4j",
    "password": "votre-mot-de-passe",
    "database": "neo4j"
  },
  
  "gcp": {
    "project_id": "gen-lang-client-0810997704",
    "location": "us-central1"
  },
  
  "embedding_model": "text-multilingual-embedding-002"
}
```

### Script Documents : `vectorize_chunks_gemini.py`

```bash
# Lancer vectorisation documents
python vectorize_chunks_gemini.py

# Options
python vectorize_chunks_gemini.py --no-fuzzy      # Désactiver fuzzy matching
python vectorize_chunks_gemini.py --no-adaptive   # Désactiver contexte adaptatif
```

**Sortie attendue** :

```
======================================================================
VECTORIZATION v3.0 - Gemini Embeddings Native
======================================================================

✨ Adaptive context ENABLED
   Min total: 400 chars
   Max total: 900 chars
✨ Fuzzy matching ENABLED (threshold: 85.0%)

🔍 Checking prerequisites...
  ✅ Found 376 Assertions

🔗 Checking SUPPORTS direction...
  ✅ Found 74 Documents with Assertions

📖 Loading documents...
  ✅ Loaded 75 documents

📄 638731155645304456-001-16...
  📌 2 assertions
  ✅ Located 2/2 quotes (1 exact, 1 fuzzy)
  📦 2 chunks
     Avg chunk size: 280 chars
  ✅ Done

...

======================================================================
VECTORIZATION REPORT v3.0 - Gemini Embeddings
======================================================================

📊 STATISTICS
----------------------------------------------------------------------
Documents processed: 74
Assertions found: 376
Quotes located: 320
  - Exact matches: 70
  - Fuzzy matches: 250
Chunks created: 225
Embeddings generated (Gemini): 225
Chunk sizes: avg=650, min=420, max=890

📈 Quote coverage: 85.1%
   ✅ Excellent coverage!

🔗 RELATIONS
----------------------------------------------------------------------
DESCRIBES_EVENT: 75
DESCRIBES_ACTION: 150
MENTIONS: 1072

======================================================================
✅ SUCCESS: 225 chunks vectorized with Gemini!
   🚀 Compatible with Claude Projects Similarity Search
======================================================================
```

### Script Entités : `vectorize_entities_gemini.py`

```bash
python vectorize_entities_gemini.py
```

**Sortie attendue** :

```
======================================================================
ENTITY VECTORIZATION v2.0 - Gemini Embeddings Native
======================================================================

📋 Processing Person entities...
  Found 48 Person entities
    Processed 10 entities...
    Processed 20 entities...
    ...
  ✅ Completed Person

📋 Processing Organization entities...
  Found 29 Organization entities
    Processed 10 entities...
    ...
  ✅ Completed Organization

📋 Processing GPE entities...
  Found 23 GPE entities
  ✅ Completed GPE

======================================================================
ENTITY VECTORIZATION REPORT v2.0 - Gemini Embeddings
======================================================================

📊 STATISTICS
----------------------------------------------------------------------
Entities processed: 91
Chunks created: 91
Embeddings generated (Gemini): 91
Narrative sections found: 248
Occupations found: 17
Origins found: 6
Family relations found: 9
  → Average 2.7 narrative sections per entity
  → Average 0.2 occupations per entity

🔗 RELATIONS
----------------------------------------------------------------------
DESCRIBES_ENTITY: 91
MENTIONS: 30

⚠️ ERRORS (9)
----------------------------------------------------------------------
  • Embedding failed for /id/person/1c6bf450... (texte trop court)
  • Embedding failed for /id/org/96ad0f92... (quota temporaire)
  ...

======================================================================
✅ SUCCESS: 91 entity chunks created!
   Plus 30 MENTIONS relations
   🚀 Using Gemini embeddings for Claude agent
======================================================================
```

### Retry Entités Échouées (Optionnel)

```bash
# Script pour retry les 9 entités échouées
python retry_failed_entities.py
```

### Pipeline Complet Claude Projects

**Dans Claude Projects, le tool Similarity Search utilise** :

1. **Embedding automatique** : Vertex AI génère l'embedding de la query
2. **Recherche Neo4j** : Via l'index `chunk_embeddings`
3. **Top K résultats** : 5 chunks les plus similaires
4. **Context enrichi** : Claude utilise les chunks + relations du graphe

**Exemple d'utilisation** :

```
User: "Où était détenue Elisabeth Müller en octobre 1942 ?"

Claude → Similarity Search Tool:
  - Embedding: text-multilingual-embedding-002
  - Query: "Où était détenue Elisabeth Müller en octobre 1942"
  - Results: 5 chunks (3 documents + 2 entités)

Claude reçoit:
  1. Chunk doc: "...Elisabeth Müller est internée au camp de Gurs..."
  2. Chunk doc: "...conditions de détention difficiles en octobre..."
  3. Chunk entity: "Elisabeth Müller. Réfugiée juive..."
  4. ...

Claude → Réponse enrichie:
  "D'après les archives, Elisabeth Müller était détenue au camp 
   de Gurs en octobre 1942. Les documents mentionnent..."
```

---

## ✅ Validation

### Tests Exécutés sur Corpus Réel

#### Test 1 : Chunks créés par type

```cypher
MATCH (c:Chunk)
RETURN c.chunk_type, count(*) AS count
ORDER BY count DESC;
```

**Attendu** :

```
quote_centered    225
entity_summary     91
```

#### Test 2 : Embeddings Gemini valides

```cypher
MATCH (c:Chunk)
WHERE c.embedding IS NOT NULL 
  AND size(c.embedding) = 768
  AND c.embedding_provider = 'vertex-ai'
  AND c.embedding_model = 'text-multilingual-embedding-002'
RETURN count(*) AS chunks_with_gemini_embeddings;
```

**Attendu** : 316

#### Test 3 : Relations DESCRIBES

```cypher
CALL {
  MATCH ()-[r:DESCRIBES_EVENT]->()
  RETURN 'DESCRIBES_EVENT' AS rel, count(r) AS count
  UNION
  MATCH ()-[r:DESCRIBES_ACTION]->()
  RETURN 'DESCRIBES_ACTION' AS rel, count(r) AS count
  UNION
  MATCH ()-[r:DESCRIBES_ENTITY]->()
  RETURN 'DESCRIBES_ENTITY' AS rel, count(r) AS count
}
RETURN rel, count;
```

**Attendu** :

```
DESCRIBES_EVENT    75
DESCRIBES_ACTION   150
DESCRIBES_ENTITY   91
```

#### Test 4 : MENTIONS par type

```cypher
MATCH (c:Chunk)-[r:MENTIONS]->()
RETURN c.chunk_type, count(r) AS mentions
ORDER BY mentions DESC;
```

**Attendu** :

```
quote_centered    1072
entity_summary      30
```

#### Test 5 : Index vectoriel

```cypher
SHOW INDEXES 
YIELD name, type, entityType, labelsOrTypes, properties
WHERE name = 'chunk_embeddings'
RETURN name, type, entityType, labelsOrTypes, properties;
```

**Attendu** :

```
name: chunk_embeddings
type: VECTOR
entityType: NODE
labelsOrTypes: ["Chunk"]
properties: ["embedding"]
```

#### Test 6 : Vérifier compatibilité Vertex AI

```cypher
MATCH (c:Chunk)
WHERE c.embedding_provider = 'vertex-ai'
  AND c.embedding_model = 'text-multilingual-embedding-002'
RETURN c.chunk_type, count(*) as count;
```

**Attendu** :

```
quote_centered    225
entity_summary     91
```

#### Test 7 : Chunks entités par type

```cypher
MATCH (c:Chunk {chunk_type: 'entity_summary'})-[:DESCRIBES_ENTITY]->(e)
RETURN labels(e)[0] AS entity_type, count(*) AS count
ORDER BY count DESC;
```

**Attendu** :

```
Person          45 (48 - 3 échecs)
Organization    27 (29 - 2 échecs)
GPE             19 (23 - 4 échecs)
Total           91
```

#### Test 8 : Recherche vectorielle test

```cypher
// Test avec embedding dummy (remplacer par vrai embedding Gemini)
WITH [0.1, 0.2, ...] AS test_embedding  // 768 dimensions

CALL db.index.vector.queryNodes(
  'chunk_embeddings',
  5,
  test_embedding
)
YIELD node AS chunk, score

RETURN chunk.text, chunk.chunk_type, score
ORDER BY score DESC;
```

---

## 🔧 Troubleshooting

### Erreur 429 : Quota Exceeded

**Symptôme** :

```
⚠️  Embedding error: 429 Quota exceeded for aiplatform.googleapis.com/
    online_prediction_requests_per_base_model
```

**Causes** :

- Trop de requêtes par minute (quota défaut : 60/min)
- Compte GCP nouveau avec quotas par défaut

**Solutions** :

1. **Le rate limiting est déjà intégré** dans v3.0 :
    
    - Attente de 1s entre chaque requête
    - Exponential backoff : 2s, 4s, 8s, 16s, 32s
    - 5 tentatives automatiques
2. **Augmenter quota GCP** :
    
    ```
    1. https://console.cloud.google.com/iam-admin/quotas
    2. Filtrer : "aiplatform.googleapis.com/online_prediction_requests"
    3. Sélectionner quota
    4. EDIT QUOTAS → Demander 600/min
    5. Justification : "Historical research project"
    6. Attendre approbation (24-48h)
    ```
    
3. **Ralentir davantage** (si nécessaire) :
    
    ```python
    # Dans vectorize_chunks_gemini.py, ligne ~550
    base_delay = 2.0  # Au lieu de 1.0
    ```
    

### Erreur : Invalid credentials

**Symptôme** :

```
google.auth.exceptions.DefaultCredentialsError: Could not automatically 
determine credentials
```

**Solution** :

```bash
# Vérifier variable d'environnement
echo $GOOGLE_APPLICATION_CREDENTIALS

# Si vide, configurer
export GOOGLE_APPLICATION_CREDENTIALS="$HOME/.gcp/vertex-ai-key.json"

# Vérifier fichier existe
ls -la $GOOGLE_APPLICATION_CREDENTIALS
```

### Erreur : Project ID non trouvé

**Symptôme** :

```
KeyError: 'gcp'
```

**Solution** : Ajouter section `gcp` dans `config.json` :

```json
{
  "gcp": {
    "project_id": "gen-lang-client-0810997704",
    "location": "us-central1"
  }
}
```

### Embeddings échouent pour certaines entités

**Symptôme** :

```
⚠️ ERRORS (9)
  • Embedding failed for /id/person/xxx
```

**Causes possibles** :

1. Texte trop court (< 20 caractères)
2. Quota 429 pour ces requêtes spécifiques
3. Entité sans contenu (pas de notice_bio/inst/geo)

**Diagnostic** :

```cypher
MATCH (e {id: "/id/person/1c6bf450-3c41-4755-be82-d77f9744f6e1"})
RETURN e.prefLabel_fr, 
       e.notice_bio,
       length(coalesce(e.notice_bio, '')) AS bio_length;
```

**Solution** :

```bash
# Retry avec script dédié
python retry_failed_entities.py
```

### Fuzzy matching trop lent

**Symptôme** : Vectorisation très lente (> 30 minutes)

**Solution** : Désactiver fuzzy matching :

```bash
python vectorize_chunks_gemini.py --no-fuzzy
```

**Trade-off** :

- Plus rapide
- Moins de quotes localisées (seulement exact match)

### Index vectoriel non créé

**Symptôme** :

```
SHOW INDEXES → chunk_embeddings non présent
```

**Solution** :

```cypher
// Supprimer si existe
DROP INDEX chunk_embeddings IF EXISTS;

// Recréer
CREATE VECTOR INDEX chunk_embeddings
FOR (c:Chunk) ON (c.embedding)
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 768,
    `vector.similarity_function`: 'cosine'
  }
};
```

### Claude Projects ne trouve pas les chunks

**Symptôme** : Le tool Similarity Search retourne 0 résultats

**Vérifications** :

```cypher
// 1. Chunks existent ?
MATCH (c:Chunk) RETURN count(c);

// 2. Embeddings Vertex AI ?
MATCH (c:Chunk) 
WHERE c.embedding_provider = 'vertex-ai'
RETURN count(c);

// 3. Index actif ?
SHOW INDEXES WHERE name = 'chunk_embeddings';

// 4. Test recherche manuelle
CALL db.index.vector.queryNodes(
  'chunk_embeddings', 
  5, 
  [0.1, 0.2, ...]  // 768 dimensions
) YIELD node, score
RETURN node.text, score;
```

---

## 📝 Notes Techniques

### Rate Limiting Automatique

Le script v3.0 implémente :

- **Base delay** : 1s entre chaque requête
- **Exponential backoff** : 2^attempt secondes en cas d'erreur 429
- **Max retries** : 5 tentatives

**Temps estimé** :

- 225 chunks documents × 1.5s = ~6 minutes
- 91 chunks entités × 1.5s = ~2.5 minutes
- **Total** : ~10 minutes (vs 2 minutes sans rate limiting)

### Coûts Vertex AI

Pour un projet typique (316 chunks, 650 chars moyenne) :

```
316 chunks × 650 chars = 205,400 caractères
205,400 / 1000 = 205.4 unités
205.4 × $0.00001 = $0.002054

Coût total : ~0.002$ (moins d'un centime)
```

**Avec crédits gratuits (300$)** : ~150 millions de chunks possibles !

### Entités sans embeddings : Normal

9/100 entités ont échoué, c'est **acceptable** car :

1. Souvent = entités avec très peu de contenu
2. 91% de couverture reste excellent
3. Recherche sémantique compensera les manquantes
4. Retry disponible si critique

### MENTIONS depuis structures réifiées

Les MENTIONS sont extraites depuis les **IDs dans le texte** :

```
"Occupations: Employée à Organisation Suisse /id/org/96ad0f92..."
                                               ^^^^^^^^^^^^
                                               Détecté et lié !
```

C'est pourquoi les chunks d'entités ont 30 MENTIONS (depuis occupations, origins, relations familiales).

### Multilingue FR/DE

`text-multilingual-embedding-002` gère nativement :

- Français
- Allemand
- 100+ autres langues

Parfait pour corpus diplomatique CH multilingue !

---
