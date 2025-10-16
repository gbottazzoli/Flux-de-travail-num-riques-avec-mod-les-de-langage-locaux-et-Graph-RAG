# DOCUMENTATION ENTITÉS v2.5

Documentation technique enrichissement entités projet diplomatique suisse 1940-1945. Export Neo4j + RAG contexte LLM.

**Date:** 2025-10-08  
**Remplace:** Documentation entités v2.4  
**Harmonisée avec:** Documentation extraction v2.6, Architecture Neo4j v1.5

---

## CHANGELOG

**v2.4 → v2.5 (2025-10-08):**

- **Règles anti-redondance** : Section 13 - Déduplication appellations, proposition alias
- **Seuils de saturation** : Limites par type de bloc (5 appellations, 10 occupations, 8 relations)
- **Validation automatisée** : Script `validate_entities.py` documenté
- **Processus curation** : Consolidation périodique tous les 20-30 sources
- **Relations professionnelles restrictives** : Règles explicites hiérarchie uniquement
- **Occupation organization** : Clarification ORG employeur jamais PERSON

**v2.3 → v2.4 (2025-10-08):**

- **EDTF corrigé** : `../date` → `..date` (alignement Architecture Neo4j v1.5)
- **Appellations obligatoires** : Au moins 1 bloc NAME/ORGNAME/GPENAME pour toute fiche vide
- **Note minimale** : 20 mots minimum pour Notice biographique (PERSON) et Note (ORG/GPE)
- Tous exemples EDTF mis à jour avec format correct

---

## 1. MÉTADONNÉES FRONTMATTER

### 1.1 Structure obligatoire

```yaml
---
id: /id/type/uuid
aliases:
  - [variante 1]
  - [variante 2]
prefLabel_fr: [forme canonique française]
prefLabel_de: [forme canonique allemande]
sameAs:
  - [URL autorité 1]
  - [URL autorité 2]
is_part_of:
  - "[[/id/type/uuid-parent]]"
gpe: "[[/id/gpe/uuid]]"  # ORG uniquement
---
````

### 1.2 Champs détaillés

#### id

- Format: `/id/type/uuid`
- Types: `person`, `org`, `gpe`
- UUID v4 stable
- **NE JAMAIS modifier**

#### aliases

- Liste variantes orthographiques/linguistiques
- Compléter depuis texte corpus si pertinent
- Inclure formes historiques, abréviations

#### prefLabel_fr / prefLabel_de

- Formes canoniques officielles
- Utilisées affichage/requêtes
- **Fortement recommandés**
- Validation automatisée :
    - Absence d'une langue → Warning informatif (`missing_prefLabel_fr` ou `missing_prefLabel_de`)
    - Absence des deux langues → Warning critique (`missing_prefLabel_both`)

#### sameAs

- URLs autorités externes
- Formats: Wikidata, GND, GeoNames
- Liste (plusieurs autorités possibles)
- Optionnel mais recommandé

#### is_part_of

- Relations hiérarchiques
- Format: `"[[/id/type/uuid-parent]]"` entre guillemets
- **/ initial OBLIGATOIRE**
- Liste (plusieurs parents possibles)
- **CRITIQUE: Frontmatter UNIQUEMENT, ne PAS répéter dans corps**
- **Validation automatique :** Toute occurrence d'`is_part_of` **dans le corps** du document est détectée et signalée comme non-conformité (`is_part_of_in_body`)

#### gpe (ORG uniquement)

- Lien vers GPE siège organisation
- Format: `"[[/id/gpe/uuid]]"` entre guillemets
- **/ initial OBLIGATOIRE**
- **Obligatoire pour ORG**

---

## 2. RÈGLES TRANSVERSALES

### 2.1 Héritage Documentation extraction

**CRITIQUE:** Hérite règles [[Documentation extraction v2.6]]:

- **Dates EDTF** : Formats standard (voir exemples sections 10-11)
- **Confidence** : section 4.4 (`#confidence/high|medium|low`)
- **Evidence_type** : section 4.5
- **Date_precision** : section 4.6 (dérivation automatique)
- **Date_source** : section 4.7

### 2.2 Formats tags / liens (COHÉRENCE SYSTÈME)

**Validation syntaxe automatisée :** Le système valide que les wikilinks frontmatter sont entre guillemets. Les violations (`frontmatter_unquoted_link`, `/` manquant) sont signalées automatiquement.

**RÈGLE ABSOLUE:** Tous vocabulaires contrôlés utilisent format #namespace/terme SANS guillemets (cohérence Documentation extraction v2.6).

```yaml
# ✅ CORRECT
type: #org_type/diplomatic
type_activity: #type_activity/government
relation_type: #relation_type/spouse
mode: #origin_mode/by_birth

# ❌ INCORRECT
type: "diplomatic"
type: diplomatic
type: "#org_type/diplomatic"
relation_type: "spouse"
```

**Format liens internes Obsidian:**

```yaml
# ✅ CORRECT - guillemets + / initial obligatoire FRONTMATTER
is_part_of: "[[/id/org/uuid]]"
gpe: "[[/id/gpe/uuid]]"

# ✅ CORRECT - SANS guillemets dans CORPS document
organization: [[/id/org/uuid]]
target: [[/id/person/uuid]]
place: [[/id/gpe/uuid]]

# ❌ INCORRECT (détecté automatiquement)
is_part_of: [[/id/org/uuid]]      # Manque guillemets frontmatter
gpe: "[[id/gpe/uuid]]"            # Manque / initial
```

### 2.3 Langues (BCP-47)

Liste autorisée:

- `fr`, `de`, `it`
- `fr-CH`, `de-CH` (optionnel)

---

## 3. PROVENANCE (OBLIGATOIRE)

> **CRITIQUE :** Chaque item d'une structure réifiée (`names`, `occupations`, `origins`, `family_relations`, `professional_relations`) DOIT avoir un bloc `provenance` complet.
> 
> **Mode strict :** L'absence de provenance bloque l'import.
> 
> **Mode normal :** L'absence génère un warning (`structure_missing_provenance`).

### 3.1 Structure

```yaml
provenance:
  doc: [[nom-fichier-sans-extension]]
  page: [numéro entier ou null]
  quote: "[extrait textuel 10-50 mots]"
  evidence_type: #evidence_type/reported
  confidence: #confidence/high
```

### 3.2 Cohérence confidence ↔ evidence_type

- `#confidence/high` → `#evidence_type/direct_observation` ou `#evidence_type/reported`
- `#confidence/medium` → `#evidence_type/reported` ou `#evidence_type/interpreted`
- `#confidence/low` → `#evidence_type/inferred` ou `#evidence_type/observation_only`

### 3.3 Quote

Citation textuelle exacte:

- Longueur: 10-50 mots
- Entre guillemets doubles
- Langue source originale

---

## 4. RID (RESOURCE ID)

### 4.1 Format

```
rid.[8hex].[TYPE].[nnn]
```

**Composants:**

- `8hex` : 8 premiers caractères UUID canonique
- `TYPE` : voir section 4.2
- `nnn` : compteur 3 chiffres (001, 002, 003...)

### 4.2 Types RID

**PERSON:**

- `NAME`, `ORIG`, `OCC`, `FAMREL`, `PROFREL`, `RES`

**ORG:**

- `ORGNAME`

**GPE:**

- `GPENAME`

### 4.3 Règles numérotation

- Séquentiel par TYPE
- Continuité vault: OCC.002 → OCC.003
- JAMAIS renuméroter existants
- Unicité vault-wide

---

## 5. VOCABULAIRES CONTRÔLÉS

### 5.1 org_type (ORG)

```yaml
#org_type/diplomatic
#org_type/executive
#org_type/judicial
#org_type/political_commission
#org_type/military
#org_type/penitentiary
#org_type/company
#org_type/ngo
```

### 5.2 type_activity (occupations PERSON)

```yaml
#type_activity/employment
#type_activity/government
#type_activity/diplomatic
#type_activity/religious
#type_activity/humanitarian
#type_activity/administrative
#type_activity/military
#type_activity/judicial
```

### 5.3 relation_type (familiales PERSON)

```yaml
#relation_type/spouse
#relation_type/parent
#relation_type/child
#relation_type/sibling
#relation_type/other
```

### 5.4 relation_type (professionnelles PERSON)

```yaml
#relation_type/superior_of
#relation_type/subordinate_of
#relation_type/colleague_of
```

### 5.5 origin_mode (origins PERSON)

```yaml
#origin_mode/by_birth
#origin_mode/by_marriage
#origin_mode/restored
#origin_mode/other
```

### 5.6 name_type (appellations PERSON)

```yaml
#name_type/birth_name
#name_type/married_name
#name_type/professional_name
#name_type/courtesy_name
#name_type/alias
#name_type/pseudonym
```

### 5.7 orgname_type (appellations ORG)

```yaml
#orgname_type/official
#orgname_type/colloquial
#orgname_type/historical
```

### 5.8 gpename_type (appellations GPE)

```yaml
#gpename_type/local_name
#gpename_type/historical_name
#gpename_type/occupation_name
```

---

## 6. STRUCTURES PERSON

### 6.1 Bio

```yaml
bio:
  description: [20-30 mots factuels]
  gender: F / M / X / unknown
  birth:
    date_edtf: [EDTF strict]
    place: [[/id/gpe/uuid]]
    provenance:
      doc: [[nom-fichier-sans-extension]]
      page: [int ou null]
      quote: "[extrait]"
      evidence_type: #evidence_type/reported
      confidence: #confidence/high
  death:
    date_edtf: [EDTF strict]
    place: [[/id/gpe/uuid]]
    provenance:
      doc: [[nom-fichier-sans-extension]]
      page: [int ou null]
      quote: "[extrait]"
      evidence_type: #evidence_type/reported
      confidence: #confidence/high
```

### 6.2 Appellations

**RÈGLE CRITIQUE (v2.4):** Toute fiche PERSON vide ou nouvellement créée DOIT contenir AU MOINS un bloc d'appellation avec provenance complète.

**Règle anti-redondance :** Avant de créer un nouveau bloc, vérifier si une appellation similaire existe (même display/lang/intervalle). Si identique → NE PAS créer, proposer alias frontmatter. Créer nouveau bloc SI : nom différent (naissance/mariage), période distincte, type distinct.

```yaml
names:
  - rid: rid.[8hex].NAME.[nnn]
    type: #name_type/birth_name
    display: [forme complète]
    parts:
      family: [nom]
      given: [prénom]
      particle: [de, von, van, etc. ou null]
    lang: [BCP-47: fr/de/it]
    interval: [EDTF]
    spouse: [nom ou UUID si courtesy_name, sinon null]
    provenance:
      doc: [[nom-fichier-sans-extension]]
      page: [int ou null]
      quote: "[extrait]"
      evidence_type: #evidence_type/reported
      confidence: #confidence/high
    note: [factuel - usage attesté]
```

### 6.3 Origins

```yaml
origins:
  - rid: rid.[8hex].ORIG.[nnn]
    mode: #origin_mode/by_birth
    place: [[/id/gpe/uuid]]
    interval: [EDTF]
    is_primary: true / false
    provenance:
      doc: [[nom-fichier-sans-extension]]
      page: [int ou null]
      quote: "[extrait]"
      evidence_type: #evidence_type/reported
      confidence: #confidence/high
    note: [factuel - acquisition nationalité]
```

**Règle is_primary:** Maximum 1 origin `is_primary: true`.

### 6.4 Occupations

**RÈGLE CRITIQUE : organization = ORG employeur, JAMAIS PERSON**

Le champ `organization` doit TOUJOURS pointer vers l'organisation employeur, même dans le cas "secrétaire de X". La relation hiérarchique avec une personne se documente dans `professional_relations`.

**Exemple correct - "Secrétaire de Bornand à la Croix-Rouge":**

```yaml
# ✅ CORRECT
occupations:
  - rid: rid.[8hex].OCC.[nnn]
    type_activity: #type_activity/administrative
    organization: [[/id/org/croix-rouge]]  # ORG employeur
    position_title: Secrétaire
    interval: [EDTF]
    provenance:
      doc: [[nom-fichier-sans-extension]]
      page: [int ou null]
      quote: "[extrait]"
      evidence_type: #evidence_type/reported
      confidence: #confidence/high
    note: Secrétaire de Bornand, directeur du service

professional_relations:
  - rid: rid.[8hex].PROFREL.[nnn]
    relation_type: #relation_type/subordinate_of
    target: [[/id/person/bornand]]  # Supérieur hiérarchique
    organization_context: [[/id/org/croix-rouge]]
    interval: [EDTF]
    provenance: [...]
    note: Relation hiérarchique attestée

# ❌ INCORRECT
occupations:
  - organization: [[/id/person/bornand]]  # NON - jamais PERSON
```

**Si organisation employeur inconnue :** Laisser champ `organization` vide et documenter dans note.

### 6.5 Relations familiales

```yaml
relations_family:
  - rid: rid.[8hex].FAMREL.[nnn]
    relation_type: #relation_type/spouse
    target: [[/id/person/uuid]]
    interval: [EDTF]
    provenance:
      doc: [[nom-fichier-sans-extension]]
      page: [int ou null]
      quote: "[extrait]"
      evidence_type: #evidence_type/reported
      confidence: #confidence/high
    note: [factuel]
```

**CRITIQUE:** PAS de champ `organization_context`.

### 6.6 Relations professionnelles

**RÈGLE RESTRICTIVE : NE créer bloc PROFREL QUE si TOUTES conditions remplies :**

1. **Evidence textuelle explicite** de hiérarchie :
    
    - "X est chef/directeur/supérieur de Y"
    - "Y travaille sous/pour X"
    - "Y secrétaire de X"
2. **Même organisation** (organization_context)
    
3. **Titre implique autorité** :
    
    - ✅ directeur, chef, supérieur, commandant, secrétaire (si subordonné)
    - ❌ conseiller, diplomate, membre (statut pair)
4. **Confidence high + evidence reported/direct_observation**
    

**NE PAS créer si :**

- Simple interaction : "informe", "écrit à", "rencontre", "communique avec"
- Contexte ponctuel sans hiérarchie établie
- Statut pair : conseillers fédéraux entre eux, diplomates même rang
- Doute sur hiérarchie

**Si incertain → Documenter occupation détaillée uniquement. Neo4j inférera les collègues via organisations partagées.**

```yaml
professional_relations:
  - rid: rid.[8hex].PROFREL.[nnn]
    relation_type: #relation_type/subordinate_of
    target: [[/id/person/uuid]]
    organization_context: [[/id/org/uuid]]
    interval: [EDTF]
    provenance:
      doc: [[nom-fichier-sans-extension]]
      page: [int ou null]
      quote: "[extrait]"
      evidence_type: #evidence_type/reported
      confidence: #confidence/high
    note: [factuel - hiérarchie]
```

**IMPORTANT :** `organization_context` est **une propriété contextuelle** de l'item. Elle **ne crée pas** de relation dans le graphe. La relation principale de l'item pointe vers `target`.

### 6.7 Notice biographique

**RÈGLE CRITIQUE (v2.4):** La section "Notice biographique" DOIT contenir minimum 20 mots pour toute fiche nouvellement créée ou vide. Cette note est un texte libre narratif qui sera enrichi progressivement avec d'autres sources.

---

## 7. STRUCTURES ORG

### 7.1 Description institutionnelle

```yaml
type: #org_type/diplomatic
```

**CRITIQUE:** Champ `is_part_of` UNIQUEMENT dans frontmatter, NE PAS répéter ici.

### 7.2 Note (traçabilité OBLIGATOIRE)

**RÈGLE CRITIQUE (v2.4):** La section "Note" DOIT contenir minimum 20 mots pour toute fiche ORG nouvellement créée ou vide.

```yaml
note: |
  Mentionné dans [[source-actuelle]] pour [fait précis + date EDTF].
  [Agrégation chronologique si multiples sources].
  Période activité documentée: [EDTF].
```

**Règles:**

- Enrichir SI note vide/lacunaire (< 20 mots)
- Format: mention source .md + fait précis
- PAS descriptions génériques

### 7.3 Appellations institutionnelles

**RÈGLE CRITIQUE (v2.4):** Toute fiche ORG vide ou nouvellement créée DOIT contenir AU MOINS un bloc d'appellation avec provenance complète.

**RÈGLE ANTI-MULTIPLICATION : UNE SEULE appellation sauf changement officiel temporel**

Les variantes linguistiques et mineures vont dans `aliases` frontmatter, PAS en blocs séparés.

**Créer UNE SEULE appellation** sauf si :

- Changement officiel de nom dans le temps (ex: Consulat → Légation)
- Forme historique distincte avec intervalle différent

**NE PAS créer de bloc pour** :

- Variante linguistique (fr/de/it) → `aliases` frontmatter
- Variation mineure ("à Berlin" vs ", Berlin") → `aliases` frontmatter
- Casse différente (MAJUSCULES vs minuscules) → `aliases` frontmatter

**Exemples :**

```yaml
# ❌ INCORRECT - 3 blocs pour même organisation
ORGNAME.001: "Légation de Suisse à Berlin" (fr)
ORGNAME.002: "Schweizerische Gesandtschaft in Berlin" (de)
ORGNAME.003: "Légation de Suisse, Berlin" (fr)

# ✅ CORRECT - 1 bloc + aliases frontmatter
ORGNAME.001: "Légation de Suisse à Berlin" (fr)
frontmatter.aliases:
  - Schweizerische Gesandtschaft in Berlin
  - Légation de Suisse, Berlin
  - SCHWEIZERISCHE GESANDTSCHAFT IN DEUTSCHLAND

# ✅ CORRECT - 2 blocs si changement officiel
ORGNAME.001: "Consulat de Suisse à Paris" (1920/1940)
ORGNAME.002: "Légation de Suisse à Paris" (1940/1945)
```

**Structure :**

```yaml
names:
  - rid: rid.[8hex].ORGNAME.[nnn]
    type: #orgname_type/official
    display: [nom complet]
    parts:
      org: [nom organisation]
      sigle: [acronyme ou vide]
    lang: [BCP-47]
    interval: [EDTF]
    provenance:
      doc: [[nom-fichier-sans-extension]]
      page: [int ou null]
      quote: "[extrait]"
      evidence_type: #evidence_type/reported
      confidence: #confidence/high
    note: [factuel]
```

---

## 8. STRUCTURES GPE

### 8.1 Note (traçabilité OBLIGATOIRE)

**RÈGLE CRITIQUE (v2.4):** La section "Note" DOIT contenir minimum 20 mots pour toute fiche GPE nouvellement créée ou vide.

```yaml
note: |
  Mentionné dans [[source-actuelle]] pour [fait précis + date].
  [Agrégation chronologique si multiples].
  Changements toponymiques/souveraineté 1940-1945: [si pertinent].
```

### 8.2 Coordonnées

```yaml
coordinates:
  system: WGS84
  lat: [latitude décimale]
  lon: [longitude décimale]
geonames_id: [identifiant ou null]
```

### 8.3 Appellations géopolitiques

**RÈGLE CRITIQUE (v2.4):** Toute fiche GPE vide ou nouvellement créée DOIT contenir AU MOINS un bloc d'appellation avec provenance complète.

**RÈGLE ANTI-MULTIPLICATION : UNE SEULE appellation sauf changement officiel temporel**

Les variantes linguistiques et mineures vont dans `aliases` frontmatter, PAS en blocs séparés.

**Créer UNE SEULE appellation** sauf si :

- Changement de souveraineté/nom officiel (ex: Königsberg → Kaliningrad)
- Forme historique distincte avec intervalle différent

**NE PAS créer de bloc pour** :

- Variante linguistique (fr/de/it) → `aliases` frontmatter
- Variation mineure → `aliases` frontmatter

**Exemples :**

```yaml
# ❌ INCORRECT - 2 blocs pour variantes linguistiques
GPENAME.001: "Berne" (fr)
GPENAME.002: "Bern" (de)

# ✅ CORRECT - 1 bloc + alias frontmatter
GPENAME.001: "Berne" (fr)
frontmatter.aliases:
  - Bern
  - Berna

# ✅ CORRECT - 2 blocs si changement souveraineté
GPENAME.001: "Königsberg" (..1945)
GPENAME.002: "Kaliningrad" (1945/..)
```

**Structure :**

```yaml
gpe_names:
  - rid: rid.[8hex].GPENAME.[nnn]
    display: [nom source]
    lang: [BCP-47]
    type: #gpename_type/local_name
    interval: [EDTF]
    is_part_of: [[/id/gpe/uuid-parent]]
    provenance:
      doc: [[nom-fichier-sans-extension]]
      page: [int ou null]
      quote: "[extrait]"
      evidence_type: #evidence_type/reported
      confidence: #confidence/high
    note: [factuel]
```

---

## 9. RÈGLES SPÉCIALES

### 9.1 Entités "n.c."

NE PAS enrichir entités non canoniques ("n.c.", "père", "avocat").

**Exception:** Stub avec bloc appellation si source nominative claire.

### 9.2 Merge incrémental

- Ajouter APRÈS existants
- JAMAIS effacer/remplacer
- JAMAIS renumérorer RID

---

## 10. EXEMPLES COMPLETS

### 10.1 ORG complet (v2.4 - EDTF corrigé)

```yaml
---
id: /id/org/07f4a125-3a5a-47ac-aa71-7d81a06b9fa0
aliases:
  - Division des affaires étrangères à Berne
  - Abteilung für Auswärtiges in Bern
prefLabel_fr: Division des affaires étrangères à Berne
prefLabel_de: Abteilung für Auswärtiges in Bern
sameAs: []
is_part_of:
  - "[[/id/org/811a0554-c0f7-480b-97b2-2af33e99ffb4|Conseil fédéral]]"
gpe: "[[/id/gpe/dee7e577-34de-4873-b28e-146172c0bdf7|Berne]]"
---

# Division des affaires étrangères à Berne

## Description institutionnelle

type: #org_type/diplomatic

## Note

note: |
  Impliquée suivi cas [[/id/person/5690edc0|Müller Elisabeth]]. 
  Transmet informations [[/id/org/92378f1e|Légation Berlin]] concernant 
  arrestation, condamnation, transfert. Le 14 octobre 1943, notifie 
  [[/id/org/8a26e625|Auswärtiges Amt]] décision [[/id/org/811a0554|Bundesrat]] 
  approuvant échange prisonniers.
  Période documentée: 1941/1943.

## Appellations institutionnelles

names:
  - rid: rid.07f4a125.ORGNAME.001
    type: #orgname_type/official
    display: Division des affaires étrangères
    parts:
      org: Division des affaires étrangères
      sigle: 
    lang: fr
    interval: 1941/1943
    provenance:
      doc: [[638731155479413286-1]]
      page: null
      quote: "Division des affaires étrangères"
      evidence_type: #evidence_type/reported
      confidence: #confidence/high
    note: Appellation officielle attestée correspondance 1941-1943.
```

### 10.2 PERSON avec appellation obligatoire (v2.4)

```yaml
---
id: /id/person/981f9d9a-1393-46a8-bc65-50f545e85596
aliases: []
prefLabel_fr: "Meylan n.c."
prefLabel_de: "Meylan n.c."
---

# Meylan n.c.

## Notice biographique

Secrétaire de Bornand à Paris mentionné dans le contexte diplomatique du suivi du cas Müller Elisabeth en avril 1942. Accompagne Madame Schulthess lors d'une visite à Bern le 18 avril 1942.

## Rôle dans le corpus

Figure comme intermédiaire dans les démarches humanitaires liées aux prisonniers civils durant l'occupation allemande de la France.

---

## Appellations

### Meylan

- **RID** : rid.981f9d9a.NAME.001
- **Type** : #name_type/professional_name
- **Display** : Meylan n.c.
- **Parts** :
  - family : Meylan
  - given : 
  - particle : 
- **Lang** : fr
- **Intervalle** : ..1942-04-24
- **Spouse** : 
- **Provenance** :
  - Doc : [[638731155479413286-1pdf]]
  - Page : null
  - Quote : "en compagnie de Meylan n.c., secrétaire du Bornand n.c."
  - Evidence : #evidence_type/reported
  - Confidence : #confidence/high
- **Note** : Nom de famille seul mentionné, prénom non connu.

---

## Origines


---

## Lieux de résidence


---

## Occupations


---

## Relations familiales


---

## Relations professionnelles


---

## Notes de recherche



## Contexte relationnel



## Sources principales
```

---

## 11. VALIDATION MANUELLE

### 11.1 Checklist

- [ ] Métadonnées frontmatter complètes (id, aliases, prefLabel, sameAs, is_part_of, gpe)
- [ ] prefLabel_fr ET/OU prefLabel_de présents (warnings si absents)
- [ ] Tous vocabulaires format #namespace/terme SANS guillemets
- [ ] Liens internes frontmatter: guillemets + / initial obligatoires
- [ ] Liens internes corps: SANS guillemets
- [ ] is_part_of: frontmatter UNIQUEMENT (validation automatique si en corps)
- [ ] **Note minimale 20 mots** (Notice biographique PERSON, Note ORG/GPE)
- [ ] **Au moins 1 bloc appellation** pour toute fiche vide (NAME/ORGNAME/GPENAME)
- [ ] **ORG/GPE : 1 appellation max** (variantes → aliases frontmatter)
- [ ] **Occupation : organization = ORG employeur, jamais PERSON**
- [ ] **Relations pro : Hiérarchie explicite uniquement**
- [ ] Provenance complète pour TOUTES structures (doc/page/quote/evidence_type/confidence)
- [ ] Confidence ↔ evidence_type cohérents
- [ ] Intervals EDTF réalistes avec format correct (`..` non `../`)
- [ ] RID: 8hex + 3 chiffres, continuité
- [ ] Aucune entité "n.c." enrichie

**Recommandation** : Utiliser `validate_entities.py` (voir section 14) avant validation manuelle.

### 11.2 Erreurs fréquentes

❌ `type: "#org_type/diplomatic"` → ✅ `type: #org_type/diplomatic`  
❌ `is_part_of: [[/id/org/uuid]]` → ✅ `is_part_of: "[[/id/org/uuid]]"` (frontmatter)  
❌ `gpe: "[[id/gpe/uuid]]"` → ✅ `gpe: "[[/id/gpe/uuid]]"`  
❌ `interval: ../1942-04-24` → ✅ `interval: ..1942-04-24` (EDTF correct)  
❌ Note vide ou < 20 mots → ✅ Minimum 20 mots  
❌ Fiche sans appellation → ✅ Au moins 1 bloc NAME/ORGNAME/GPENAME  
❌ ORG/GPE : 2+ appellations variantes → ✅ 1 bloc + aliases  
❌ `organization: [[/id/person/uuid]]` → ✅ `organization: [[/id/org/uuid]]`  
❌ PROFREL pour interaction simple → ✅ Hiérarchie explicite uniquement  
❌ is_part_of répété corps → ✅ frontmatter uniquement (warning automatique)  
❌ Provenance manquante structure → ✅ Blocage en strict_mode

---

## 12. CHANGELOG COMPLET

**v2.5 (2025-10-08):**

- Règles anti-redondance : Section 13.1 fusionnée avec 7.3 et 8.3
- Seuils saturation : 5 appellations, 10 occupations, 8 relations (Section 13.2)
- Note principale stable : Ne jamais accumuler mentions linéaires (Section 13.3)
- Processus curation : Consolidation périodique tous les 20-30 sources (Section 13.4)
- Validation automatisée : Script `validate_entities.py` documenté (Section 14)
- **Relations professionnelles restrictives** : Section 6.6 - hiérarchie explicite uniquement
- **Occupation organization** : Section 6.4 - ORG employeur jamais PERSON
- Workflow validation : Console + rapport Markdown
- Checklist actualisée avec nouvelles règles

**v2.4 (2025-10-08):**

- EDTF corrigé : `../date` → `..date` partout (alignement Architecture Neo4j v1.5)
- Règle appellations obligatoires : Au moins 1 bloc pour toute fiche vide
- Note minimale : 20 mots minimum (Notice biographique PERSON, Note ORG/GPE)
- Tous exemples mis à jour avec EDTF correct

**v2.3 (2025-10-06):**

- `prefLabel_fr/de` : validation souple (signalement si manquants)
- `is_part_of` : contrôle explicite automatique si présent dans le corps
- Provenance obligatoire : blocage en mode strict pour structures réifiées
- `organization_context` : clarification qu'il n'induit plus de relation
- Syntaxe wikilinks : validation automatisée frontmatter documentée

**v2.2 (2025-10-05):**

- Ajout champ `status: active/provisional/deprecated` (retiré en v2.3)
- is_part_of: frontmatter UNIQUEMENT (suppression duplication corps)
- Note vide → status provisional OBLIGATOIRE
- Liens internes: / initial systématique
- Clarification syntaxe: tags SANS guillemets, liens frontmatter AVEC guillemets

**v2.1 (2025-10-05):**

- Métadonnées frontmatter détaillées
- Standardisation vocabulaires #namespace/terme

---

## 13. RÈGLES ANTI-REDONDANCE ET SATURATION

### 13.1 Déduplication des appellations

**Note :** Cette section a été fusionnée avec sections 7.3 (ORG) et 8.3 (GPE). Les règles anti-multiplication sont maintenant documentées directement dans les sections concernées.

### 13.2 Seuils de saturation

**Objectif** : Éviter l'explosion du nombre de blocs par fiche.

#### Seuils par type de bloc

|Type|Seuil|Action si dépassé|
|---|---|---|
|NAME/ORGNAME/GPENAME|5|Signaler, demander confirmation avant ajout|
|Occupations (OCC)|10|Signaler saturation, validation humaine recommandée|
|Relations pro (PROFREL)|8|Idem|
|Relations familiales (FAMREL)|8|Idem|
|Origines (ORIG)|5|Idem|

#### Détection automatique

Le script `validate_entities.py` détecte automatiquement les fiches saturées et génère des warnings.

**Message type** :

```
⚠️  /id/org/legation-berlin : 12 appellations (seuil: 5)
→ Revue humaine recommandée
```

### 13.3 Note principale : éviter l'accumulation

**Anti-pattern** : Note qui devient une liste de 50 mentions

```yaml
# ❌ MAUVAIS
note: |
  Mentionné dans [[source-001]] pour suivi cas Müller.
  Mentionné dans [[source-003]] pour arrestation Dupont.
  Mentionné dans [[source-007]] pour échange prisonniers.
  [... 47 autres lignes identiques ...]
```

**Pattern correct** : Note synthétique organisée par thème

```yaml
# ✅ BON
note: |
  Représentation diplomatique suisse à Berlin durant la Seconde Guerre mondiale.
  
  Rôle principal: Coordination assistance ressortissants suisses en Allemagne,
  liaison avec autorités allemandes pour cas de prisonniers et détenus.
  
  Cas documentés: Müller Elisabeth (1941-1943), Dupont Jean (1942), [...].
  
  Période activité: 1920-1945 (fermeture mai 1945).
  
  Sources: 23 documents couvrant période 1940-1945.
```

**Règle** : La Note principale ne doit JAMAIS être modifiée lors de l'enrichissement (sauf si < 20 mots). Elle reste une synthèse high-level stable.

### 13.4 Processus de curation périodique

**Fréquence recommandée** : Tous les 20-30 sources enrichies

**Actions** :

1. **Identifier fiches saturées** (via `validate_entities.py`)
2. **Consolidation manuelle** :
    - Fusionner appellations redondantes
    - Renumérorer RID si nécessaire (exception à la règle)
    - Arbitrer contradictions
    - Hiérarchiser informations (principal vs secondaire)
3. **Documenter** :
    
    ```yaml
    ## Historique consolidation### Consolidation 2025-10-15- Fusionné 12 appellations redondantes → 3 variantes réelles- Note restructurée : 2100 chars → 450 chars (synthèse)- Résolu 3 contradictions dates (privilégié sources primaires)- RID renumérotés : .001-.043 → .001-.031
    ```
    

---

## 14. VALIDATION AUTOMATISÉE

### 14.1 Script de validation

**Outil** : `validate_entities.py`

**Usage** :

```bash
# Validation normale
python validate_entities.py --vault /path/to/vault

# Mode strict (warnings → errors)
python validate_entities.py --vault /path/to/vault --strict

# Avec rapport détaillé Markdown
python validate_entities.py --vault /path/to/vault --report validation_report.md
```

### 14.2 Détections

#### Erreurs critiques (bloquantes)

- Wikilinks sans `/` initial
- EDTF incorrect (`../` au lieu de `..`)
- Vocabulaires hors liste autorisée
- Tags entre guillemets
- Frontmatter invalide ou incomplet
- Provenance manquante (mode strict)

#### Warnings (à corriger)

- Notice biographique / Note < 20 mots
- Fiche sans appellation
- RID non séquentiels
- Appellations potentiellement redondantes
- Saturation (≥ seuils définis)
- Note > 3000 caractères

### 14.3 Workflow recommandé

```
1. Enrichissement via LLM
   ↓
2. Validation : python validate_entities.py --vault ./ --report rapport.md
   ↓
3. Correction des erreurs identifiées
   ↓
4. Re-validation jusqu'à 0 erreurs
   ↓
5. Export Neo4j : python master_import.py
```

### 14.4 Rapport de validation

**Format console** :

```
📊 Analyse de 152 fiches...

======================================================================
RAPPORT DE VALIDATION
======================================================================

📊 Statistiques:
  - Fiches analysées : 152
    • PERSON : 87
    • ORG : 42
    • GPE : 23

  - Erreurs : 3
  - Warnings : 12

🔍 Détails par catégorie:
  WIKILINK: 2 erreurs
  EDTF: 1 erreur
  SATURATION: 5 warnings

======================================================================
✅ VALIDATION RÉUSSIE - Prêt pour export Neo4j
======================================================================
```

**Format Markdown** (si `--report` spécifié) :

- Liste exhaustive des erreurs par catégorie
- Fichier, ligne, message, détail
- Limité à 50 erreurs par catégorie pour lisibilité

---

FIN DOCUMENTATION v2.5
