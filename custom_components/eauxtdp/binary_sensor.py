"""Capteurs binaires (BinarySensorEntity) pour Eaux Terre de Provence."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN
from .coordinator import EauxTdpCoordinator, EauxTdpData
from .sensor import build_device_info


@dataclass(frozen=True, kw_only=True)
class EauxTdpBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Description d'un capteur binaire Eaux Terre de Provence."""

    is_on_fn: Callable[[EauxTdpData], bool]
    extra_attrs_fn: Callable[[EauxTdpData], dict[str, Any]] | None = None


BINARY_SENSORS: tuple[EauxTdpBinarySensorEntityDescription, ...] = (
    EauxTdpBinarySensorEntityDescription(
        key="leak_alert",
        name="Alerte fuite compteur",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:pipe-leak",
        is_on_fn=lambda d: bool(
            d.compteur_attrs.get("flag_alerte")
            or d.pconso_attrs.get("cptfuite")
            or d.last_releve_attrs.get("cptfuite")
        ),
        extra_attrs_fn=lambda d: {
            "flag_alerte_compteur": d.compteur_attrs.get("flag_alerte"),
            "chaine_alerte": d.compteur_attrs.get("chaine_alerte"),
            "compteur_fuite_pconso": d.pconso_attrs.get("cptfuite"),
            "fuite_dernier_releve": d.last_releve_attrs.get("cptfuite"),
        },
    ),
    EauxTdpBinarySensorEntityDescription(
        key="meter_status",
        name="État compteur & télérelève",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:radio-tower",
        is_on_fn=lambda d: bool(
            d.compteur_attrs.get("compteur_actif", True)
            and not d.pconso_attrs.get("cptferme", False)
        ),
        extra_attrs_fn=lambda d: {
            "numero_contrat": d.numcontrat,
            "contrat_id": d.contrat_id,
            "numero_serie_compteur": d.compteur_attrs.get("numserie"),
            "marque_compteur": d.compteur_attrs.get("enum_marq"),
            "diametre_mm": d.compteur_attrs.get("enum_diam"),
            "annee_fabrication": d.compteur_attrs.get("anneefab"),
            "date_installation": d.compteur_attrs.get("dateinst"),
            "releve_radio_actif": d.compteur_attrs.get("releve_radio"),
            "type_module_radio": d.compteur_attrs.get("rrtypemodule"),
            "numero_module_radio": d.compteur_attrs.get("rrnsmodule"),
            "id_pdl_telereleve": d.pdl_attrs.get("rlp_id_externe"),
            "adresse_desserte": " ".join(
                str(p)
                for p in (
                    d.pdessadr_attrs.get("numvoirie"),
                    d.pdessadr_attrs.get("nomvoie"),
                    d.pdessadr_attrs.get("cp"),
                    d.pdessadr_attrs.get("ville"),
                )
                if p
            ),
            "coordonnees_gps": d.pconso_attrs.get("sigcoord"),
        },
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Configure les capteurs binaires Eaux Terre de Provence."""
    coordinator: EauxTdpCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        EauxTdpBinarySensor(coordinator, description)
        for description in BINARY_SENSORS
    )


class EauxTdpBinarySensor(
    CoordinatorEntity[EauxTdpCoordinator], BinarySensorEntity
):
    """Représentation d'un capteur binaire Eaux Terre de Provence."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION
    entity_description: EauxTdpBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: EauxTdpCoordinator,
        description: EauxTdpBinarySensorEntityDescription,
    ) -> None:
        """Initialise le capteur binaire."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = (
            f"{DOMAIN}_{coordinator.contrat_id}_{description.key}"
        )
        self._attr_device_info = build_device_info(coordinator.data)

    @property
    def is_on(self) -> bool:
        """Retourne l'état binaire."""
        return self.entity_description.is_on_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Retourne les attributs supplémentaires."""
        if self.entity_description.extra_attrs_fn is not None:
            return self.entity_description.extra_attrs_fn(self.coordinator.data)
        return None
