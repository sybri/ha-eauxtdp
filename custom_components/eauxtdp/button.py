"""Entités boutons (ButtonEntity) pour Eaux Terre de Provence."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, INITIAL_HISTORY_DAYS
from .coordinator import EauxTdpCoordinator
from .sensor import build_device_info


@dataclass(frozen=True, kw_only=True)
class EauxTdpButtonEntityDescription(ButtonEntityDescription):
    """Description d'un bouton Eaux Terre de Provence."""

    press_fn: Callable[[EauxTdpCoordinator], Awaitable[None]]


async def _async_press_refresh(coordinator: EauxTdpCoordinator) -> None:
    """Force une mise à jour immédiate des données."""
    await coordinator.async_request_refresh()


async def _async_press_import_history(coordinator: EauxTdpCoordinator) -> None:
    """Force l'import de l'historique sur 365 jours dans le Dashboard Énergie."""
    await coordinator.async_import_history(days=INITIAL_HISTORY_DAYS)
    await coordinator.async_request_refresh()


BUTTONS: tuple[EauxTdpButtonEntityDescription, ...] = (
    EauxTdpButtonEntityDescription(
        key="refresh",
        name="Actualiser les données",
        icon="mdi:refresh",
        entity_category=EntityCategory.CONFIG,
        press_fn=_async_press_refresh,
    ),
    EauxTdpButtonEntityDescription(
        key="import_history",
        name="Importer l'historique (365 jours)",
        icon="mdi:database-import-outline",
        entity_category=EntityCategory.CONFIG,
        press_fn=_async_press_import_history,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Configure les boutons Eaux Terre de Provence."""
    coordinator: EauxTdpCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        EauxTdpButton(coordinator, description) for description in BUTTONS
    )


class EauxTdpButton(CoordinatorEntity[EauxTdpCoordinator], ButtonEntity):
    """Représentation d'un bouton d'action Eaux Terre de Provence."""

    _attr_has_entity_name = True
    entity_description: EauxTdpButtonEntityDescription

    def __init__(
        self,
        coordinator: EauxTdpCoordinator,
        description: EauxTdpButtonEntityDescription,
    ) -> None:
        """Initialise le bouton."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = (
            f"{DOMAIN}_{coordinator.contrat_id}_{description.key}"
        )
        self._attr_device_info = build_device_info(coordinator.data)

    async def async_press(self) -> None:
        """Exécute l'action associée au bouton."""
        await self.entity_description.press_fn(self.coordinator)
