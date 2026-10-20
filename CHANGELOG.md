# Changelog

Toutes les modifications notables de ce projet sont documentées dans ce fichier.

## [1.0.0] - 2026-10-20

### Ajouté
- Client asynchrone `aiohttp` complet pour le portail JVS-Mairistem `portail.eauxtdp.fr` avec gestion des en-têtes anti-WAF (`Referer`, `User-Agent`, `Api-Id`), authentification `Jwt id="..."` et renouvellement automatique de session (`AutoLogin`).
- Flux de configuration UI (`ConfigFlow`) avec découverte automatique des contrats, support multi-contrats, ré-authentification (`reauth`) et options configurables (`OptionsFlow`).
- Capteurs de télérelève journalière (`m³`, `L`, consommation veille en `L`) filtrant automatiquement les entrées de complétion non remontées (`add: true`).
- Double calcul du tarif de l'eau (Prix variable TTC hors abonnement `~3,727 €/m³` et Prix moyen TTC abonnement inclus `~4,492 €/m³`) basé sur la grille 2026 et la dernière facture réelle.
- Suivi de la dernière facture TTC et de l'échéancier des prélèvements SEPA à venir.
- Capteurs binaires d'alerte de fuite et de diagnostic du compteur ITRON / module radio HOMG3.
- Injection rétroactive des statistiques long terme (`async_add_external_statistics`) sur 365 jours au premier démarrage puis sur 35 jours glissants pour le Dashboard Énergie.
- Boutons et services `eauxtdp.refresh` et `eauxtdp.import_history`.
