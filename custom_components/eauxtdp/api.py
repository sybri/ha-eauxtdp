"""Client asynchrone pour l'API JVS-Mairistem (Portail Eaux Terre de Provence)."""
from __future__ import annotations

import asyncio
from datetime import date, timedelta
import logging
from typing import Any

import aiohttp

from .const import API_ID, BASE_URL, REFERER, USER_AGENT

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)


class EauxTdpError(Exception):
    """Exception de base pour l'intégration Eaux Terre de Provence."""


class EauxTdpAuthError(EauxTdpError):
    """Erreur d'authentification (identifiants invalides ou compte bloqué)."""


class EauxTdpApiError(EauxTdpError):
    """Erreur de communication ou de réponse avec l'API."""


class EauxTdpClient:
    """Client asynchrone pour l'API JSON:API du portail Eaux Terre de Provence."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        email: str,
        password: str,
    ) -> None:
        """Initialise le client API."""
        self._session = session
        self._email = email
        self._password = password
        self._authorization: str = "JWT"
        self._sso_id: str | None = None
        self._app_id: str | None = None
        self._autologin: str | None = None
        self._auth_lock = asyncio.Lock()

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        """Construit les en-têtes obligatoires (anti-WAF Apache + session JVS)."""
        headers: dict[str, str] = {
            "Api-Id": API_ID,
            "Accept": "application/vnd.api+json",
            "Content-Type": "application/vnd.api+json",
            "Referer": REFERER,
            "User-Agent": USER_AGENT,
            "Authorization": self._authorization,
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }
        if self._sso_id:
            headers["Sso-Id"] = self._sso_id
        if self._app_id:
            headers["App-Id"] = self._app_id
        if extra:
            headers.update(extra)
        return headers

    def _update_tokens_from_response(self, resp: aiohttp.ClientResponse) -> None:
        """Extrait et met à jour les jetons de session depuis les en-têtes HTTP."""
        if auth := (
            resp.headers.get("Authorization") or resp.headers.get("authorization")
        ):
            self._authorization = auth
        if sso_id := resp.headers.get("Sso-Id") or resp.headers.get("sso-id"):
            self._sso_id = sso_id
        if app_id := resp.headers.get("App-Id") or resp.headers.get("app-id"):
            self._app_id = app_id
        if autologin := (
            resp.headers.get("AutoLogin") or resp.headers.get("autologin")
        ):
            self._autologin = autologin

    async def async_login(self) -> dict[str, Any]:
        """Authentifie l'utilisateur et récupère les jetons JWT / Sso-Id / App-Id."""
        async with self._auth_lock:
            payload = {
                "data": {
                    "type": "POICL_Signin",
                    "id": "",
                    "attributes": {
                        "login": self._email,
                        "password": self._password,
                        "remember": True,
                    },
                }
            }
            self._authorization = "JWT"
            headers = self._headers({"Referer": f"{REFERER}public/connexion"})
            try:
                async with self._session.post(
                    f"{BASE_URL}/v1/iclients/signin",
                    headers=headers,
                    json=payload,
                    timeout=REQUEST_TIMEOUT,
                ) as resp:
                    if resp.status in (401, 403, 422):
                        body = await resp.text()
                        _LOGGER.debug(
                            "Échec login EauxTDP (HTTP %s): %s", resp.status, body
                        )
                        raise EauxTdpAuthError(
                            f"Identifiants invalides ou accès refusé (HTTP {resp.status})"
                        )
                    if resp.status >= 400:
                        raise EauxTdpApiError(
                            f"Erreur serveur lors du login: HTTP {resp.status}"
                        )
                    self._update_tokens_from_response(resp)
                    data = await resp.json(content_type=None)
                    return data or {}
            except aiohttp.ClientError as err:
                raise EauxTdpApiError(
                    f"Erreur réseau lors de la connexion au portail: {err}"
                ) from err

    async def async_check_session(self) -> bool:
        """Tente de rafraîchir la session via /v1/iclients/check et le jeton AutoLogin."""
        if self._authorization == "JWT":
            return False
        extra: dict[str, str] = {}
        if self._autologin:
            extra["AutoLogin"] = self._autologin
        try:
            async with self._session.post(
                f"{BASE_URL}/v1/iclients/check",
                headers=self._headers(extra),
                json={},
                timeout=REQUEST_TIMEOUT,
            ) as resp:
                if resp.status == 200:
                    self._update_tokens_from_response(resp)
                    return True
                return False
        except aiohttp.ClientError:
            return False

    async def _request(
        self,
        method: str,
        path: str,
        retry_auth: bool = True,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Exécute une requête API avec rafraîchissement ou reconnexion automatique sur 401/403."""
        if self._authorization == "JWT":
            await self.async_login()

        try:
            async with self._session.request(
                method,
                f"{BASE_URL}{path}",
                headers=self._headers(),
                timeout=REQUEST_TIMEOUT,
                **kwargs,
            ) as resp:
                if resp.status in (401, 403) and retry_auth:
                    _LOGGER.debug(
                        "Session expirée (HTTP %s sur %s), tentative de rafraîchissement...",
                        resp.status,
                        path,
                    )
                    if not await self.async_check_session():
                        await self.async_login()
                    return await self._request(
                        method, path, retry_auth=False, **kwargs
                    )
                if resp.status in (401, 403):
                    raise EauxTdpAuthError(
                        f"Accès non autorisé sur {path} (HTTP {resp.status})"
                    )
                if resp.status >= 400:
                    raise EauxTdpApiError(
                        f"Erreur HTTP {resp.status} lors de l'appel à {path}"
                    )
                self._update_tokens_from_response(resp)
                data = await resp.json(content_type=None)
                return data or {}
        except aiohttp.ClientError as err:
            raise EauxTdpApiError(f"Erreur réseau sur {path}: {err}") from err

    async def async_get_contracts(self) -> dict[str, Any]:
        """Récupère la liste des contrats de l'abonné."""
        return await self._request(
            "GET",
            "/v1/iclients/contrat?include=pconso,pconso.pdessadr,redevable_actif,redevable_actif.personne&page[size]=20",
        )

    async def async_get_contract_detail(self, contrat_id: str) -> dict[str, Any]:
        """Récupère le détail complet d'un contrat (compteur, adresse, dernier relevé, tarif interne)."""
        return await self._request(
            "GET",
            f"/v1/iclients/contrat/{contrat_id}?include=price,pconso,pconso.pdessadr,pconso.compteur,pconso.dernierreleve,telereleve",
        )

    async def async_get_teleindex(
        self,
        contrat_id: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict[str, Any]:
        """Récupère les index journaliers de télérelève (en litres) sur une période."""
        if end_date is None:
            end_date = date.today() - timedelta(days=1)
        if start_date is None:
            start_date = end_date - timedelta(days=35)
        start_str = start_date.strftime("%Y%m%d")
        end_str = end_date.strftime("%Y%m%d")
        return await self._request(
            "GET",
            f"/v1/iclients/teleindex2/{contrat_id}/{start_str}/{end_str}?option[sort]=asc&option[algorithm]=reverse",
        )

    async def async_get_bills(self, contrat_id: str) -> dict[str, Any]:
        """Récupère l'historique des factures du contrat."""
        return await self._request(
            "GET",
            f"/v1/iclients/facture?sort=-datefact&filter[and][contfact.contrat_id][eq]={contrat_id}",
        )

    async def async_get_next_payments(self, contrat_id: str) -> dict[str, Any]:
        """Récupère l'échéancier des règlements / prélèvements SEPA."""
        return await self._request(
            "GET",
            f"/v1/iclients/contrat/reglements/{contrat_id}?include=hfact,moderegl",
        )

    async def async_get_readings(self, contrat_id: str) -> dict[str, Any]:
        """Récupère l'historique des relevés semestriels officiels."""
        return await self._request(
            "GET",
            f"/v1/iclients/releve/contrat/{contrat_id}?include=pconso,compteur&sort=-dateni,-dateai,-releve_id",
        )
