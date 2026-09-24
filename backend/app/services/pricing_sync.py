from __future__ import annotations

import logging
from datetime import UTC, datetime, time, timedelta
from time import sleep
from zoneinfo import ZoneInfo

from app.config import update_pricing_config
from app.services.erp_pricing import ERPPriceClient, ERPSettings, map_erp_prices


LOGGER = logging.getLogger(__name__)
MADRID_TIMEZONE = ZoneInfo("Europe/Madrid")
SYNC_TIME = time(hour=0, minute=10)
LOOKAHEAD_DAYS = 31


def sync_pricing(now: datetime | None = None) -> dict:
    local_now = (now or datetime.now(MADRID_TIMEZONE)).astimezone(MADRID_TIMEZONE)
    target_date = local_now.date() + timedelta(days=LOOKAHEAD_DAYS)
    client = ERPPriceClient(ERPSettings.from_environment())
    prices = client.fetch_tariff_prices(target_date)
    updated_fields = map_erp_prices(prices, synced_at=datetime.now(UTC).isoformat())
    return update_pricing_config(updated_fields)


def run_forever() -> None:
    while True:
        try:
            sync_pricing()
            LOGGER.info("Preus sincronitzats correctament amb l'ERP.")
        except Exception:
            LOGGER.exception("No s'han pogut sincronitzar els preus amb l'ERP.")
        sleep(_seconds_until_next_sync(datetime.now(MADRID_TIMEZONE)))


def _seconds_until_next_sync(now: datetime) -> float:
    local_now = now.astimezone(MADRID_TIMEZONE)
    next_sync = datetime.combine(local_now.date(), SYNC_TIME, tzinfo=MADRID_TIMEZONE)
    if next_sync <= local_now:
        next_sync += timedelta(days=1)
    return (next_sync - local_now).total_seconds()
