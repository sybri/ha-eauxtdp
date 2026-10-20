# Eaux Terre de Provence — Intégration Home Assistant (`eauxtdp`)

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![Validate](https://github.com/sybri/ha-eauxtdp/actions/workflows/validate.yml/badge.svg)](https://github.com/sybri/ha-eauxtdp/actions/workflows/validate.yml)
[![GitHub Release](https://img.shields.io/github/v/release/sybri/ha-eauxtdp)](https://github.com/sybri/ha-eauxtdp/releases)

Intégration personnalisée (**HACS**) pour **Home Assistant** permettant de suivre sa consommation d'eau quotidienne (télérelève Birdz / compteur ITRON), ses tarifs réels au m³, ses factures et ses échéanciers SEPA depuis le portail abonné de la **Régie des Eaux de Terre de Provence** ([portail.eauxtdp.fr](https://portail.eauxtdp.fr) — basé sur la solution *JVS-Mairistem iClients*).

---

## Fonctionnalités principales

- **Télérelève quotidienne** : Récupération automatique des index journaliers en **Litres** et en **m³**, ainsi que de la consommation de la dernière journée relevée.
- **Injection rétroactive dans le Dashboard Énergie (`async_add_external_statistics`)** :
  - Comme la télérelève radio Birdz remonte avec un décalage de 24h à 72h, l'intégration injecte automatiquement chaque consommation quotidienne **à sa date réelle (`dateni` à 02h00)** dans les statistiques long-terme de Home Assistant (`eauxtdp:water_consumption_<contrat_id>` et `eauxtdp:water_cost_<contrat_id>`).
  - Au premier démarrage, l'historique complet des **365 derniers jours** est importé automatiquement.
- **Calcul du tarif réel de l'eau (correction du bug API `POICL_Price`)** :
  - L'objet interne `POICL_Price` de l'API renvoie une estimation erronée (`8,24 €/m³`).
  - L'intégration calcule dynamiquement les **2 tarifs réels TTC** à partir de vos factures et de la grille tarifaire 2026 :
    1. **Prix Eau Variable TTC (hors abonnement)** : `~3,727 €/m³` (`(Facture TTC - Abonnement annuel 81,89 €) / m³ facturés`) — idéal pour suivre le coût marginal de chaque litre consommé.
    2. **Prix Eau Moyen TTC (abonnement inclus)** : `~4,492 €/m³` (`Facture TTC / m³ facturés`) — amortit l'abonnement annuel (`81,89 €/an`) sur votre consommation.
- **Suivi de facturation & prélèvements SEPA** :
  - Montant et détails complets de la dernière facture (`HT`, `TVA`, `TTC`, `mensualités déduites`, `reste à payer`, statut soldé).
  - Montant et date du prochain prélèvement mensuel SEPA (`POICL_Hreglmnt`), nombre d'échéances restantes et cumul à venir.
- **Diagnostics & Alertes** :
  - Capteur binaire d'**alerte fuite** (`flag_alerte`, `cptfuite`).
  - Capteur binaire d'**état du compteur & télérelève** exposant le numéro de série ITRON, l'identifiant du module radio `HOMG3`, l'adresse de desserte et les coordonnées GPS.
- **Boutons & Services** :
  - `eauxtdp.refresh` : Force une actualisation immédiate.
  - `eauxtdp.import_history` : Force la récupération et la reconstruction des statistiques sur `N` jours (par défaut 365 jours).

---

## Installation

### Via HACS (Recommandé)

1. Ouvrez **HACS** dans Home Assistant.
2. Cliquez sur le menu `⋮` en haut à droite → **Dépôts personnalisés** (*Custom repositories*).
3. Ajoutez l'URL du dépôt : `https://github.com/sybri/ha-eauxtdp` avec la catégorie **Intégration** (*Integration*).
4. Recherchez **Eaux Terre de Provence** et cliquez sur **Télécharger**.
5. Redémarrez Home Assistant.

### Installation manuelle

1. Copiez le dossier `custom_components/eauxtdp` dans le répertoire `/config/custom_components/` de votre installation Home Assistant.
2. Redémarrez Home Assistant.

---

## Configuration

1. Allez dans **Paramètres** → **Appareils et services** → **Ajouter une intégration**.
2. Recherchez **Eaux Terre de Provence**.
3. Saisissez votre **adresse e-mail** et votre **mot de passe** du portail [portail.eauxtdp.fr](https://portail.eauxtdp.fr).
4. Si votre compte possède un seul contrat, il est configuré automatiquement (sinon, sélectionnez le contrat souhaité).

### Options de tarification

Cliquez sur **Configurer** sur l'intégration pour personnaliser :
- **Mode de calcul du prix variable** : Automatique depuis la dernière facture ou Manuel.
- **Abonnement annuel TTC** : Par défaut `81,89 €/an` (`40,09 €` Eau potable + `41,80 €` Assainissement — grille 2026).
- **Prix variable manuel TTC** : Par défaut `3,727 €/m³` (`1,7705 €` Eau potable + `1,9565 €` Assainissement — grille 2026).
- **Tarif utilisé pour la statistique de coût du Dashboard Énergie** : Prix variable hors abonnement (recommandé) ou Prix moyen abonnement inclus.
- **Intervalle de mise à jour** : Par défaut toutes les `6 heures`.

---

## Intégration au Dashboard Énergie (Energy Dashboard)

Dans **Paramètres** → **Tableaux de bord** → **Énergie** → **Consommation d'eau** → **Ajouter une source d'eau** :

### Option A — Statistiques externes horodatées à la date réelle de relève (Recommandé)
- **Eau consommée** : Sélectionnez la statistique externe `Eaux Terre de Provence Consommation (<numcontrat>)` (`eauxtdp:water_consumption_<contrat_id>`).
- **Coût** : Sélectionnez *Utiliser une entité suivant les coûts totaux* → `Eaux Terre de Provence Coût (<numcontrat>)` (`eauxtdp:water_cost_<contrat_id>`).

### Option B — Capteurs temps-réel décalés classiques
- **Eau consommée** : `sensor.eau_terre_de_provence_<numcontrat>_index_telereleve` (`m³`).
- **Coût** : *Utiliser une entité avec le prix actuel* → `sensor.eau_terre_de_provence_<numcontrat>_prix_eau_variable_ttc_hors_abonnement` (`EUR/m³`).

---

## Entités créées

| Type | Nom | Unité | Description |
| :--- | :--- | :---: | :--- |
| `sensor` | **Index télérelève** | `m³` | Dernier index réel télérelevé (`ni / 1000`) |
| `sensor` | **Index télérelève (Litres)** | `L` | Dernier index réel en litres (`ni`) |
| `sensor` | **Dernière consommation journalière** | `L` | Consommation sur la dernière journée relevée (`ni - previous_ni`) |
| `sensor` | **Prix eau variable TTC (hors abonnement)** | `EUR/m³` | Tarif marginal au m³ (`~3,727 €/m³`) |
| `sensor` | **Prix eau moyen TTC (abonnement inclus)** | `EUR/m³` | Tarif complet au m³ (`~4,492 €/m³`) |
| `sensor` | **Coût dernière journée (hors abonnement)** | `EUR` | Coût de la dernière journée relevée |
| `sensor` | **Dernière facture TTC** | `EUR` | Montant TTC et détails de la dernière facture |
| `sensor` | **Prochain prélèvement SEPA** | `EUR` | Prochaine mensualité à venir et sa date |
| `binary_sensor` | **Alerte fuite compteur** | — | Détection d'anomalie / fuite signalée par le compteur |
| `binary_sensor` | **État compteur & télérelève** | — | Statut du compteur et métadonnées radio ITRON/Birdz |
| `button` | **Actualiser les données** | — | Rafraîchit immédiatement les données du contrat |
| `button` | **Importer l'historique (365 jours)** | — | Reconstruit 1 an de statistiques dans le Dashboard Énergie |

---

## Documentation technique

La spécification complète issue de la rétro-ingénierie de l'API JSON:API JVS-Mairistem est disponible dans [`docs/api_eauxtdp_home_assistant.md`](docs/api_eauxtdp_home_assistant.md).
