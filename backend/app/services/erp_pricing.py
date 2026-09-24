from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse
from xmlrpc.client import ServerProxy


TARIFF_MODEL = "giscedata.polissa.tarifa"
TARIFF_NAME = "2.0TD"


class ERPPriceError(RuntimeError):
    pass


@dataclass(frozen=True)
class ERPSettings:
    user: str
    password: str
    database: str
    uri: str
    port: int
    municipi_id: int

    @classmethod
    def from_environment(cls) -> "ERPSettings":
        values = {
            "user": os.environ.get("OOOP_USER", "").strip(),
            "password": os.environ.get("OOOP_PWD", ""),
            "database": os.environ.get("OOOP_DBNAME", "").strip(),
            "uri": os.environ.get("OOOP_URI", "").strip().rstrip("/"),
            "port": os.environ.get("OOOP_PORT", "").strip(),
            "municipi_id": os.environ.get("TARIFF_MUNICIPI_ID", "28").strip(),
        }
        if not all(values[key] for key in ("user", "password", "database", "uri", "port", "municipi_id")):
            raise ERPPriceError("Falten variables de configuracio de l'ERP.")

        parsed_uri = urlparse(values["uri"])
        if parsed_uri.scheme not in {"http", "https"} or not parsed_uri.netloc:
            raise ERPPriceError("OOOP_URI ha de ser una URL absoluta HTTP o HTTPS.")

        try:
            port = int(values["port"])
            municipi_id = int(values["municipi_id"])
        except ValueError as exc:
            raise ERPPriceError("OOOP_PORT i TARIFF_MUNICIPI_ID han de ser enters.") from exc
        if port <= 0 or municipi_id <= 0:
            raise ERPPriceError("OOOP_PORT i TARIFF_MUNICIPI_ID han de ser positius.")

        return cls(
            user=values["user"],
            password=values["password"],
            database=values["database"],
            uri=values["uri"],
            port=port,
            municipi_id=municipi_id,
        )


class ERPPriceClient:
    def __init__(self, settings: ERPSettings):
        self.settings = settings
        base_url = f"{settings.uri}:{settings.port}/xmlrpc"
        self._common = ServerProxy(f"{base_url}/common", allow_none=True)
        self._objects = ServerProxy(f"{base_url}/object", allow_none=True)

    def fetch_tariff_prices(self, target_date: date) -> dict[str, Any]:
        uid = self._common.login(self.settings.database, self.settings.user, self.settings.password)
        if not isinstance(uid, int) or isinstance(uid, bool) or uid <= 0:
            raise ERPPriceError("L'autenticacio amb l'ERP ha fallat.")

        tariff_ids = self._execute(uid, "search", [("name", "=", TARIFF_NAME)])
        if not isinstance(tariff_ids, list) or len(tariff_ids) != 1:
            raise ERPPriceError("L'ERP ha de retornar exactament una tarifa 2.0TD.")

        prices = self._execute(
            uid,
            "get_tariff_prices",
            tariff_ids[0],
            self.settings.municipi_id,
            None,
            None,
            False,
            target_date.isoformat(),
            {},
        )
        if not isinstance(prices, dict):
            raise ERPPriceError("L'ERP no ha retornat un diccionari de preus.")
        return prices

    def _execute(self, uid: int, method: str, *args: Any) -> Any:
        return self._objects.execute(
            self.settings.database,
            uid,
            self.settings.password,
            TARIFF_MODEL,
            method,
            *args,
        )


def map_erp_prices(prices: dict[str, Any], *, synced_at: str) -> dict[str, Any]:
    start_date = _require_date(prices, "start_date")
    version_name = _require_text(prices, "version_name")
    return {
        "tariff_name": version_name,
        "effective_date": start_date,
        "energy_prices_eur_per_kwh": _map_periods(prices, "te", ("P1", "P2", "P3")),
        "contracted_power_prices_eur_per_kw_day": _map_periods(prices, "tp", ("P1", "P2")),
        "self_consumption_surplus_price_eur_per_kwh": _optional_period_price(prices, "ex", "P1"),
        "social_bonus_eur_per_day": _require_price(prices, "bo_social"),
        "synced_at": synced_at,
    }


def _map_periods(prices: dict[str, Any], key: str, periods: tuple[str, ...]) -> dict[str, float]:
    payload = prices.get(key)
    if not isinstance(payload, dict):
        raise ERPPriceError(f"L'ERP no ha retornat el terme '{key}'.")
    return {period: _require_price(payload, period) for period in periods}


def _optional_period_price(prices: dict[str, Any], key: str, period: str) -> float:
    payload = prices.get(key)
    if payload is None:
        return 0.0
    if not isinstance(payload, dict):
        raise ERPPriceError(f"L'ERP ha retornat un terme '{key}' invalid.")
    if period not in payload:
        return 0.0
    return _require_price(payload, period)


def _require_price(payload: dict[str, Any], key: str) -> float:
    entry = payload.get(key)
    if not isinstance(entry, dict) or "value" not in entry:
        raise ERPPriceError(f"L'ERP no ha retornat el preu '{key}'.")
    try:
        value = Decimal(str(entry["value"]))
    except (InvalidOperation, ValueError) as exc:
        raise ERPPriceError(f"El preu '{key}' no es numeric.") from exc
    if not value.is_finite() or value < 0:
        raise ERPPriceError(f"El preu '{key}' ha de ser positiu o zero.")
    return float(value)


def _require_date(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ERPPriceError(f"L'ERP no ha retornat '{key}'.")
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ERPPriceError(f"La data '{key}' no es valida.") from exc


def _require_text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ERPPriceError(f"L'ERP no ha retornat '{key}'.")
    return value.strip()
