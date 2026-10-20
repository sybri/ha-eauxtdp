"""Intégration Eaux Terre de Provence (portail.eauxtdp.fr) pour Home Assistant."""
from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import EauxTdpClient
from .const import (
    ATTR_DAYS,
    CONF_CONTRAT_ID,
    CONF_EMAIL,
    CONF_PASSWORD,
    DOMAIN,
    INITIAL_HISTORY_DAYS,
    SERVICE_IMPORT_HISTORY,
    SERVICE_REFRESH,
)
from .coordinator import EauxTdpCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
]

SERVICE_REFRESH_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_CONTRAT_ID): cv.string,
    }
)

SERVICE_IMPORT_HISTORY_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_CONTRAT_ID): cv.string,
        vol.Optional(ATTR_DAYS, default=INITIAL_HISTORY_DAYS): vol.All(
            vol.Coerce(int), vol.Range(min=7, max=1825)
        ),
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Configure une entrée Eaux Terre de Provence."""
    hass.data.setdefault(DOMAIN, {})

    session = async_create_clientsession(hass)
    client = EauxTdpClient(
        session=session,
        email=str(entry.data[CONF_EMAIL]),
        password=str(entry.data[CONF_PASSWORD]),
    )

    coordinator = EauxTdpCoordinator(hass=hass, entry=entry, client=client)
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _async_register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Décharge une entrée Eaux Terre de Provence."""
    if unload_ok := await hass.config_entries.async_unload_platforms(
        entry, PLATFORMS
    ):
        hass.data[DOMAIN].pop(entry.entry_id, None)
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, SERVICE_REFRESH)
            hass.services.async_remove(DOMAIN, SERVICE_IMPORT_HISTORY)
    return unload_ok


async def _async_update_listener(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Met à jour le coordinateur lorsque les options de tarification changent."""
    coordinator: EauxTdpCoordinator | None = hass.data.get(DOMAIN, {}).get(
        entry.entry_id
    )
    if coordinator is not None:
        coordinator.update_options()
        await coordinator.async_request_refresh()


def _async_register_services(hass: HomeAssistant) -> None:
    """Enregistre les services `eauxtdp.refresh` et `eauxtdp.import_history`."""
    if hass.services.has_service(DOMAIN, SERVICE_REFRESH):
        return

    async def handle_refresh(call: ServiceCall) -> None:
        """Gère l'appel au service `eauxtdp.refresh`."""
        target_contrat = call.data.get(CONF_CONTRAT_ID)
        for coord in hass.data.get(DOMAIN, {}).values():
            if isinstance(coord, EauxTdpCoordinator):
                if not target_contrat or coord.contrat_id == str(target_contrat):
                    await coord.async_request_refresh()

    async def handle_import_history(call: ServiceCall) -> None:
        """Gère l'appel au service `eauxtdp.import_history`."""
        target_contrat = call.data.get(CONF_CONTRAT_ID)
        days = int(call.data.get(ATTR_DAYS, INITIAL_HISTORY_DAYS))
        for coord in hass.data.get(DOMAIN, {}).values():
            if isinstance(coord, EauxTdpCoordinator):
                if not target_contrat or coord.contrat_id == str(target_contrat):
                    await coord.async_import_history(days=days)
                    await coord.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        SERVICE_REFRESH,
        handle_refresh,
        schema=SERVICE_REFRESH_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_IMPORT_HISTORY,
        handle_import_history,
        schema=SERVICE_IMPORT_HISTORY_SCHEMA,
    )
