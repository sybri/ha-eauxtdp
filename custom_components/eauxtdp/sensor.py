"""Entités capteurs (SensorEntity) pour Eaux Terre de Provence."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CURRENCY_EURO, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN, REFERER
from .coordinator import EauxTdpCoordinator, EauxTdpData


def build_device_info(data: EauxTdpData) -> DeviceInfo:
    """Construit l'objet DeviceInfo pour le compteur d'eau du contrat."""
    compteur = data.compteur_attrs
    numserie = compteur.get("numserie") or f"Contrat-{data.numcontrat}"
    marque = compteur.get("enum_marq") or "ITRON / Birdz"
    module_type = compteur.get("rrtypemodule") or "Télérelève"
    diam = compteur.get("enum_diam") or "20"
    model = f"Compteur {marque} Ø{diam}mm ({module_type})"

    return DeviceInfo(
        identifiers={(DOMAIN, data.contrat_id)},
        name=f"Eau Terre de Provence ({data.numcontrat})",
        manufacturer=marque,
        model=model,
        serial_number=str(numserie),
        configuration_url=REFERER,
    )


@dataclass(frozen=True, kw_only=True)
class EauxTdpSensorEntityDescription(SensorEntityDescription):
    """Description d'un capteur Eaux Terre de Provence."""

    value_fn: Callable[[EauxTdpData], Any]
    extra_attrs_fn: Callable[[EauxTdpData], dict[str, Any]] | None = None


SENSORS: tuple[EauxTdpSensorEntityDescription, ...] = (
    EauxTdpSensorEntityDescription(
        key="teleindex_m3",
        name="Index télérelève",
        icon="mdi:counter",
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=3,
        value_fn=lambda d: (
            round(d.latest_point.ni_liters / 1000.0, 3)
            if d.latest_point
            else None
        ),
        extra_attrs_fn=lambda d: {
            "date_releve": d.latest_point.dateni if d.latest_point else None,
            "index_litres": d.latest_point.ni_liters if d.latest_point else None,
            "index_precedent_litres": (
                d.latest_point.previous_ni_liters if d.latest_point else None
            ),
            "date_releve_precedent": (
                d.latest_point.previous_dateni if d.latest_point else None
            ),
            "consommation_jour_litres": (
                d.latest_point.daily_liters if d.latest_point else None
            ),
            "estime": d.latest_point.estimated if d.latest_point else False,
            "statistique_externe_volume": f"{DOMAIN}:water_consumption_{d.contrat_id}",
            "statistique_externe_cout": f"{DOMAIN}:water_cost_{d.contrat_id}",
        },
    ),
    EauxTdpSensorEntityDescription(
        key="teleindex_l",
        name="Index télérelève (Litres)",
        icon="mdi:water-pump",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=0,
        value_fn=lambda d: d.latest_point.ni_liters if d.latest_point else None,
        extra_attrs_fn=lambda d: {
            "date_releve": d.latest_point.dateni if d.latest_point else None,
            "numero_serie_compteur": d.compteur_attrs.get("numserie"),
            "numero_module_radio": d.compteur_attrs.get("rrnsmodule"),
        },
    ),
    EauxTdpSensorEntityDescription(
        key="daily_conso_l",
        name="Dernière consommation journalière",
        icon="mdi:water",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda d: (
            d.latest_point.daily_liters
            if d.latest_point and d.latest_point.daily_liters is not None
            else None
        ),
        extra_attrs_fn=lambda d: {
            "date_releve": d.latest_point.dateni if d.latest_point else None,
            "date_debut_periode": (
                d.latest_point.previous_dateni if d.latest_point else None
            ),
            "consommation_m3": (
                round(d.latest_point.daily_liters / 1000.0, 3)
                if d.latest_point and d.latest_point.daily_liters is not None
                else None
            ),
            "cout_variable_ttc_eur": d.daily_cost_variable_eur,
            "cout_moyen_ttc_eur": d.daily_cost_average_eur,
        },
    ),
    EauxTdpSensorEntityDescription(
        key="water_price_variable_ttc",
        name="Prix eau variable TTC (hors abonnement)",
        icon="mdi:currency-eur",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{UnitOfVolume.CUBIC_METERS}",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=4,
        value_fn=lambda d: d.water_price_variable_ttc,
        extra_attrs_fn=lambda d: {
            "source_calcul": d.price_calculation_source,
            "prix_litre_ttc_eur": round(d.water_price_variable_ttc / 1000.0, 6),
            "abonnement_annuel_ttc_eur": d.annual_subscription_ttc,
            "abonnement_journalier_ttc_eur": round(
                d.annual_subscription_ttc / 365.0, 5
            ),
            "detail_eau_potable_ttc_2026": 1.7705,
            "detail_assainissement_ttc_2026": 1.9565,
            "api_poicl_price_brut": d.api_price_attrs.get("price"),
        },
    ),
    EauxTdpSensorEntityDescription(
        key="water_price_avg_ttc",
        name="Prix eau moyen TTC (abonnement inclus)",
        icon="mdi:cash-multiple",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{UnitOfVolume.CUBIC_METERS}",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=4,
        value_fn=lambda d: d.water_price_average_ttc,
        extra_attrs_fn=lambda d: {
            "prix_litre_moyen_ttc_eur": round(
                d.water_price_average_ttc / 1000.0, 6
            ),
            "facture_reference": d.last_bill.get("nofacture"),
            "facture_ttc_eur": d.last_bill.get("ttc"),
            "facture_volume_m3": d.last_bill.get("consofac"),
        },
    ),
    EauxTdpSensorEntityDescription(
        key="daily_cost",
        name="Coût dernière journée (hors abonnement)",
        icon="mdi:hand-coin",
        native_unit_of_measurement=CURRENCY_EURO,
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda d: d.daily_cost_variable_eur,
        extra_attrs_fn=lambda d: {
            "date_releve": d.latest_point.dateni if d.latest_point else None,
            "consommation_litres": (
                d.latest_point.daily_liters if d.latest_point else None
            ),
            "cout_avec_abonnement_inclus_eur": d.daily_cost_average_eur,
            "tarif_applique_eur_m3": d.water_price_variable_ttc,
        },
    ),
    EauxTdpSensorEntityDescription(
        key="last_bill_ttc",
        name="Dernière facture TTC",
        icon="mdi:file-document-outline",
        native_unit_of_measurement=CURRENCY_EURO,
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
        value_fn=lambda d: (
            float(d.last_bill["ttc"])
            if d.last_bill and d.last_bill.get("ttc") is not None
            else None
        ),
        extra_attrs_fn=lambda d: {
            "numero_facture": d.last_bill.get("nofacture"),
            "date_facture": d.last_bill.get("datefact"),
            "type_facture": d.last_bill.get("typefact"),
            "consommation_facturee_m3": d.last_bill.get("consofac"),
            "montant_ht_eur": d.last_bill.get("ht"),
            "montant_tva_eur": d.last_bill.get("tva"),
            "mensualites_deduites_eur": d.last_bill.get("mensualites"),
            "net_a_payer_eur": d.last_bill.get("nap"),
            "reste_a_payer_eur": d.last_bill.get("h_restant"),
            "facture_soldee": d.last_bill.get("h_soldee"),
            "date_echeance": d.last_bill.get("datech"),
            "fichier_pdf": d.last_bill.get("pdf_filename"),
        },
    ),
    EauxTdpSensorEntityDescription(
        key="next_payment",
        name="Prochain prélèvement SEPA",
        icon="mdi:calendar-clock",
        native_unit_of_measurement=CURRENCY_EURO,
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda d: (
            float(d.next_payment["ttc"])
            if d.next_payment and d.next_payment.get("ttc") is not None
            else 0.0
        ),
        extra_attrs_fn=lambda d: {
            "date_prochain_prelevement": d.next_payment.get("dateregl"),
            "statut_echeance": d.next_payment.get("enum_stregl"),
            "mensualite_avance": d.next_payment.get("avance"),
            "nombre_echeances_a_venir": d.upcoming_payments_count,
            "total_echeances_a_venir_eur": d.upcoming_payments_total,
        },
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Configure les capteurs Eaux Terre de Provence à partir d'une ConfigEntry."""
    coordinator: EauxTdpCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        EauxTdpSensor(coordinator, description) for description in SENSORS
    )


class EauxTdpSensor(CoordinatorEntity[EauxTdpCoordinator], SensorEntity):
    """Représentation d'un capteur Eaux Terre de Provence."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION
    entity_description: EauxTdpSensorEntityDescription

    def __init__(
        self,
        coordinator: EauxTdpCoordinator,
        description: EauxTdpSensorEntityDescription,
    ) -> None:
        """Initialise le capteur."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = (
            f"{DOMAIN}_{coordinator.contrat_id}_{description.key}"
        )
        self._attr_device_info = build_device_info(coordinator.data)

    @property
    def native_value(self) -> Any:
        """Retourne la valeur actuelle du capteur."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Retourne les attributs supplémentaires du capteur."""
        if self.entity_description.extra_attrs_fn is not None:
            return self.entity_description.extra_attrs_fn(self.coordinator.data)
        return None
