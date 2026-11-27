from __future__ import annotations

import logging
from datetime import UTC, datetime, time, timedelta
from time import monotonic, sleep
from zoneinfo import ZoneInfo

from app.config import update_pricing_config
from app.services.erp_pricing import ERPPriceClient, ERPSettings, map_erp_adjustment_prices, map_erp_prices


LOGGER = logging.getLogger(__name__)
MADRID_TIMEZONE = ZoneInfo("Europe/Madrid")
SYNC_TIME = time(hour=0, minute=10)
LOOKAHEAD_DAYS = 38


def sync_pricing(now: datetime | None = None) -> dict:
    started_at = monotonic()
    local_now = (now or datetime.now(MADRID_TIMEZONE)).astimezone(MADRID_TIMEZONE)
    target_date = local_now.date() + timedelta(days=LOOKAHEAD_DAYS)
    LOGGER.info("Inici de sincronització ERP: data consultada=%s, marge=%s dies.", target_date, LOOKAHEAD_DAYS)
    client = ERPPriceClient(ERPSettings.from_environment())
    LOGGER.info("Consultant la tarifa 2.0TD a l'ERP.")
    prices = client.fetch_tariff_prices(target_date)
    updated_fields = map_erp_prices(prices, synced_at=datetime.now(UTC).isoformat())
    LOGGER.info(
        "Tarifa rebuda i validada: tarifa=%s, entrada en vigor=%s.",
        updated_fields["tariff_name"], updated_fields["effective_date"],
    )
    LOGGER.info("Consultant els serveis d'ajust a l'ERP.")
    updated_fields.update(map_erp_adjustment_prices(client.fetch_adjustment_prices()))
    LOGGER.info("Serveis d'ajust rebuts i validats: data=%s.", updated_fields["adjustment_service_price_date"])
    LOGGER.info("Desant els preus a pricing.json.")
    pricing = update_pricing_config(updated_fields)
    LOGGER.info("Preus sincronitzats i desats correctament amb l'ERP. Durada=%.2f s.", monotonic() - started_at)
    return pricing


def run_forever() -> None:
    LOGGER.info(
        "Servei pricing-sync iniciat: marge=%s dies, sincronització en arrencar i cada dia a les %s (%s).",
        LOOKAHEAD_DAYS, SYNC_TIME.isoformat(timespec="minutes"), MADRID_TIMEZONE,
    )
    while True:
        try:
            sync_pricing()
        except Exception:
            LOGGER.exception("No s'han pogut sincronitzar els preus amb l'ERP.")
        now = datetime.now(MADRID_TIMEZONE)
        seconds = _seconds_until_next_sync(now)
        LOGGER.info("Propera sincronització: %s (%s).", (now + timedelta(seconds=seconds)).isoformat(), MADRID_TIMEZONE)
        sleep(seconds)


def _seconds_until_next_sync(now: datetime) -> float:
    local_now = now.astimezone(MADRID_TIMEZONE)
    next_sync = datetime.combine(local_now.date(), SYNC_TIME, tzinfo=MADRID_TIMEZONE)
    if next_sync <= local_now:
        next_sync += timedelta(days=1)
    return (next_sync - local_now).total_seconds()
