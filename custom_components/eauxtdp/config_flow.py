"""Flux de configuration (ConfigFlow & OptionsFlow) pour Eaux Terre de Provence."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import EauxTdpApiError, EauxTdpAuthError, EauxTdpClient
from .const import (
    CONF_ANNUAL_SUBSCRIPTION_TTC,
    CONF_CONTRAT_ID,
    CONF_COST_STAT_TARIFF,
    CONF_EMAIL,
    CONF_MANUAL_VARIABLE_PRICE_TTC,
    CONF_NUM_CONTRAT,
    CONF_PASSWORD,
    CONF_PRICE_MODE,
    CONF_UPDATE_INTERVAL_HOURS,
    COST_STAT_TARIFF_AVERAGE,
    COST_STAT_TARIFF_VARIABLE,
    DEFAULT_ANNUAL_SUBSCRIPTION_TTC,
    DEFAULT_UPDATE_INTERVAL_HOURS,
    DEFAULT_VARIABLE_PRICE_TTC,
    DOMAIN,
    PRICE_MODE_AUTO_INVOICE,
    PRICE_MODE_MANUAL,
)

_LOGGER = logging.getLogger(__name__)


class EauxTdpConfigFlow(ConfigFlow, domain=DOMAIN):
    """Gère le flux de configuration pour Eaux Terre de Provence."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialise le flux de configuration."""
        self._email: str = ""
        self._password: str = ""
        self._contracts: list[dict[str, Any]] = []
        self._reauth_entry: ConfigEntry | None = None

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> EauxTdpOptionsFlowHandler:
        """Retourne le gestionnaire d'options pour cette entrée."""
        return EauxTdpOptionsFlowHandler(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Étape initiale : saisie de l'email et du mot de passe du portail."""
        errors: dict[str, str] = {}

        if user_input is not None:
            email = user_input[CONF_EMAIL].strip()
            password = user_input[CONF_PASSWORD]

            session = async_create_clientsession(self.hass)
            client = EauxTdpClient(session=session, email=email, password=password)

            try:
                await client.async_login()
                contracts_resp = await client.async_get_contracts()
            except EauxTdpAuthError:
                errors["base"] = "invalid_auth"
            except EauxTdpApiError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Erreur inattendue lors de la connexion EauxTDP")
                errors["base"] = "unknown"
            else:
                contracts = self._extract_contracts(contracts_resp)
                if not contracts:
                    errors["base"] = "no_contract"
                elif len(contracts) == 1:
                    contract = contracts[0]
                    return await self._async_create_entry_from_contract(
                        email=email,
                        password=password,
                        contract=contract,
                    )
                else:
                    self._email = email
                    self._password = password
                    self._contracts = contracts
                    return await self.async_step_select_contract()

        schema = vol.Schema(
            {
                vol.Required(CONF_EMAIL): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.EMAIL, autocomplete="email")
                ),
                vol.Required(CONF_PASSWORD): TextSelector(
                    TextSelectorConfig(
                        type=TextSelectorType.PASSWORD, autocomplete="current-password"
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_select_contract(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Étape de sélection du contrat si le compte en possède plusieurs."""
        if user_input is not None:
            selected_id = user_input[CONF_CONTRAT_ID]
            for contract in self._contracts:
                if contract["id"] == selected_id:
                    return await self._async_create_entry_from_contract(
                        email=self._email,
                        password=self._password,
                        contract=contract,
                    )

        options = [
            SelectOptionDict(
                value=c["id"],
                label=f"Contrat n° {c['numcontrat']} ({c['label']})",
            )
            for c in self._contracts
        ]
        schema = vol.Schema(
            {
                vol.Required(CONF_CONTRAT_ID): SelectSelector(
                    SelectSelectorConfig(
                        options=options,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                )
            }
        )
        return self.async_show_form(
            step_id="select_contract",
            data_schema=schema,
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Déclenché lorsque les identifiants ont expiré ou changé."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Formulaire de ré-authentification."""
        errors: dict[str, str] = {}
        default_email = (
            self._reauth_entry.data.get(CONF_EMAIL, "")
            if self._reauth_entry
            else ""
        )

        if user_input is not None and self._reauth_entry is not None:
            email = user_input[CONF_EMAIL].strip()
            password = user_input[CONF_PASSWORD]
            session = async_create_clientsession(self.hass)
            client = EauxTdpClient(session=session, email=email, password=password)

            try:
                await client.async_login()
            except EauxTdpAuthError:
                errors["base"] = "invalid_auth"
            except EauxTdpApiError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    self._reauth_entry,
                    data_updates={
                        CONF_EMAIL: email,
                        CONF_PASSWORD: password,
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_EMAIL, default=default_email): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.EMAIL)
                ),
                vol.Required(CONF_PASSWORD): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
            }
        )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=schema,
            errors=errors,
        )

    async def _async_create_entry_from_contract(
        self,
        email: str,
        password: str,
        contract: dict[str, Any],
    ) -> ConfigFlowResult:
        """Crée l'entrée de configuration pour un contrat donné."""
        contrat_id = str(contract["id"])
        numcontrat = str(contract["numcontrat"])
        await self.async_set_unique_id(f"{DOMAIN}_{contrat_id}")
        self._abort_if_unique_id_configured()

        title = f"Eaux TDP ({numcontrat})"
        return self.async_create_entry(
            title=title,
            data={
                CONF_EMAIL: email,
                CONF_PASSWORD: password,
                CONF_CONTRAT_ID: contrat_id,
                CONF_NUM_CONTRAT: numcontrat,
            },
            options={
                CONF_PRICE_MODE: PRICE_MODE_AUTO_INVOICE,
                CONF_ANNUAL_SUBSCRIPTION_TTC: DEFAULT_ANNUAL_SUBSCRIPTION_TTC,
                CONF_MANUAL_VARIABLE_PRICE_TTC: DEFAULT_VARIABLE_PRICE_TTC,
                CONF_COST_STAT_TARIFF: COST_STAT_TARIFF_VARIABLE,
                CONF_UPDATE_INTERVAL_HOURS: DEFAULT_UPDATE_INTERVAL_HOURS,
            },
        )

    @staticmethod
    def _extract_contracts(resp: dict[str, Any]) -> list[dict[str, Any]]:
        """Extrait la liste des contrats depuis la réponse JSON:API."""
        data_list = resp.get("data") or []
        included = resp.get("included") or []
        addr_map: dict[str, str] = {}

        for inc in included:
            if inc.get("type") == "POICL_Pdessadr":
                attrs = inc.get("attributes") or {}
                parts = [
                    str(attrs.get("numvoirie") or "").strip(),
                    str(attrs.get("nomvoie") or "").strip(),
                    str(attrs.get("cp") or "").strip(),
                    str(attrs.get("ville") or "").strip(),
                ]
                addr_str = " ".join(p for p in parts if p)
                if addr_str:
                    addr_map[str(inc.get("id"))] = addr_str

        first_addr = next(iter(addr_map.values()), "Terre de Provence")
        results: list[dict[str, Any]] = []

        for item in data_list:
            if item.get("type") != "POICL_Contrat":
                continue
            c_id = str(item.get("id") or "")
            attrs = item.get("attributes") or {}
            if not c_id:
                continue
            numcontrat = str(attrs.get("numcontrat") or c_id)
            results.append(
                {
                    "id": c_id,
                    "numcontrat": numcontrat,
                    "actif": bool(attrs.get("actif", True)),
                    "label": first_addr,
                }
            )
        return results


class EauxTdpOptionsFlowHandler(OptionsFlow):
    """Gère les options de tarification et de rafraîchissement d'Eaux Terre de Provence."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialise l'OptionsFlow."""
        self._entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Affiche et enregistre le formulaire d'options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        opts = self._entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_PRICE_MODE,
                    default=opts.get(CONF_PRICE_MODE, PRICE_MODE_AUTO_INVOICE),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(
                                value=PRICE_MODE_AUTO_INVOICE,
                                label="Automatique depuis la dernière facture ((TTC - Abonnement) / m³)",
                            ),
                            SelectOptionDict(
                                value=PRICE_MODE_MANUAL,
                                label="Manuel (utiliser le tarif variable saisi ci-dessous)",
                            ),
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    CONF_ANNUAL_SUBSCRIPTION_TTC,
                    default=float(
                        opts.get(
                            CONF_ANNUAL_SUBSCRIPTION_TTC,
                            DEFAULT_ANNUAL_SUBSCRIPTION_TTC,
                        )
                    ),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=0.0,
                        max=500.0,
                        step=0.01,
                        unit_of_measurement="EUR/an",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    CONF_MANUAL_VARIABLE_PRICE_TTC,
                    default=float(
                        opts.get(
                            CONF_MANUAL_VARIABLE_PRICE_TTC,
                            DEFAULT_VARIABLE_PRICE_TTC,
                        )
                    ),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=0.1,
                        max=25.0,
                        step=0.001,
                        unit_of_measurement="EUR/m³",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    CONF_COST_STAT_TARIFF,
                    default=opts.get(
                        CONF_COST_STAT_TARIFF, COST_STAT_TARIFF_VARIABLE
                    ),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(
                                value=COST_STAT_TARIFF_VARIABLE,
                                label="Prix variable TTC hors abonnement (~3,73 €/m³ - Recommandé)",
                            ),
                            SelectOptionDict(
                                value=COST_STAT_TARIFF_AVERAGE,
                                label="Prix moyen TTC tout compris avec abonnement (~4,49 €/m³)",
                            ),
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    CONF_UPDATE_INTERVAL_HOURS,
                    default=int(
                        opts.get(
                            CONF_UPDATE_INTERVAL_HOURS,
                            DEFAULT_UPDATE_INTERVAL_HOURS,
                        )
                    ),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=1,
                        max=24,
                        step=1,
                        unit_of_measurement="h",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
