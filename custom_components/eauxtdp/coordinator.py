"""DataUpdateCoordinator et injection des statistiques pour Eaux Terre de Provence."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
import logging
from typing import Any

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CURRENCY_EURO, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import EauxTdpApiError, EauxTdpAuthError, EauxTdpClient
from .const import (
    CONF_ANNUAL_SUBSCRIPTION_TTC,
    CONF_CONTRAT_ID,
    CONF_COST_STAT_TARIFF,
    CONF_MANUAL_VARIABLE_PRICE_TTC,
    CONF_NUM_CONTRAT,
    CONF_PRICE_MODE,
    CONF_UPDATE_INTERVAL_HOURS,
    COST_STAT_TARIFF_AVERAGE,
    COST_STAT_TARIFF_VARIABLE,
    DEFAULT_ANNUAL_SUBSCRIPTION_TTC,
    DEFAULT_AVERAGE_PRICE_TTC,
    DEFAULT_TELEINDEX_DAYS,
    DEFAULT_UPDATE_INTERVAL_HOURS,
    DEFAULT_VARIABLE_PRICE_TTC,
    DOMAIN,
    INITIAL_HISTORY_DAYS,
    PRICE_MODE_AUTO_INVOICE,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class TeleindexPoint:
    """Représente un relevé journalier valide issu de teleindex2."""

    dateni: str
    dt_utc: datetime
    ni_liters: int
    previous_ni_liters: int | None
    previous_dateni: str | None
    daily_liters: int | None
    estimated: bool = False


@dataclass
class EauxTdpData:
    """Données agrégées exposées aux entités Home Assistant."""

    contrat_id: str
    numcontrat: str
    contrat_attrs: dict[str, Any] = field(default_factory=dict)
    compteur_attrs: dict[str, Any] = field(default_factory=dict)
    pconso_attrs: dict[str, Any] = field(default_factory=dict)
    pdessadr_attrs: dict[str, Any] = field(default_factory=dict)
    pdl_attrs: dict[str, Any] = field(default_factory=dict)
    api_price_attrs: dict[str, Any] = field(default_factory=dict)
    last_releve_attrs: dict[str, Any] = field(default_factory=dict)

    # Télérelève
    latest_point: TeleindexPoint | None = None
    teleindex_points: list[TeleindexPoint] = field(default_factory=list)

    # Facturation & Échéancier
    last_bill: dict[str, Any] = field(default_factory=dict)
    next_payment: dict[str, Any] = field(default_factory=dict)
    upcoming_payments_count: int = 0
    upcoming_payments_total: float = 0.0

    # Tarifs calculés (€/m³)
    water_price_variable_ttc: float = DEFAULT_VARIABLE_PRICE_TTC
    water_price_average_ttc: float = DEFAULT_AVERAGE_PRICE_TTC
    annual_subscription_ttc: float = DEFAULT_ANNUAL_SUBSCRIPTION_TTC
    price_calculation_source: str = "default_2026"

    # Coûts journaliers estimés (€)
    daily_cost_variable_eur: float | None = None
    daily_cost_average_eur: float | None = None


class EauxTdpCoordinator(DataUpdateCoordinator[EauxTdpData]):
    """Coordinateur de mise à jour des données Eaux Terre de Provence."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: EauxTdpClient,
    ) -> None:
        """Initialise le coordinateur."""
        self.client = client
        self.contrat_id: str = str(entry.data[CONF_CONTRAT_ID])
        self.numcontrat: str = str(entry.data.get(CONF_NUM_CONTRAT, self.contrat_id))
        self._initial_history_checked: bool = False

        hours = int(
            entry.options.get(
                CONF_UPDATE_INTERVAL_HOURS, DEFAULT_UPDATE_INTERVAL_HOURS
            )
        )
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{self.contrat_id}",
            update_interval=timedelta(hours=hours),
        )

    def update_options(self) -> None:
        """Met à jour l'intervalle de rafraîchissement lorsque les options changent."""
        hours = int(
            self.config_entry.options.get(
                CONF_UPDATE_INTERVAL_HOURS, DEFAULT_UPDATE_INTERVAL_HOURS
            )
        )
        self.update_interval = timedelta(hours=hours)

    async def _async_update_data(self) -> EauxTdpData:
        """Récupère l'ensemble des données du contrat depuis l'API JVS."""
        try:
            detail_resp = await self.client.async_get_contract_detail(self.contrat_id)
            bills_resp = await self.client.async_get_bills(self.contrat_id)
            payments_resp = await self.client.async_get_next_payments(self.contrat_id)

            end_date = date.today() - timedelta(days=1)
            start_date = end_date - timedelta(days=DEFAULT_TELEINDEX_DAYS)
            tele_resp = await self.client.async_get_teleindex(
                self.contrat_id, start_date=start_date, end_date=end_date
            )
        except EauxTdpAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except EauxTdpApiError as err:
            raise UpdateFailed(f"Erreur de communication avec le portail EauxTDP: {err}") from err

        data = self._parse_payloads(
            detail_resp=detail_resp,
            bills_resp=bills_resp,
            payments_resp=payments_resp,
            tele_resp=tele_resp,
        )

        # Injection des statistiques dans le Recorder (Dashboard Énergie)
        try:
            await self._async_sync_statistics(data)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning(
                "Erreur non bloquante lors de l'injection des statistiques Énergie EauxTDP: %s",
                err,
            )

        return data

    def _parse_payloads(
        self,
        detail_resp: dict[str, Any],
        bills_resp: dict[str, Any],
        payments_resp: dict[str, Any],
        tele_resp: dict[str, Any],
    ) -> EauxTdpData:
        """Analyse les réponses JSON:API et construit l'objet EauxTdpData."""
        contrat_data = detail_resp.get("data") or {}
        contrat_attrs = contrat_data.get("attributes") or {}
        numcontrat = str(contrat_attrs.get("numcontrat") or self.numcontrat)

        compteur_attrs: dict[str, Any] = {}
        pconso_attrs: dict[str, Any] = {}
        pdessadr_attrs: dict[str, Any] = {}
        pdl_attrs: dict[str, Any] = {}
        api_price_attrs: dict[str, Any] = {}
        last_releve_attrs: dict[str, Any] = {}

        for inc in detail_resp.get("included") or []:
            inc_type = inc.get("type")
            inc_attrs = inc.get("attributes") or {}
            if inc_type == "POICL_Compteur" and not compteur_attrs:
                compteur_attrs = inc_attrs
            elif inc_type == "POICL_Pconso" and not pconso_attrs:
                pconso_attrs = inc_attrs
            elif inc_type == "POICL_Pdessadr" and not pdessadr_attrs:
                pdessadr_attrs = inc_attrs
            elif inc_type == "PORLV_Pdl" and not pdl_attrs:
                pdl_attrs = inc_attrs
            elif inc_type == "POICL_Price" and not api_price_attrs:
                api_price_attrs = inc_attrs
            elif inc_type == "POICL_Releve" and not last_releve_attrs:
                last_releve_attrs = inc_attrs

        # Analyse de la dernière facture
        bills_list = bills_resp.get("data") or []
        last_bill: dict[str, Any] = {}
        if bills_list:
            last_bill = dict(bills_list[0].get("attributes") or {})
            last_bill["id"] = bills_list[0].get("id")

        # Analyse de l'échéancier des règlements (mensualités SEPA à venir)
        payments_list = payments_resp.get("data") or []
        upcoming: list[dict[str, Any]] = []
        for item in payments_list:
            attrs = item.get("attributes") or {}
            if attrs.get("enum_stregl") == "NEXP":
                upcoming.append(attrs)

        upcoming.sort(key=lambda x: str(x.get("dateregl") or "9999-99-99"))
        next_payment = upcoming[0] if upcoming else {}
        upcoming_total = sum(
            _safe_float(p.get("ttc"), 0.0) for p in upcoming
        )

        # Calcul des tarifs (Variable hors abo & Moyen abo inclus)
        options = self.config_entry.options
        price_mode = options.get(CONF_PRICE_MODE, PRICE_MODE_AUTO_INVOICE)
        annual_sub_ttc = _safe_float(
            options.get(CONF_ANNUAL_SUBSCRIPTION_TTC),
            DEFAULT_ANNUAL_SUBSCRIPTION_TTC,
        )
        manual_var_ttc = _safe_float(
            options.get(CONF_MANUAL_VARIABLE_PRICE_TTC),
            DEFAULT_VARIABLE_PRICE_TTC,
        )

        bill_ttc = _safe_float(last_bill.get("ttc"), 0.0)
        bill_conso = _safe_float(last_bill.get("consofac"), 0.0)

        # Prix moyen "Tout compris" (Facture TTC / Volume facturé)
        if bill_ttc > 0 and bill_conso > 0:
            water_price_avg_ttc = round(bill_ttc / bill_conso, 4)
        else:
            water_price_avg_ttc = round(
                manual_var_ttc + (annual_sub_ttc / 100.0), 4
            )

        # Prix variable TTC (Hors abonnement)
        if (
            price_mode == PRICE_MODE_AUTO_INVOICE
            and bill_ttc > annual_sub_ttc
            and bill_conso > 0
        ):
            water_price_var_ttc = round(
                (bill_ttc - annual_sub_ttc) / bill_conso, 4
            )
            price_source = f"facture_{last_bill.get('nofacture', 'auto')}"
        else:
            water_price_var_ttc = round(manual_var_ttc, 4)
            price_source = "grille_tarifaire_2026"

        # Analyse des points de télérelève
        points = self._parse_teleindex_points(tele_resp)
        latest_point = points[-1] if points else None

        daily_cost_var: float | None = None
        daily_cost_avg: float | None = None
        if latest_point and latest_point.daily_liters is not None:
            daily_m3 = latest_point.daily_liters / 1000.0
            daily_cost_var = round(daily_m3 * water_price_var_ttc, 2)
            daily_cost_avg = round(daily_m3 * water_price_avg_ttc, 2)

        return EauxTdpData(
            contrat_id=self.contrat_id,
            numcontrat=numcontrat,
            contrat_attrs=contrat_attrs,
            compteur_attrs=compteur_attrs,
            pconso_attrs=pconso_attrs,
            pdessadr_attrs=pdessadr_attrs,
            pdl_attrs=pdl_attrs,
            api_price_attrs=api_price_attrs,
            last_releve_attrs=last_releve_attrs,
            latest_point=latest_point,
            teleindex_points=points,
            last_bill=last_bill,
            next_payment=next_payment,
            upcoming_payments_count=len(upcoming),
            upcoming_payments_total=round(upcoming_total, 2),
            water_price_variable_ttc=water_price_var_ttc,
            water_price_average_ttc=water_price_avg_ttc,
            annual_subscription_ttc=annual_sub_ttc,
            price_calculation_source=price_source,
            daily_cost_variable_eur=daily_cost_var,
            daily_cost_average_eur=daily_cost_avg,
        )

    def _parse_teleindex_points(
        self, tele_resp: dict[str, Any]
    ) -> list[TeleindexPoint]:
        """Extrait et filtre les relevés journaliers valides de PORLV_Teleconso2."""
        raw_items = tele_resp.get("data") or []
        valid_points: list[TeleindexPoint] = []
        local_tz = dt_util.get_default_time_zone()

        for item in raw_items:
            attrs = item.get("attributes") or {}
            # Règle critique : ignorer les entrées de complétion (add: true ou ni: null)
            if attrs.get("add") is True or attrs.get("ni") is None:
                continue

            dateni_str = str(attrs.get("dateni") or "").strip()
            if not dateni_str:
                continue

            ni_val = _safe_int(attrs.get("ni"))
            if ni_val is None:
                continue

            prev_ni_val = _safe_int(attrs.get("previous_ni"))
            prev_dateni_str = attrs.get("previous_dateni")

            # Calcul de la consommation de la journée arrivant à `dateni`
            daily_liters: int | None = None
            if prev_ni_val is not None and ni_val >= prev_ni_val:
                daily_liters = ni_val - prev_ni_val

            dt_parsed = _parse_dateni_to_utc(dateni_str, local_tz)
            if dt_parsed is None:
                continue

            valid_points.append(
                TeleindexPoint(
                    dateni=dateni_str,
                    dt_utc=dt_parsed,
                    ni_liters=ni_val,
                    previous_ni_liters=prev_ni_val,
                    previous_dateni=str(prev_dateni_str) if prev_dateni_str else None,
                    daily_liters=daily_liters,
                    estimated=bool(attrs.get("estimated_consumption")),
                )
            )

        valid_points.sort(key=lambda p: p.dt_utc)

        # Si previous_ni n'était pas renseigné sur certains points consécutifs, on le déduit
        for idx in range(1, len(valid_points)):
            curr = valid_points[idx]
            prev = valid_points[idx - 1]
            if curr.daily_liters is None and curr.ni_liters >= prev.ni_liters:
                curr.previous_ni_liters = prev.ni_liters
                curr.daily_liters = curr.ni_liters - prev.ni_liters

        return valid_points

    async def async_import_history(
        self, days: int = INITIAL_HISTORY_DAYS
    ) -> int:
        """Récupère l'historique sur `days` jours et injecte les statistiques externes."""
        end_date = date.today() - timedelta(days=1)
        start_date = end_date - timedelta(days=days)
        _LOGGER.info(
            "Import de l'historique EauxTDP pour le contrat %s du %s au %s (%d jours)",
            self.contrat_id,
            start_date,
            end_date,
            days,
        )
        tele_resp = await self.client.async_get_teleindex(
            self.contrat_id, start_date=start_date, end_date=end_date
        )
        points = self._parse_teleindex_points(tele_resp)
        if not points:
            _LOGGER.warning(
                "Aucun point de télérelève valide trouvé sur les %d derniers jours",
                days,
            )
            return 0

        price_per_m3 = self._get_selected_stat_price(self.data)
        await self._async_insert_statistics_points(points, price_per_m3)
        return len(points)

    def _get_selected_stat_price(self, data: EauxTdpData | None) -> float:
        """Retourne le tarif (€/m³) choisi pour calculer la statistique de coût."""
        tariff_choice = self.config_entry.options.get(
            CONF_COST_STAT_TARIFF, COST_STAT_TARIFF_VARIABLE
        )
        if data is None:
            return DEFAULT_VARIABLE_PRICE_TTC
        if tariff_choice == COST_STAT_TARIFF_AVERAGE:
            return data.water_price_average_ttc
        return data.water_price_variable_ttc

    async def _async_sync_statistics(self, data: EauxTdpData) -> None:
        """Synchronise automatiquement les statistiques (365j au 1er lancement, puis 35j)."""
        if "recorder" not in self.hass.config.components:
            return

        vol_stat_id = f"{DOMAIN}:water_consumption_{self.contrat_id}"
        price_per_m3 = self._get_selected_stat_price(data)

        if not self._initial_history_checked:
            self._initial_history_checked = True
            last_stats = await get_instance(self.hass).async_add_executor_job(
                get_last_statistics,
                self.hass,
                1,
                vol_stat_id,
                True,
                {"sum", "state"},
            )
            if not last_stats or vol_stat_id not in last_stats:
                _LOGGER.info(
                    "Première initialisation des statistiques EauxTDP (%s) : import de l'historique sur %d jours",
                    vol_stat_id,
                    INITIAL_HISTORY_DAYS,
                )
                end_date = date.today() - timedelta(days=1)
                start_date = end_date - timedelta(days=INITIAL_HISTORY_DAYS)
                tele_resp = await self.client.async_get_teleindex(
                    self.contrat_id, start_date=start_date, end_date=end_date
                )
                history_points = self._parse_teleindex_points(tele_resp)
                if history_points:
                    await self._async_insert_statistics_points(
                        history_points, price_per_m3
                    )
                    return

        if data.teleindex_points:
            await self._async_insert_statistics_points(
                data.teleindex_points, price_per_m3
            )

    async def _async_insert_statistics_points(
        self,
        points: list[TeleindexPoint],
        price_per_m3: float,
    ) -> None:
        """Construit et injecte les séries `water_consumption` (m³) et `water_cost` (EUR)."""
        if not points:
            return

        vol_stat_id = f"{DOMAIN}:water_consumption_{self.contrat_id}"
        cost_stat_id = f"{DOMAIN}:water_cost_{self.contrat_id}"

        vol_meta_kwargs: dict[str, Any] = {
            "has_mean": False,
            "has_sum": True,
            "name": f"Eaux Terre de Provence Consommation ({self.numcontrat})",
            "source": DOMAIN,
            "statistic_id": vol_stat_id,
            "unit_of_measurement": UnitOfVolume.CUBIC_METERS,
        }
        cost_meta_kwargs: dict[str, Any] = {
            "has_mean": False,
            "has_sum": True,
            "name": f"Eaux Terre de Provence Coût ({self.numcontrat})",
            "source": DOMAIN,
            "statistic_id": cost_stat_id,
            "unit_of_measurement": CURRENCY_EURO,
        }

        # Compatibilité Home Assistant 2025/2026+ (mean_type et unit_class sur StatisticMetaData)
        try:
            from homeassistant.components.recorder.models import StatisticMeanType

            vol_meta_kwargs["mean_type"] = StatisticMeanType.NONE
            cost_meta_kwargs["mean_type"] = StatisticMeanType.NONE
        except ImportError:
            pass

        vol_meta_kwargs["unit_class"] = "volume"
        cost_meta_kwargs["unit_class"] = None

        vol_metadata = StatisticMetaData(**vol_meta_kwargs)
        cost_metadata = StatisticMetaData(**cost_meta_kwargs)

        vol_statistics: list[StatisticData] = []
        cost_statistics: list[StatisticData] = []

        for pt in points:
            # L'horodatage de la statistique doit être aligné au début de l'heure (minute=0, second=0)
            stat_start = pt.dt_utc.replace(minute=0, second=0, microsecond=0)
            sum_m3 = round(pt.ni_liters / 1000.0, 3)
            state_m3 = (
                round(pt.daily_liters / 1000.0, 3)
                if pt.daily_liters is not None
                else 0.0
            )
            sum_cost = round(sum_m3 * price_per_m3, 4)
            state_cost = round(state_m3 * price_per_m3, 4)

            vol_statistics.append(
                StatisticData(
                    start=stat_start,
                    state=state_m3,
                    sum=sum_m3,
                )
            )
            cost_statistics.append(
                StatisticData(
                    start=stat_start,
                    state=state_cost,
                    sum=sum_cost,
                )
            )

        async_add_external_statistics(self.hass, vol_metadata, vol_statistics)
        async_add_external_statistics(self.hass, cost_metadata, cost_statistics)
        _LOGGER.debug(
            "%d points de statistiques externes injectés pour %s et %s (tarif=%.4f €/m³)",
            len(vol_statistics),
            vol_stat_id,
            cost_stat_id,
            price_per_m3,
        )


def _safe_float(val: Any, default: float = 0.0) -> float:
    """Convertit une valeur en float en toute sécurité."""
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _safe_int(val: Any) -> int | None:
    """Convertit une valeur en int en toute sécurité."""
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _parse_dateni_to_utc(dateni_str: str, local_tz: Any) -> datetime | None:
    """Parse une date `YYYY-MM-DD HH:MM:SS` ou `YYYY-MM-DD` en datetime UTC alignée à l'heure."""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            naive = datetime.strptime(dateni_str, fmt)
            local_dt = naive.replace(tzinfo=local_tz)
            return dt_util.as_utc(local_dt)
        except ValueError:
            continue
    parsed = dt_util.parse_datetime(dateni_str)
    if parsed is not None:
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=local_tz)
        return dt_util.as_utc(parsed)
    return None
