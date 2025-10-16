#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vectorize_chunks_gemini.py - Quote-First avec Gemini Embeddings
Version: 3.0.0 - Vertex AI Native
Date: 2025-10-11
"""

import json
import re
import time
from typing import List, Dict, Any, Set, Optional, Tuple
from neo4j import GraphDatabase
from google.cloud import aiplatform
from vertexai.language_models import TextEmbeddingModel

# Fuzzy matching optionnel
try:
    from rapidfuzz import fuzz

    FUZZY_AVAILABLE = True
except ImportError:
    FUZZY_AVAILABLE = False
    print("⚠️  rapidfuzz not installed - fuzzy matching disabled")


class QuoteFirstVectorizerGemini:
    """Vectorisation Quote-First avec Gemini Embeddings"""

    def __init__(self, config_path: str = "config.json"):
        self.config = self._load_config(config_path)

        # Neo4j
        neo4j_config = self.config['neo4j']
        self.driver = GraphDatabase.driver(
            neo4j_config['uri'],
            auth=(neo4j_config['user'], neo4j_config['password']),
            database=neo4j_config.get('database', 'neo4j')
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
        self.dimensions = 768  # text-multilingual-embedding-002

        print(f"✅ Gemini model loaded: {model_name}")

        # Contexte adaptatif
        self.use_adaptive_context = True
        self.min_total_context = 400
        self.max_total_context = 900
        self.context_before = 600
        self.context_after = 600

        # Fuzzy matching
        self.use_fuzzy = FUZZY_AVAILABLE
        self.fuzzy_threshold = 85.0

        self.stats = {
            'documents_processed': 0,
            'assertions_total': 0,
            'quotes_located_exact': 0,
            'quotes_located_fuzzy': 0,
            'quotes_not_found': [],
            'chunks_created': 0,
            'embeddings_generated': 0,
            'relations_describes_event': 0,
            'relations_describes_action': 0,
            'relations_mentions': 0,
            'errors': [],
            'context_sizes': []
        }

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def run(self):
        """Exécute vectorisation Quote-First avec Gemini"""
        print("=" * 70)
        print("VECTORIZATION v3.0 - Gemini Embeddings Native")
        print("=" * 70)
        print()

        if self.use_adaptive_context:
            print(f"✨ Adaptive context ENABLED")
            print(f"   Min total: {self.min_total_context} chars")
            print(f"   Max total: {self.max_total_context} chars")

        if self.use_fuzzy:
            print(f"✨ Fuzzy matching ENABLED (threshold: {self.fuzzy_threshold}%)")
        print()

        with self.driver.session() as session:
            # Vérifier assertions
            print("🔍 Checking prerequisites...")
            assertion_check = session.run("MATCH (a:Assertion) RETURN count(a) as count")
            assertion_count = assertion_check.single()['count']

            if assertion_count == 0:
                print("❌ FATAL: No Assertions found!")
                return

            print(f"  ✅ Found {assertion_count} Assertions\n")

            # Vérifier direction SUPPORTS
            print("🔗 Checking SUPPORTS direction...")
            supports_check = session.run("""
                MATCH (d:ArchiveDocument)-[:SUPPORTS]->(a:Assertion)
                RETURN count(DISTINCT d) as docs_with_assertions
            """)
            docs_count = supports_check.single()['docs_with_assertions']

            if docs_count == 0:
                print("❌ FATAL: No Documents linked to Assertions!")
                return

            print(f"  ✅ Found {docs_count} Documents with Assertions\n")

            # Supprimer anciens chunks
            print("🗑️  Clearing old document chunks...")
            session.run("""
                MATCH (c:Chunk)
                WHERE c.chunk_type = 'quote_centered'
                DETACH DELETE c
            """)
            print("  ✅ Cleared\n")

            # Récupérer documents
            print("📖 Loading documents...")
            documents = list(session.run("""
                MATCH (d:ArchiveDocument)
                WHERE d.content IS NOT NULL AND d.content <> ''
                RETURN d.id as doc_id, 
                       d.content as content,
                       d.title as title,
                       d.date_norm as date_norm
                ORDER BY d.id
            """))
            print(f"  ✅ Loaded {len(documents)} documents\n")

            # Traiter chaque document
            for doc_record in documents:
                self._process_document(session, doc_record)

            # Créer index vectoriel
            self._create_vector_index(session)

        # Rapport
        self._print_report()
        self.driver.close()

    def _calculate_adaptive_context(self, quote_length: int) -> int:
        """Calcule taille contexte selon longueur quote"""
        if not self.use_adaptive_context:
            return self.context_before

        if quote_length < 100:
            context = 200
        elif quote_length < 300:
            context = 350
        else:
            context = 450

        total = quote_length + (2 * context)

        if total < self.min_total_context:
            context = (self.min_total_context - quote_length) // 2
        elif total > self.max_total_context:
            context = (self.max_total_context - quote_length) // 2

        return max(context, 150)

    def _extend_to_paragraph_boundaries(self, start_pos: int, end_pos: int,
                                        content: str) -> Tuple[int, int]:
        """Étend jusqu'aux frontières de paragraphe si proche"""
        prev_para = content.rfind('\n\n', 0, start_pos)
        if prev_para != -1 and (start_pos - prev_para) < 50:
            start_pos = prev_para + 2

        next_para = content.find('\n\n', end_pos)
        if next_para != -1 and (next_para - end_pos) < 50:
            end_pos = next_para

        return start_pos, end_pos

    def _process_document(self, session, doc_record):
        """Traite un document avec stratégie Quote-First"""
        doc_id = doc_record['doc_id']
        content = doc_record['content']

        print(f"📄 {doc_record.get('title', doc_id[:40])}...")

        # Récupérer assertions
        assertions_result = session.run("""
            MATCH (d:ArchiveDocument {id: $doc_id})-[:SUPPORTS]->(a:Assertion)
            WHERE a.source_quote IS NOT NULL AND a.source_quote <> ''
            OPTIONAL MATCH (a)-[:CLAIMS]->(e:Event)
            OPTIONAL MATCH (a)-[:CLAIMS]->(m:MicroAction)
            RETURN a.assertion_id as assertion_id,
                   a.source_quote as quote,
                   e.event_id as event_id,
                   m.micro_id as micro_id
        """, doc_id=doc_id)

        assertions = list(assertions_result)
        self.stats['assertions_total'] += len(assertions)

        if not assertions:
            print(f"  ℹ️  No assertions\n")
            return

        print(f"  📌 {len(assertions)} assertions")

        # Normaliser contenu
        content_normalized = self._normalize_content(content)

        # Localiser quotes
        quote_locations = []
        debug_count = 0

        for a in assertions:
            quote_text = self._normalize_quote(a['quote'])
            quote_normalized = self._normalize_content(quote_text)

            pos = content_normalized.find(quote_normalized)
            match_method = 'exact'

            if pos == -1 and self.use_fuzzy:
                pos = self._fuzzy_locate_quote(quote_normalized, content_normalized)
                if pos != -1:
                    match_method = 'fuzzy'

            if pos != -1:
                quote_locations.append({
                    'assertion_id': a['assertion_id'],
                    'start': pos,
                    'end': pos + len(quote_normalized),
                    'quote': quote_text,
                    'quote_length': len(quote_text),
                    'event_id': a['event_id'],
                    'micro_id': a['micro_id'],
                    'match_method': match_method
                })

                if match_method == 'exact':
                    self.stats['quotes_located_exact'] += 1
                else:
                    self.stats['quotes_located_fuzzy'] += 1
            else:
                self.stats['quotes_not_found'].append({
                    'doc_id': doc_id,
                    'doc_title': doc_record.get('title', 'N/A'),
                    'assertion_id': a['assertion_id'],
                    'quote': quote_text[:80] + '...' if len(quote_text) > 80 else quote_text
                })

                if debug_count < 3:
                    self._debug_quote_mismatch(quote_text, content, quote_normalized, content_normalized)
                    debug_count += 1

        exact = self.stats['quotes_located_exact']
        fuzzy = self.stats['quotes_located_fuzzy']
        total_located = exact + fuzzy

        print(f"  ✅ Located {total_located}/{len(assertions)} quotes", end="")
        if fuzzy > 0:
            print(f" ({exact} exact, {fuzzy} fuzzy)")
        else:
            print()

        if not quote_locations:
            print(f"  ⚠️  No quotes located\n")
            return

        # Créer chunks
        chunks_data = self._create_quote_centered_chunks(
            content,
            content_normalized,
            quote_locations
        )

        print(f"  📦 {len(chunks_data)} chunks")

        if self.use_adaptive_context and chunks_data:
            avg_size = sum(len(c['text']) for c in chunks_data) / len(chunks_data)
            print(f"     Avg chunk size: {int(avg_size)} chars")

        # Écrire dans Neo4j
        for chunk_data in chunks_data:
            self._write_chunk_to_neo4j(session, doc_id, chunk_data, doc_record)

        print(f"  ✅ Done\n")
        self.stats['documents_processed'] += 1

    def _normalize_quote(self, quote: str) -> str:
        """Normalisation spécifique pour les quotes"""
        quote = quote.strip()

        while quote.startswith('"') or quote.startswith('"'):
            quote = quote[1:]
        while quote.endswith('"') or quote.endswith('"'):
            quote = quote[:-1]

        while quote.startswith("'") or quote.startswith("'"):
            quote = quote[1:]
        while quote.endswith("'") or quote.endswith("'"):
            quote = quote[:-1]

        quote = quote.strip()
        return quote

    def _normalize_content(self, text: str) -> str:
        """Normalisation du contenu pour matching robuste"""
        text = text.replace('\n', ' ')
        text = text.replace('\r', ' ')
        text = re.sub(r'\s+', ' ', text)
        text = text.lower()
        text = text.replace('"', '"').replace('"', '"')
        text = text.replace(''', "'").replace(''', "'")
        text = re.sub(r'\[\[/id/[^|]+\|([^\]]+)\]\]', r'\1', text)
        text = re.sub(r'\[\[/id/[^\]]+\]\]', '', text)
        text = re.sub(r'\(/id/(person|org|gpe)/[a-f0-9-]+\)', '', text)
        text = text.replace("'", "'")
        text = text.strip()
        return text

    def _fuzzy_locate_quote(self, quote_normalized: str, content_normalized: str) -> int:
        """Cherche une quote avec fuzzy matching"""
        if not FUZZY_AVAILABLE:
            return -1

        quote_len = len(quote_normalized)
        if quote_len < 30:
            return -1

        best_score = 0
        best_pos = -1
        step = max(10, quote_len // 10)

        for i in range(0, len(content_normalized) - quote_len + 1, step):
            window = content_normalized[i:i + quote_len]
            score = fuzz.ratio(quote_normalized, window)

            if score > best_score:
                best_score = score
                best_pos = i

            if score >= 98:
                break

        if best_score >= self.fuzzy_threshold:
            return best_pos

        return -1

    def _debug_quote_mismatch(self, quote_raw: str, content_raw: str,
                              quote_norm: str, content_norm: str):
        """Debug visuel pour comprendre pourquoi une quote ne matche pas"""
        print(f"\n  🔍 DEBUG Quote Not Found:")
        print(f"     Raw: {quote_raw[:60]}...")
        print(f"     Norm: {quote_norm[:60]}...")

        words = [w for w in quote_norm.split() if len(w) > 3][:5]
        found_words = sum(1 for word in words if word in content_norm)

        print(f"     Word match: {found_words}/{len(words)} significant words found")

    def _create_quote_centered_chunks(
            self,
            content_original: str,
            content_normalized: str,
            quote_locations: List[Dict]
    ) -> List[Dict]:
        """Crée chunks centrés sur quotes avec contexte adaptatif"""
        chunks = []

        for idx, loc in enumerate(quote_locations):
            quote_length = loc['quote_length']
            context_size = self._calculate_adaptive_context(quote_length)

            start = max(0, loc['start'] - context_size)
            end = min(len(content_normalized), loc['end'] + context_size)

            start, end = self._extend_to_paragraph_boundaries(start, end, content_original)

            chunk_text = content_original[start:end]
            self.stats['context_sizes'].append(len(chunk_text))

            chunk_data = {
                'chunk_id': f"chunk_{idx}",
                'text': chunk_text,
                'type': 'quote_centered',
                'start_char': start,
                'end_char': end,
                'assertion_id': loc['assertion_id'],
                'event_id': loc.get('event_id'),
                'micro_id': loc.get('micro_id'),
                'match_method': loc.get('match_method', 'exact'),
                'context_size_used': context_size
            }

            chunks.append(chunk_data)
            self.stats['chunks_created'] += 1

        return chunks

    def _write_chunk_to_neo4j(self, session, doc_id: str, chunk_data: Dict, doc_record):
        """Écrit chunk et crée relations"""
        chunk_id = f"{doc_id}::{chunk_data['chunk_id']}"

        # Embedding via Gemini
        embedding = self._get_embedding_gemini(chunk_data['text'])
        if not embedding:
            self.stats['errors'].append(f"Embedding failed: {chunk_id}")
            return

        self.stats['embeddings_generated'] += 1
        year = self._extract_year(doc_record)

        # Créer Chunk
        session.run("""
            CREATE (c:Chunk {
                id: $chunk_id,
                text: $text,
                chunk_type: $chunk_type,
                start_char: $start_char,
                end_char: $end_char,
                embedding: $embedding,
                embedding_model: $embedding_model,
                embedding_provider: $embedding_provider,
                doc_id: $doc_id,
                year: $year,
                assertion_id: $assertion_id,
                match_method: $match_method
            })
        """,
                    chunk_id=chunk_id,
                    text=chunk_data['text'],
                    chunk_type=chunk_data['type'],
                    start_char=chunk_data['start_char'],
                    end_char=chunk_data['end_char'],
                    embedding=embedding,
                    embedding_model='text-multilingual-embedding-002',
                    embedding_provider='vertex-ai',
                    doc_id=doc_id,
                    year=year,
                    assertion_id=chunk_data['assertion_id'],
                    match_method=chunk_data.get('match_method', 'exact')
                    )

        # CHUNK_OF
        session.run("""
            MATCH (c:Chunk {id: $chunk_id})
            MATCH (d:ArchiveDocument {id: $doc_id})
            MERGE (c)-[:CHUNK_OF]->(d)
        """, chunk_id=chunk_id, doc_id=doc_id)

        # DESCRIBES_EVENT
        if chunk_data['event_id']:
            try:
                result = session.run("""
                    MATCH (c:Chunk {id: $chunk_id})
                    MATCH (e:Event {event_id: $event_id})
                    MERGE (c)-[r:DESCRIBES_EVENT]->(e)
                    SET r.method = $match_method,
                        r.confidence = CASE 
                            WHEN $match_method = 'exact' THEN 1.0 
                            ELSE 0.9 
                        END,
                        r.via_assertion = $assertion_id
                    RETURN count(r) as created
                """,
                                     chunk_id=chunk_id,
                                     event_id=chunk_data['event_id'],
                                     assertion_id=chunk_data['assertion_id'],
                                     match_method=chunk_data.get('match_method', 'exact')
                                     )

                if result.single()['created'] > 0:
                    self.stats['relations_describes_event'] += 1
            except Exception as e:
                self.stats['errors'].append(f"DESCRIBES_EVENT: {e}")

        # DESCRIBES_ACTION
        if chunk_data['micro_id']:
            try:
                result = session.run("""
                    MATCH (c:Chunk {id: $chunk_id})
                    MATCH (m:MicroAction {micro_id: $micro_id})
                    MERGE (c)-[r:DESCRIBES_ACTION]->(m)
                    SET r.method = $match_method,
                        r.confidence = CASE 
                            WHEN $match_method = 'exact' THEN 1.0 
                            ELSE 0.9 
                        END,
                        r.via_assertion = $assertion_id
                    RETURN count(r) as created
                """,
                                     chunk_id=chunk_id,
                                     micro_id=chunk_data['micro_id'],
                                     assertion_id=chunk_data['assertion_id'],
                                     match_method=chunk_data.get('match_method', 'exact')
                                     )

                if result.single()['created'] > 0:
                    self.stats['relations_describes_action'] += 1
            except Exception as e:
                self.stats['errors'].append(f"DESCRIBES_ACTION: {e}")

        # MENTIONS
        mentions = self._extract_mentions(chunk_data['text'])
        for entity_id in mentions:
            try:
                session.run("""
                    MATCH (c:Chunk {id: $chunk_id})
                    MATCH (e {id: $entity_id})
                    MERGE (c)-[:MENTIONS]->(e)
                """, chunk_id=chunk_id, entity_id=entity_id)
                self.stats['relations_mentions'] += 1
            except:
                pass

    def _extract_mentions(self, text: str) -> Set[str]:
        """Extrait entity IDs"""
        mentions = set()
        for pattern in [
            r'\[\[(/id/(person|org|gpe)/[a-fA-F0-9-]+)\|[^\]]+\]\]',
            r'\[\[(/id/(person|org|gpe)/[a-fA-F0-9-]+)\]\]',
            r'\((/id/(person|org|gpe)/[a-fA-F0-9-]+)\)'
        ]:
            for match in re.finditer(pattern, text):
                mentions.add(match.group(1))
        return mentions

    def _get_embedding_gemini(self, text: str) -> List[float]:
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
                    print(f"  ⚠️  Embedding error after {max_retries} attempts: {error_str[:100]}")
                    return []

        return []

    def _extract_year(self, doc_record: Dict) -> Optional[int]:
        """Extrait année"""
        date_str = doc_record.get('date_norm')
        if date_str and isinstance(date_str, str) and len(date_str) >= 4:
            try:
                return int(date_str[:4])
            except:
                pass
        return None

    def _create_vector_index(self, session):
        """Crée index vectoriel"""
        print("🔧 Creating vector index...")
        try:
            session.run("""
                CREATE VECTOR INDEX chunk_embeddings IF NOT EXISTS
                FOR (c:Chunk)
                ON c.embedding
                OPTIONS {
                    indexConfig: {
                        `vector.dimensions`: 768,
                        `vector.similarity_function`: 'cosine'
                    }
                }
            """)
            print("  ✅ Vector index created\n")
        except Exception as e:
            if "already exists" in str(e).lower():
                print("  ✅ Vector index already exists\n")
            else:
                print(f"  ⚠️  Error: {e}\n")

    def _print_report(self):
        """Rapport détaillé"""
        print("=" * 70)
        print("VECTORIZATION REPORT v3.0 - Gemini Embeddings")
        print("=" * 70)
        print()

        print("📊 STATISTICS")
        print("-" * 70)
        print(f"Documents processed: {self.stats['documents_processed']}")
        print(f"Assertions found: {self.stats['assertions_total']}")

        total_located = self.stats['quotes_located_exact'] + self.stats['quotes_located_fuzzy']
        print(f"Quotes located: {total_located}")
        print(f"  - Exact matches: {self.stats['quotes_located_exact']}")
        print(f"  - Fuzzy matches: {self.stats['quotes_located_fuzzy']}")
        print(f"Chunks created: {self.stats['chunks_created']}")
        print(f"Embeddings generated (Gemini): {self.stats['embeddings_generated']}")

        if self.stats['context_sizes']:
            avg_chunk = sum(self.stats['context_sizes']) / len(self.stats['context_sizes'])
            min_chunk = min(self.stats['context_sizes'])
            max_chunk = max(self.stats['context_sizes'])
            print(f"Chunk sizes: avg={int(avg_chunk)}, min={min_chunk}, max={max_chunk}")
        print()

        if self.stats['assertions_total'] > 0:
            coverage = (total_located / self.stats['assertions_total']) * 100
            print(f"📈 Quote coverage: {coverage:.1f}%")

            if coverage < 50:
                print(f"   ⚠️  Low coverage - check normalization or OCR quality")
            elif coverage < 80:
                print(f"   ℹ️  Good coverage - some quotes still missing")
            else:
                print(f"   ✅ Excellent coverage!")
            print()

        print("🔗 RELATIONS")
        print("-" * 70)
        print(f"DESCRIBES_EVENT: {self.stats['relations_describes_event']}")
        print(f"DESCRIBES_ACTION: {self.stats['relations_describes_action']}")
        print(f"MENTIONS: {self.stats['relations_mentions']}")
        print()

        if self.stats['quotes_not_found']:
            not_found_count = len(self.stats['quotes_not_found'])
            print(f"⚠️  QUOTES NOT FOUND ({not_found_count})")
            print("-" * 70)

            if not_found_count <= 10:
                for nf in self.stats['quotes_not_found']:
                    print(f"  • {nf['doc_title']}")
                    print(f"    {nf['quote']}")
            else:
                print(f"  First 5 examples:")
                for nf in self.stats['quotes_not_found'][:5]:
                    print(f"  • {nf['doc_title']}: {nf['quote']}")
                print(f"  ... and {not_found_count - 5} more")
            print()

        if self.stats['errors']:
            print(f"❌ ERRORS ({len(self.stats['errors'])})")
            print("-" * 70)
            for err in self.stats['errors'][:5]:
                print(f"  • {err}")
            print()

        print("=" * 70)
        total = self.stats['relations_describes_event'] + self.stats['relations_describes_action']
        if total > 0:
            print(f"✅ SUCCESS: {total} DESCRIBES_* relations created!")
            print(f"   Plus {self.stats['relations_mentions']} MENTIONS relations")
            print(f"   🚀 Using Gemini embeddings for Claude agent")
        else:
            print("❌ FAILURE: 0 DESCRIBES_* relations")
        print("=" * 70)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Vectorize v3.0 (Gemini Native)')
    parser.add_argument('--config', default='config.json')
    parser.add_argument('--no-fuzzy', action='store_true', help='Disable fuzzy matching')
    parser.add_argument('--no-adaptive', action='store_true', help='Disable adaptive context')
    args = parser.parse_args()

    print("Quote-First Vectorizer v3.0 - Gemini Embeddings")
    print("Features: Vertex AI Native + Adaptive context + Fuzzy fallback")
    print()

    vectorizer = QuoteFirstVectorizerGemini(config_path=args.config)

    if args.no_fuzzy:
        vectorizer.use_fuzzy = False
        print("Fuzzy matching disabled by user")

    if args.no_adaptive:
        vectorizer.use_adaptive_context = False
        print("Adaptive context disabled by user")

    print()

    vectorizer.run()


if __name__ == "__main__":
    main()