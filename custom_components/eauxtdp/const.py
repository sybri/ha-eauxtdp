"""Constantes pour l'intégration Eaux Terre de Provence (eauxtdp)."""
from __future__ import annotations

from datetime import timedelta

DOMAIN = "eauxtdp"
DEFAULT_NAME = "Eaux Terre de Provence"
ATTRIBUTION = "Données fournies par le portail Régie des Eaux Terre de Provence (JVS-Mairistem / Birdz)"

# Configuration réseau API JVS-Mairistem (iClients)
BASE_URL = "https://portail.eauxtdp.fr/api"
API_ID = "00ab80a941962fc608283fead90150ed@iclients-09064-terredeprovence"
REFERER = "https://portail.eauxtdp.fr/"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)

# Clés de configuration (ConfigEntry.data)
CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_CONTRAT_ID = "contrat_id"
CONF_NUM_CONTRAT = "numcontrat"

# Clés d'options (ConfigEntry.options)
CONF_PRICE_MODE = "price_mode"
CONF_ANNUAL_SUBSCRIPTION_TTC = "annual_subscription_ttc"
CONF_MANUAL_VARIABLE_PRICE_TTC = "manual_variable_price_ttc"
CONF_COST_STAT_TARIFF = "cost_stat_tariff"
CONF_UPDATE_INTERVAL_HOURS = "update_interval_hours"

# Modes de calcul du prix
PRICE_MODE_AUTO_INVOICE = "auto_invoice"
PRICE_MODE_MANUAL = "manual"

# Choix du tarif pour la statistique de coût du Dashboard Énergie
COST_STAT_TARIFF_VARIABLE = "variable"
COST_STAT_TARIFF_AVERAGE = "average"

# Grille tarifaire 2026 par défaut (Régie des Eaux de Terre de Provence)
# Abonnement Eau Potable TTC (40.09 €) + Abonnement Assainissement TTC (41.80 €) = 81.89 €/an
DEFAULT_ANNUAL_SUBSCRIPTION_TTC = 81.89
# Part variable TTC/m³ hors abonnement : Eau Potable + Taxes 5.5% (1.77050 €) + Assainissement + Taxe 10% (1.95646 €) = 3.72696 €/m³
DEFAULT_VARIABLE_PRICE_TTC = 3.727
# Prix moyen constaté sur facture 2026 (480.69 € / 107 m³) en repli si aucune facture n'est disponible
DEFAULT_AVERAGE_PRICE_TTC = 4.492

# Intervalles et fenêtres d'historique
DEFAULT_UPDATE_INTERVAL_HOURS = 6
DEFAULT_UPDATE_INTERVAL = timedelta(hours=DEFAULT_UPDATE_INTERVAL_HOURS)
DEFAULT_TELEINDEX_DAYS = 35
INITIAL_HISTORY_DAYS = 365

# Services
SERVICE_REFRESH = "refresh"
SERVICE_IMPORT_HISTORY = "import_history"
ATTR_DAYS = "days"
