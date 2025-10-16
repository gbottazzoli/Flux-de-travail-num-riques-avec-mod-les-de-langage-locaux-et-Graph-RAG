# DOCUMENTATION EXTRACTION v2.6 - SCHÉMA COMPLET

*Dernière mise à jour : 2025-10-06*

## 1. STRUCTURE GÉNÉRALE

### 1.1 Types d'entrées

Deux types principaux :

**Micro-actions** : Actions administratives, diplomatiques, logistiques
- Identifiant : `#micro_id: mic.<doc-id>-<nn>`
- Préfixe : `mic.`

**Événements de persécution** : Faits subis par la victime
- Identifiant : `#event_id: ev.<doc-id>-<nn>`
- Préfixe : `ev.`

### 1.2 Format document-id

`<doc-id>` = nom fichier source sans extension

Exemples :
- `638731157259877990-001` (fichier PDF)
- `638731157047951088-003` (fichier PDF)

### 1.3 Numérotation séquentielle

`<nn>` = numéro séquentiel 01, 02, 03...

Indépendant entre micro-actions et événements :
- `mic.638731157259877990-001-01`, `mic.638731157259877990-001-02`...
- `ev.638731157259877990-001-01`, `ev.638731157259877990-001-02`...

---

## 2. SCHÉMA MICRO-ACTIONS

### 2.1 Champs obligatoires

```yaml
#micro_id: mic.<doc-id>-<nn>

# === CLASSIFICATION ===
- tags: #microAction/<catégorie>/<sous-catégorie>
- action_type: <type_action>
- link_type: #link_type/<modalité>
- delivery_channel: #delivery_channel/<canal>

# === ACTEURS ===
- actor: [[/id/org/<uuid>|Nom organisation]]
- recipient: [[/id/org/<uuid>|Nom organisation]] OU [[/id/person/<uuid>|Nom personne]]

# === TEMPORALITÉ ===
- date_edtf: <date_EDTF>
- date_precision: #date_precision/<précision>
- date_source: #date_source/<source>

# === FIABILITÉ ===
- confidence: #confidence/<niveau>
- evidence_type: #evidence_type/<type>

# === CONTENU ===
- description: <description_factuelle>

# === TRAÇABILITÉ ===
- source_document: [[<fichier_source>]]
- source_quote: "<citation_textuelle>"
````

### 2.2 Champs optionnels

```yaml
# === PERSONNES CONCERNÉES ===
- about: [[/id/person/<uuid>|Nom]]
  # FORTEMENT RECOMMANDÉ si micro-action concerne victime spécifique
  # L'absence d'about alors qu'une personne est mentionnée dans le texte
  # est signalée comme anomalie par le système

- on_behalf_of: [[/id/org/<uuid>|Nom]] # Si action menée au nom de

# === RÉPONSE À CORRESPONDANCE ===
- in_reply_to_date: <YYYY-MM-DD>
  # Date EDTF du courrier auquel cette micro-action répond
  # Si ABSENT et link_type = acknowledges_receipt OU replies_to,
  # le système tente extraction AUTOMATIQUE depuis le texte (voir §2.5)

# === LOCALISATION ===
- place: [[/id/gpe/<uuid>|Lieu]]
  # CRITIQUE: Toujours GPE (lieu géopolitique), jamais organisation
  # Pour visites prison: place = ville, précision dans observations

# === INFORMATIONS ADDITIONNELLES ===
- observations: <détails_contextuels>
- outcome: #outcome/<résultat> # Si résultat connu
- reported_by: [[/id/org/<uuid>|Source]] # Si evidence_type = reported
```

### 2.3 Champs textuels standards

**Les seuls champs de texte libre standard sont :**

- `description` (principal)
- `observations` (complémentaire)

**Variantes acceptées mais signalées :** `summary`, `abstract`

Le système émet un warning `non_standard_field` si ces variantes sont utilisées.

### 2.4 Taxonomie micro-actions

#### Administrative

```yaml
#microAction/administrative/correspondence    # Correspondance générale
#microAction/administrative/reporting         # Rapports, compte-rendus
#microAction/administrative/documentation     # Enregistrement, archivage
#microAction/administrative/case_assessment   # Évaluation de dossier
```

#### Diplomatique

```yaml
#microAction/diplomatic/intervention          # Démarche diplomatique
#microAction/diplomatic/representation        # Représentation officielle
#microAction/diplomatic/negotiation           # Négociation
```

#### Logistique

```yaml
#microAction/logistic/visit                   # Visite consulaire
#microAction/logistic/material_support        # Aide matérielle (colis, vivres)
#microAction/logistic/legal_support           # Assistance juridique
#microAction/logistic/financial_support       # Aide financière
```

#### Légale

```yaml
#microAction/legal/clemency_request           # Demande de grâce
#microAction/legal/legal_support              # Assistance juridique formelle
```

#### Communication

```yaml
#microAction/communication/family_contact     # Contact familial
#microAction/communication/information_transmission  # Transmission info
```

### 2.5 Détection automatique de la date ancre

**Déclenchement automatique :** Quand `link_type ∈ {acknowledges_receipt, replies_to}` ET `in_reply_to_date` est absent.

Le parseur recherche dans `description` / `observations` des motifs linguistiques :

**Allemand :**

- `Schreiben vom 1942-04-24`
- `vom 24. April 1942`
- `Telegramm Nr. 154 vom 23.04.1942`

**Français :**

- `lettre du 27 avril 1942`
- `télégramme du 23.04.1942`

**Résultat :**

- Date trouvée → Normalisation EDTF automatique (`YYYY-MM-DD`)
- Date non trouvée → Warning `reply_missing_anchor_date`

---

## 3. SCHÉMA ÉVÉNEMENTS

### 3.1 Champs obligatoires

```yaml
#event_id: ev.<doc-id>-<nn>

# === CLASSIFICATION ===
- tags: #persecution/<catégorie>/<sous-catégorie>
  # OBLIGATOIRE - L'absence est signalée
  # event_type est DÉRIVÉ AUTOMATIQUEMENT du dernier segment
  # Ex: #persecution/legal/arrest → event_type = "arrest"
  # Incohérences détectées et signalées

# === ACTEURS ===
- victim: [[/id/person/<uuid>|Nom victime]]

- agent: [[/id/org/<uuid>|Nom autorité]] OU UNKNOWN_AUTHORITY
  # Format UNKNOWN_AUTHORITY : valeur littérale SANS wikilink
  # Syntaxes fautives fréquentes tolérées mais signalées

- agent_role: #<rôle>

# === LOCALISATION ===
- place: [[/id/gpe/<uuid>|Lieu]] OU [[/id/org/<uuid>|Prison/Camp]]
  # Pour détention/emprisonnement: préférer organisation prison
  # Pour autres événements: GPE

# === TEMPORALITÉ ===
- date_edtf: <date_EDTF>
- date_precision: #date_precision/<précision>
- date_source: #date_source/<source>

# === FIABILITÉ ===
- confidence: #confidence/<niveau>
- evidence_type: #evidence_type/<type>

# === CONTENU ===
- description: <description_factuelle>

# === TRAÇABILITÉ ===
- source_document: [[<fichier_source>]]
- source_quote: "<citation_textuelle>"
  # L'absence est signalée
```

### 3.2 Sections textuelles (reconnaissance flexible)

**Description** et **Observations** — Headers acceptés :

```
**Description**
**Description:**
**Description :**
**DESCRIPTION**        # Casse tolérée
```

```
**Observations**
**Observation:**       # Singulier toléré
**Observations :**
**OBSERVATIONS**
```

Le système reconnaît ces variations automatiquement.

### 3.3 Champs optionnels

```yaml
# === PRÉCISIONS AGENT ===
- agent_precision: <précision_textuelle> # Si UNKNOWN_AUTHORITY

# === LOCALISATION COMPLÉMENTAIRE ===
- place_precision: <précision_lieu>
- to_place: [[/id/gpe/<uuid>|Destination]] # Pour transferts
- place: [[/id/gpe/<uuid>|Origine]] # Pour transferts

# === INFORMATIONS ADDITIONNELLES ===
- observations: <détails_contextuels>
- conditions: [<liste_conditions>] # Conditions détention/procès
- reported_by: [[/id/org/<uuid>|Source]] # Si evidence_type = reported
```

### 3.4 Taxonomie événements

#### Arrestation & Détention

```yaml
#persecution/legal/arrest                     # Arrestation
#persecution/detention/imprisonment           # Emprisonnement général
#persecution/detention/zuchthaus              # Bagne (Zuchthaus)
#persecution/detention/concentration_camp     # Camp de concentration
#persecution/detention/internment             # Internement
```

#### Procédure judiciaire

```yaml
#persecution/legal/charge                     # Inculpation générale
#persecution/legal/charge/espionage           # Espionnage
#persecution/legal/charge/treason             # Trahison
#persecution/legal/charge/currency_smuggling  # Contrebande de devises
#persecution/legal/charge/illegal_border_crossing  # Franchissement illégal frontière

#persecution/legal/sentence/death             # Condamnation à mort
#persecution/legal/sentence/prison            # Condamnation prison
#persecution/legal/sentence/forced_labor      # Travaux forcés

#persecution/legal/clemency/commutation       # Commutation de peine
#persecution/legal/clemency/pardon            # Grâce totale

#persecution/legal/liberation                 # Libération
```

#### Déplacement

```yaml
#persecution/displacement/transfer            # Transfert entre lieux détention
#persecution/displacement/deportation         # Déportation
#persecution/displacement/expulsion           # Expulsion
```

#### Violence & Conditions

```yaml
#persecution/violence/physical_abuse         # Violences physiques
#persecution/violence/torture                # Torture
#persecution/violence/execution              # Exécution

#persecution/conditions/deprivation          # Privations
#persecution/conditions/forced_labor         # Travail forcé
#persecution/conditions/isolation            # Isolement
```

---

## 4. VOCABULAIRES CONTRÔLÉS

### 4.1 agent_role (rôle autorité - événements)

```yaml
#arresting      # Autorité ayant procédé à l'arrestation
#charging       # Autorité ayant porté l'accusation/inculpation, OBLIGATOIRE pour tous tags #persecution/legal/charge/*
#detaining      # Autorité détentrice (prison, camp)
#sentencing     # Autorité ayant prononcé la sentence
#clemency       # Autorité ayant accordé grâce/commutation
#transferring   # Autorité ayant organisé le transfert
#executing      # Autorité ayant procédé à l'exécution
#liberating     # Autorité/force ayant procédé à la libération [NEW v2.4]
```

**Usage #liberating** : Forces militaires libératrices (troupes alliées, soviétiques), autorités ayant ordonné libération, événements armistice.

### 4.2 link_type (modalité communicationnelle - micro-actions)

```yaml
#link_type/informs               # Information, avis, notification
#link_type/requests              # Demande, sollicitation
#link_type/forwards              # Relai, transmission de documents
#link_type/acknowledges_receipt  # Accusé de réception explicite
#link_type/summarizes            # Synthèse, rapport récapitulatif
#link_type/supports              # Action de soutien direct
#link_type/replies_to            # Réponse à correspondance
```

### 4.3 delivery_channel (canal transmission - micro-actions)

```yaml
#delivery_channel/letter              # Courrier postal
#delivery_channel/telegram            # Télégramme
#delivery_channel/phone               # Téléphone
#delivery_channel/in_person           # En personne (visite, entretien)
#delivery_channel/physical_delivery   # Livraison matérielle (colis, vivres)
#delivery_channel/unknown             # Canal non spécifié dans source
```

### 4.4 confidence (certitude linguistique)

```yaml
#confidence/high       # Formulation certaine, factuelle
                       # Exemples: "a été condamnée", "est détenue", "le tribunal a prononcé"

#confidence/medium     # Formulation neutre, rapportée
                       # Exemples: "indique que", "rapporte que", "selon"

#confidence/low        # Incertitude, modalisation
                       # Exemples: "aurait", "semble-t-il", "probablement", "vraisemblable"
                       # Allemand: "soll", "dem Vernehmen nach", "scheint"
                       # Format tag accepté: #confidence/low
```

**Normalisation automatique :** Le système accepte `low`, `#confidence/low`, avec gestion casse/espaces.

### 4.5 evidence_type (mode obtention information)

#### Sources contemporaines (1940-1945)

```yaml
#evidence_type/direct_observation           
# Document administratif/judiciaire direct produit par autorité compétente
# Exemples: jugement, ordre transfert, registre prison

#evidence_type/victim_statement             
# Paroles directes de la victime (lettre, témoignage contemporain)

#evidence_type/reported                     
# Information rapportée par tiers fiable (consulat, avocat, témoin)
# Requiert champ reported_by

#evidence_type/interpreted                  
# Déduction, hypothèse, prédiction contemporaine
# Exemple: "Il est vraisemblable que la peine sera commuée"

#evidence_type/observation_only             
# Mention indirecte, indice faible, rumeur non confirmée
```

#### Sources post-guerre (1945+)

```yaml
#evidence_type/postwar_summary              
# Formulaires, rapports administratifs établis après 1945
# Reconstitution rétrospective par autorités

#evidence_type/postwar_victim_testimony     
# Témoignage victime après libération/guerre
# Récit rétrospectif direct

#evidence_type/administrative_review        
# Réévaluation administrative tardive (ex: commission 1962)
# Analyse dossier pour indemnisation/réparation

#evidence_type/oral_testimony               
# Témoignage oral postérieur non structuré

#evidence_type/institutional_reconstruction 
# Reconstitution institutionnelle (archives, enquêtes)
```

### 4.6 date_precision (précision temporelle)

```yaml
#date_precision/day        # Jour exact connu
#date_precision/month      # Mois exact, jour inconnu
#date_precision/year       # Année exacte, mois inconnu
#date_precision/interval   # Intervalle délimité
#date_precision/circa      # Date approximative (~)
#date_precision/uncertain  # Date incertaine (?)
#date_precision/before     # Borne ouverte avant (../)
#date_precision/after      # Borne ouverte après (/..
#date_precision/unknown    # Date inconnue (../..)
```

### 4.7 date_source (source datation)

```yaml
#date_source/document_date    # Date du document source
#date_source/explicit         # Date explicite dans texte
#date_source/inferred         # Date déduite du contexte
#date_source/imputed          # Date imputée (approximation)
```

### 4.8 outcome (résultat - micro-actions optionnel)

```yaml
#outcome/granted     # Demande accordée
#outcome/refused     # Demande refusée
#outcome/pending     # En attente de décision
#outcome/unknown     # Résultat non documenté
```

### 4.9 conditions (conditions détention - événements optionnel)

```yaml
legal_representation    # Assistance avocat
family_contact         # Contact familial autorisé
correspondence        # Correspondance autorisée
packages             # Colis autorisés
isolation            # Isolement cellulaire
forced_labor         # Travail forcé imposé
inadequate_food      # Alimentation insuffisante
inadequate_medical   # Soins médicaux insuffisants
```

---

## 5. RÈGLES EDTF (Extended Date/Time Format)

### 5.1 Dates exactes

```yaml
date_edtf: 1942-04-27           # 27 avril 1942
date_edtf: 1942-04              # Avril 1942 (jour inconnu)
date_edtf: 1942                 # Année 1942 (mois inconnu)
```

### 5.2 Intervalles

```yaml
date_edtf: 1942-04-15/1942-04-27    # Du 15 au 27 avril 1942
date_edtf: 1941-03/1942-03          # De mars 1941 à mars 1942
date_edtf: 1942/1945                # De 1942 à 1945
```

### 5.3 Bornes ouvertes

```yaml
date_edtf: ../1942-04-27            # Avant le 27 avril 1942 (borne fin connue)
date_edtf: 1942-04-27/..            # Après le 27 avril 1942 (borne début connue)
date_edtf: ../..                    # Date totalement inconnue (éviter)
```

### 5.4 Dates approximatives

```yaml
date_edtf: 1942~                    # Environ 1942
date_edtf: 1942-04~                 # Environ avril 1942
```

### 5.5 Incertitude

```yaml
date_edtf: 1942?                    # 1942 incertain
date_edtf: 1942-04?                 # Avril 1942 incertain
```

### 5.6 Dérivation automatique (SYSTÈME)

> **Règle transversale :** `date_precision` est **TOUJOURS dérivée automatiquement** depuis la chaîne EDTF par le système d'import.
> 
> - `"1942"` → `date_precision = "year"`
> - `"1942~"` → `date_precision = "circa"`
> - `"1942-04-27"` → `date_precision = "day"`
> - `"1942/1945"` → `date_precision = "interval"`
> 
> Elle n'est **jamais fournie manuellement** et est stockée avec `date_start`/`date_end` pour permettre des requêtes temporelles précises dans Neo4j.

---

## 6. CAS SPÉCIAUX & EXEMPLES

### 6.1 Visites consulaires/humanitaires [CRITIQUE v2.4]

**RÈGLE ABSOLUE** : Le champ `place` attend un **GPE** (lieu géopolitique), JAMAIS une organisation.

#### ❌ Incorrect

```yaml
#micro_id: mic.visit-01
- tags: #microAction/logistic/visit
- actor: [[/id/org/consulat_paris]]
- recipient: [[/id/person/mueller]]
- place: [[/id/org/prison_cherche_midi]]  # ERREUR
- date_edtf: 1942-04-15
```

#### ✅ Correct

```yaml
#micro_id: mic.visit-01
- tags: #microAction/logistic/visit
- actor: [[/id/org/consulat_paris]]
- recipient: [[/id/person/mueller]]
- place: [[/id/gpe/paris]]  # GPE ville
- date_edtf: 1942-04-15
- observations: "Visite à la prison Cherche-Midi. L'intéressée ne paraissait pas avoir trop souffert de sa longue détention."
```

**Exception camps isolés** : Prison/camp géographiquement isolé (zone rurale, camp concentration) → GPE région/ville proche.

```yaml
place: [[/id/gpe/thuringia]]
observations: "Visite au camp de Buchenwald"
```

---

### 6.2 Rapports synthétiques multi-victimes

**Situation** : Document mentionnant N cas distincts (N ≥ 3 victimes).

**Stratégie** : Créer UNE micro-action `#microAction/administrative/reporting` synthétisant les N cas + micro-actions séparées pour actions distinctes (transmission, demandes).

#### Exemple

Document : "Rapport sur 8 arrestations de ressortissants suisses à Paris. Transmission liste nominative jointe. Demandons instructions urgentes."

```yaml
#micro_id: mic.rapport-01
- tags: #microAction/administrative/reporting
- action_type: reporting
- link_type: #link_type/informs
- description: "Rapport synthétique sur 8 arrestations de ressortissants suisses à Paris par autorités allemandes."
- observations: "Détails nominatifs: [liste si pertinent pour contexte]"

---

#micro_id: mic.rapport-02
- tags: #microAction/administrative/correspondence
- action_type: correspondence
- link_type: #link_type/forwards
- description: "Transmission de la liste nominative des 8 personnes arrêtées."

---

#micro_id: mic.rapport-03
- tags: #microAction/administrative/correspondence
- action_type: correspondence
- link_type: #link_type/requests
- description: "Demande d'instructions urgentes concernant les 8 arrestations."
```

**Total** : 3 micro-actions (pas 8+)

---

### 6.3 Événements hypothétiques/prédictifs

**Situation** : Source contemporaine contient prédiction, hypothèse, estimation future.

**Exemple texte** : "Il est vraisemblable cependant que la peine de mort infligée à l'intéressée sera commuée en peine de réclusion."

```yaml
#event_id: ev.prediction-01
- tags: #persecution/legal/clemency/commutation
- victim: [[/id/person/mueller]]
- agent: [[UNKNOWN_AUTHORITY]]
- agent_role: #clemency
- agent_precision: "Autorité allemande compétente pour grâce"
- date_edtf: 1942-04-22/..            # Borne ouverte (événement futur)
- date_precision: #date_precision/interval
- date_source: #date_source/inferred
- confidence: #confidence/low          # Incertitude linguistique
- evidence_type: #evidence_type/interpreted  # Hypothèse/prédiction
- description: "Commutation anticipée de la peine de mort en peine de réclusion pour Müller Elisabeth, jugée vraisemblable par l'interlocuteur consulaire."
- observations: "Événement ANTICIPÉ, pas encore accompli au moment de la note. Source utilise le futur 'sera commuée' et qualifie cela de 'vraisemblable'."
```

**Clés** :

- `confidence: #confidence/low` (modalisation)
- `evidence_type: #evidence_type/interpreted` (hypothèse)
- `observations` : préciser caractère prédictif

---

### 6.4 Informations contradictoires évolutives

**Situation** : Documents successifs donnent informations contradictoires (ex: raisons arrestation évoluent).

**Principe** : Créer événements DISTINCTS reflétant évolution connaissance, PAS fusion/correction.

#### Exemple

- **Doc 1941-09** : "Arrêtée pour contrebande de devises"
- **Doc 1942-04** : "Condamnée pour espionnage"

```yaml
#event_id: ev.charge-01
- tags: #persecution/legal/charge/currency_smuggling
- victim: [[/id/person/mueller]]
- date_edtf: ../1941-09-16
- description: "Müller Elisabeth arrêtée pour contrebande de devises par les autorités allemandes à Paris."
- confidence: #confidence/medium
- evidence_type: #evidence_type/reported
- reported_by: [[/id/org/consulat_paris]]

---

#event_id: ev.sentence-01
- tags: #persecution/legal/sentence/death
- victim: [[/id/person/mueller]]
- date_edtf: 1942-03-30
- description: "Condamnation à mort pour espionnage par tribunal militaire allemand."
- confidence: #confidence/high
- evidence_type: #evidence_type/reported
- reported_by: [[/id/org/consulat_paris]]
```

**Résultat graphe** : 2 nœuds distincts montrant évolution/rectification accusation. Ne PAS supprimer currency_smuggling.

---

### 6.5 Chaînage correspondances

**Détecter mentions courriers antérieurs** :

- Allemand : "Bezugnahme auf", "im Nachgang zu", "Ich beziehe mich auf"
- Français : "suite à votre lettre du", "Votre lettre du", "J'ai l'honneur de me référer"

**Action** : Créer micro-action `#link_type/acknowledges_receipt` OU `#link_type/replies_to`

#### Exemple

Texte : "Ich beziehe mich auf Ihr Telegramm Nr. 154 vom 23. April 1942..."

```yaml
#micro_id: mic.ack-01
- tags: #microAction/administrative/correspondence
- action_type: correspondence
- link_type: #link_type/acknowledges_receipt
- delivery_channel: #delivery_channel/letter  # Document actuel
- actor: [[/id/org/gesandtschaft_berlin]]
- recipient: [[/id/org/abteilung_bern]]
- date_edtf: 1942-04-27
- in_reply_to_date: 1942-04-23  # Date extraite automatiquement si absente
- description: "Accusé de réception du télégramme n°154 du 23 avril 1942 concernant le cas Müller Elisabeth."
- source_quote: "Ich beziehe mich auf Ihr Telegramm Nr. 154 vom 23. April 1942"
```

**Note :** Si `in_reply_to_date` absent, le système extrait "23. April 1942" automatiquement.

---

### 6.6 Documents post-guerre (1958-1962)

**Caractéristiques** : Notes internes, rapports indemnisation, commissions réparations.

**Règles spécifiques** :

- `evidence_type: #evidence_type/postwar_summary` OU `#evidence_type/administrative_review`
- `confidence` : évaluer selon formulation (souvent `#confidence/high` car document officiel)
- Multiplier événements si synthèse reconstitue parcours complet

#### Exemple

Document 1958 : "Note sur le cas Müller Elisabeth. Arrêtée 29 mars 1941. Détenue Cherche-Midi puis La Santé. Condamnée à mort 30 mars 1942. Transférée Allemagne 27 avril 1942..."

**Extraction** : 13 événements distincts (1 par fait reconstitué) + micro-actions administratives.

```yaml
#event_id: ev.postwar-01
- tags: #persecution/legal/arrest
- victim: [[/id/person/mueller]]
- date_edtf: 1941-03-29
- confidence: #confidence/high
- evidence_type: #evidence_type/postwar_summary  # Source 1958
- description: "Arrestation d'Elisabeth Müller par les Allemands à Paris pour soupçon d'espionnage suite à un voyage en Suisse."
```

### 6.7 Lieux de détention - Format obligatoire

**RÈGLE CRITIQUE** : Événements de détention doivent pointer vers ORGANISATION (prison/camp).

#### ❌ Incorrect

```yaml
tags: #persecution/detention/imprisonment
place: [[/id/gpe/paris]]  # GPE ville
```

#### ✅ Correct

```yaml
tags: #persecution/detention/imprisonment
place: [[/id/org/prison_cherche_midi]]  # Organisation prison
```

**Si prison non identifiable** :

```yaml
place: [[/id/org/placeholder_prison_paris]]
agent_precision: "Prison non identifiée à Paris"
observations: "Mention dans source : 'détenu à Paris'"
```

---

## 7. RÈGLES DE FUSION/SÉPARATION

### 7.1 Fusion micro-actions AUTORISÉE si

Toutes les conditions réunies :

- ✅ Même `actor`
- ✅ Même `recipient`
- ✅ Même `delivery_channel`
- ✅ Même `link_type`
- ✅ Même document source
- ✅ Contenus liés sémantiquement

#### Exemple fusion correcte

Télégramme : "Décision finale cas Müller dépend OKW Berlin stop. Intéressée transférée Allemagne lundi 27 avril stop."

```yaml
#micro_id: mic.telegram-01
- tags: #microAction/administrative/reporting
- link_type: #link_type/informs
- delivery_channel: #delivery_channel/telegram
- description: "Le Consulat de Paris informe que la décision finale concernant Müller Elisabeth dépend exclusivement de l'O.K.W. Berlin et que l'intéressée a été transférée en Allemagne le lundi 27 avril."
```

**Justification** : Même télégramme, même link_type, contenus liés (statut procédure + transfert).

---

### 7.2 Séparation micro-actions OBLIGATOIRE si

**L'une des conditions diffère** :

- ❌ `link_type` différents (#informs vs #requests)
- ❌ `delivery_channel` différents (lettre vs télégramme joint)
- ❌ `recipient` différents

#### Exemple séparation correcte

Lettre : "Nous vous informons de la condamnation. Nous demandons vos instructions."

```yaml
#micro_id: mic.letter-01
- link_type: #link_type/informs
- description: "Information sur la condamnation à mort de Müller Elisabeth."

---

#micro_id: mic.letter-02
- link_type: #link_type/requests
- description: "Demande d'instructions concernant les démarches à entreprendre."
```

**Justification** : `link_type` différents (#informs ≠ #requests) → séparation obligatoire.

---

## 8. TRAÇABILITÉ & CITATIONS

### 8.1 source_document

**Format** : `[[<nom_fichier_sans_extension>]]`

Exemples :

- `[[638731157259877990-001.pdf]]`
- `[[rapport_consulat_1942-04-15.pdf]]`

**Règle** : Identique pour tous extraits d'un même document.

**L'absence est signalée** par le système (`missing_source_document`).

---

### 8.2 source_quote

**Règle** : Citation textuelle EXACTE du passage source justifiant l'extraction.

**Format** : Entre guillemets doubles `"..."`

**Longueur** : 10-50 mots (essentiel, pas phrases complètes nécessairement)

**Exemples** :

```yaml
source_quote: "Ich beziehe mich auf Ihr Telegramm Nr. 154 vom 23. April 1942"

source_quote: "par un jugement du 30 mars, Müller Elisabeth a été condamnée à mort sous l'inculpation d'espionnage"

source_quote: "intéressée transférée en Deutschland lundi vingtsept avril"
```

**Interdiction** : Paraphrase, résumé, traduction. Toujours texte original.

**L'absence est signalée** pour les événements (`events_missing_quote`).

---

## 9. VALIDATION & WARNINGS SYSTÈME

### 9.1 Warnings automatiques

Le système d'import émet des warnings pour :

**Wikilinks :**

- `invalid_wikilinks_ignored` — UUID malformé, type inconnu
- `wikilinks_slash_auto_corrected` — `/` manquant corrigé automatiquement
- `frontmatter_unquoted_link` — Wikilinks FM sans guillemets

**Taxonomie :**

- `events_missing_tags` — Event sans taxonomie complète
- `event_type_conflict` — Incohérence tags vs event_type manuel

**Provenance :**

- `events_missing_quote` — Event sans source_quote
- `structure_missing_provenance` — Structure réifiée sans provenance

**Micro-actions :**

- `reply_missing_anchor_date` — AR/Reply sans in_reply_to_date
- `in_reply_to_date_extracted` — Date ancre extraite automatiquement (info)
- `microaction_missing_about` — Personne mentionnée sans about
- `missing_source_document` — Micro-action sans source_document

**Entités :**

- `is_part_of_in_body` — is_part_of détecté dans corps (devrait être FM uniquement)
- `entity_unlinked` — Actor/recipient non lié (string libre toléré)

---

## 10. CHECKLIST VALIDATION PRÉ-SOUMISSION

### 10.1 Validation structurelle

- [ ] Tous les highlights ont une entrée YAML correspondante ?
- [ ] Numérotation séquentielle correcte (01, 02, 03...) ?
- [ ] Aucun doublon `#micro_id` ou `#event_id` ?
- [ ] Tous les champs obligatoires présents ?

### 10.2 Validation sémantique

- [ ] `agent_role` cohérent avec `tags` événement ?
- [ ] `link_type` justifie fusion/séparation micro-actions ?
- [ ] `place` = GPE pour visites (pas organisation) ?
- [ ] `reported_by` présent si `evidence_type: #evidence_type/reported` ?
- [ ] Libérations : `agent_role: #liberating` (pas #executing) ?
- [ ] `about` présent si victime spécifique mentionnée ?

### 10.3 Validation temporelle

- [ ] `date_edtf` syntaxe EDTF valide ?
- [ ] `date_precision` laissé vide (dérivation automatique) ?
- [ ] `date_source` reflète réalité extraction ?
- [ ] Intervalles ouverts utilisés correctement (`../`, `/..`) ?

### 10.4 Validation vocabulaires

- [ ] Tous les tags existent dans taxonomie officielle ?
- [ ] `confidence` approprié à formulation source ?
- [ ] `evidence_type` distingue sources contemporaines vs post-guerre ?
- [ ] Aucun terme inventé sans proposition formelle ?

### 10.5 Validation traçabilité

- [ ] `source_document` présent et correct ?
- [ ] `source_quote` exact (copier-coller source) ?
- [ ] Citations entre guillemets doubles ?
- [ ] Longueur citation raisonnable (10-50 mots) ?

---

## 11. GOUVERNANCE TAXONOMIQUE

### 11.1 Principe défensif

**Utiliser PRIORITAIREMENT termes existants** de la taxonomie officielle v2.6.

Si aucun terme existant ne convient :

1. ⛔ STOP extraction
2. 📝 Proposer nouveau terme avec justification
3. ⏸️ Attendre validation
4. ✅ Une fois validé → intégrer doc + continuer

### 11.2 Format proposition

```yaml
# TAXONOMIE - PROPOSITION NOUVEAU TERME

Section: [#microAction/... ou #persecution/... ou agent_role/...]
Terme proposé: <terme>
Niveau hiérarchique: #<chemin_complet>

Justification: 
<Distinction sémantique claire vs termes existants>

Cas d'usage: 
<Exemple concret du document justifiant besoin>

Alternatives existantes analysées:
- #terme_proche_1 : pourquoi insuffisant
- #terme_proche_2 : pourquoi insuffisant

Fréquence estimée: [unique / rare / récurrent]
```

### 11.3 Critères acceptation

✅ **Accepter si** :

- Distinction sémantique CLAIRE vs termes existants
- Réutilisable (pas cas unique)
- S'insère logiquement dans hiérarchie
- Comble lacune réelle taxonomie

❌ **Refuser si** :

- Synonyme terme existant
- Cas unique/marginal
- Peut être exprimé via `observations`
- Granularité excessive (sur-spécification)

---

## 12. GLOSSAIRE TECHNIQUE

**GPE** : Geo-Political Entity (entité géopolitique) - ville, région, pays  
**EDTF** : Extended Date/Time Format (format dates étendu ISO)  
**UUID** : Identifiant unique entité dans vault Obsidian  
**Link_type** : Modalité communicationnelle d'une micro-action  
**Agent_role** : Rôle fonctionnel autorité dans événement  
**Evidence_type** : Mode d'obtention information (directe, rapportée, post-guerre...)  
**Confidence** : Degré certitude linguistique formulation source  
**Highlight** : Marquage texte source `==...==%%annotation%%`  
**Warning** : Signal automatique anomalie/non-conformité détecté par système

---

## CHANGELOG v2.6

**Ajouts majeurs :**

- `in_reply_to_date` avec détection automatique depuis texte (§2.2, §2.5)
- Dérivation `event_type` depuis `tags` avec détection incohérences (§3.1)
- `UNKNOWN_AUTHORITY` formalisé sans wikilink (§3.1)
- Clarification champs textuels standards vs variantes (§2.3)
- Précision EDTF : dérivation automatique `date_precision` (§5.6)
- Section complète warnings système (§9.1)
- `about` fortement recommandé avec warning si personne mentionnée (§2.2)

**Corrections :**

- Reconnaissance flexible headers Description/Observations (§3.2)
- Formats `confidence` multiples acceptés (#confidence/low, low) (§4.4)

---

## CONTACTS & MISES À JOUR

**Version courante** : 2.6  
**Dernière mise à jour** : 2025-10-06  
**Prochaine révision** : Sur besoin (propositions taxonomie)

---

FIN DOCUMENTATION v2.6
