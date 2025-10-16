# utils/relation_calculator.py
"""
Calcul des relations déduites après import de base
Conforme Architecture v1.4.1

BUGFIX v2.2.1 : Remplacement duration.between() par calcul epoch
(bug Neo4j Aura confirmé : duration.between retourne des valeurs incorrectes)
"""

from typing import Dict


class RelationCalculator:
    """Calcule les relations complexes post-import"""

    def __init__(self, config: Dict):
        self.config = config
        windows = config.get('calculated_relations', {}).get('windows', {})
        self.reply_max_days = windows.get('reply_search_days', 90)
        self.chain_max_days = windows.get('communication_chain_max_days', 14)

    def calculate_replies_to(self, session) -> int:
        """
        Crée REPLIES_TO : dernier message antérieur avec acteur/destinataire inversés
        Option B (robuste) : ne dépend pas strictement de in_reply_to_date
        """
        query = """
        MATCH (reply:MicroAction)
        WHERE (toLower(reply.link_type) CONTAINS 'replies_to' 
               OR toLower(reply.link_type) CONTAINS 'acknowledges_receipt')
          AND reply.actor_id IS NOT NULL 
          AND reply.recipient_id IS NOT NULL
          AND reply.date_start IS NOT NULL
          AND NOT (reply)-[:REPLIES_TO]->()

        CALL (reply) {
          WITH reply
          MATCH (original:MicroAction)
          WHERE original.actor_id = reply.recipient_id
            AND original.recipient_id = reply.actor_id
            AND original.date_start IS NOT NULL
            AND date(original.date_start) < date(reply.date_start)
          RETURN original
          ORDER BY date(original.date_start) DESC
          LIMIT 1
        }

        WITH reply, original
        WHERE original IS NOT NULL

        MERGE (reply)-[r:REPLIES_TO]->(original)
        SET r.computed = true

        RETURN count(r) AS created
        """

        result = session.run(query)
        return result.single()['created']

    def calculate_next_in_chain(self, session) -> int:
        """
        Crée NEXT_IN_COMMUNICATION_CHAIN selon doc v1.4.1 Section 6.4

        BUGFIX : Utilise calcul epoch au lieu de duration.between()

        Critères STRICTS :
        - Même acteur/destinataire (direction identique)
        - Même personne concernée (via CONCERNS ou REFERENCES)
        - Maximum N jours d'écart (config, défaut 14)
        - Pas d'autre message intermédiaire
        """
        query = """
        MATCH (m1:MicroAction), (m2:MicroAction)
        WHERE m1.actor_id = m2.actor_id
          AND m1.recipient_id = m2.recipient_id
          AND m1.date_start IS NOT NULL
          AND m2.date_start IS NOT NULL
          AND m1.date_start > m2.date_start

          // ✨ BUGFIX : Calcul différence en jours avec epoch
          AND toInteger((datetime(m1.date_start).epochSeconds - datetime(m2.date_start).epochSeconds) / 86400) <= $max_days

          // ⭐ CRITÈRE CLÉ DOC v1.4.1 : Même personne concernée
          AND EXISTS {
            MATCH (m1)-[:CONCERNS|REFERENCES]->(p:Person)
            MATCH (m2)-[:CONCERNS|REFERENCES]->(p)
          }

          // ⭐ Pas d'intermédiaire
          AND NOT EXISTS {
            MATCH (m3:MicroAction)
            WHERE m3.actor_id = m1.actor_id
              AND m3.recipient_id = m1.recipient_id
              AND m3.date_start > m2.date_start
              AND m3.date_start < m1.date_start
              AND EXISTS {
                MATCH (m3)-[:CONCERNS|REFERENCES]->(p:Person)
                MATCH (m1)-[:CONCERNS|REFERENCES]->(p)
              }
          }

        // Lien chronologique : ancien → nouveau
        MERGE (m2)-[r:NEXT_IN_COMMUNICATION_CHAIN]->(m1)
        WITH r,
             datetime(m1.date_start).epochSeconds AS epoch1,
             datetime(m2.date_start).epochSeconds AS epoch2
        SET r.computed = true,
            r.days_diff = toInteger((epoch1 - epoch2) / 86400)

        RETURN count(r) AS created
        """

        result = session.run(query, max_days=self.chain_max_days)
        return result.single()['created']

    def calculate_acted_in_context(self, session) -> int:
        """
        Crée ACTED_IN_CONTEXT_OF selon doc v1.4.1 Section 6.3

        Logique :
        - La micro-action mentionne une personne (CONCERNS ou REFERENCES)
        - Cette personne est victime d'un événement
        - Les intervalles temporels se chevauchent
        """
        query = """
        MATCH (m:MicroAction)-[:CONCERNS|REFERENCES]->(p:Person)
        MATCH (e:Event)
        WHERE e.victim_id = p.id
          AND m.date_start IS NOT NULL
          AND e.date_start IS NOT NULL

        // Normalisation dates avec coalesce (gestion NULL)
        WITH m, e,
             date(m.date_start) AS m_start,
             date(coalesce(m.date_end, m.date_start)) AS m_end,
             date(e.date_start) AS e_start,
             date(coalesce(e.date_end, e.date_start)) AS e_end

        // Chevauchement d'intervalles
        WHERE m_start <= e_end AND m_end >= e_start

        MERGE (m)-[r:ACTED_IN_CONTEXT_OF]->(e)
        SET r.computed = true

        RETURN count(r) AS created
        """

        result = session.run(query)
        return result.single()['created']

    def calculate_case_timeline(self, session) -> int:
        """
        Crée FOLLOWS_IN_CASE selon doc v1.4.1 Section 6.2

        Timeline chronologique des événements par victime.
        Utilise fallback manuel (APOC non disponible sur Aura).
        """
        query = """
        MATCH (e1:Event), (e2:Event)
        WHERE e1.victim_id = e2.victim_id
          AND e1.victim_id IS NOT NULL
          AND e1.date_start IS NOT NULL
          AND e2.date_start IS NOT NULL
          AND e1.date_start < e2.date_start

          // Pas d'événement intermédiaire
          AND NOT EXISTS {
            MATCH (e3:Event)
            WHERE e3.victim_id = e1.victim_id
              AND e3.date_start > e1.date_start
              AND e3.date_start < e2.date_start
          }

        MERGE (e1)-[r:FOLLOWS_IN_CASE]->(e2)
        SET r.computed = true

        RETURN count(r) AS created
        """

        result = session.run(query)
        return result.single()['created']