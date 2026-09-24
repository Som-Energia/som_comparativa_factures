from datetime import UTC, date, datetime
import json
from pathlib import Path
from unittest.mock import patch

import pytest

import app.config as app_config
from app.config import load_pricing_config, update_pricing_config
from app.services.calculator import build_comparison_report
from app.services.erp_pricing import ERPPriceClient, ERPPriceError, ERPSettings, map_erp_prices
from app.services.pricing_sync import MADRID_TIMEZONE, _seconds_until_next_sync, sync_pricing


def erp_prices(**overrides):
    prices = {
        "tp": {
            "P1": {"value": 0.074529, "uom": "EUR/kW/dia"},
            "P2": {"value": 0.008666, "uom": "EUR/kW/dia"},
        },
        "te": {
            "P1": {"value": 0.342, "uom": "EUR/kWh"},
            "P2": {"value": 0.281, "uom": "EUR/kWh"},
            "P3": {"value": 0.234, "uom": "EUR/kWh"},
        },
        "ex": {"P1": {"value": 0.055, "uom": "EUR/kWh"}},
        "bo_social": {"value": 0.0, "uom": "EUR/dia"},
        "version_name": "2.0TD_SOM 2026-10-01",
        "start_date": "2026-10-01",
        "end_date": False,
    }
    prices.update(overrides)
    return prices


@pytest.fixture
def pricing_config(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    source_path = Path(__file__).parents[1] / "config" / "pricing.json"
    target_path = config_dir / "pricing.json"
    target_path.write_text(source_path.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(app_config, "CONFIG_DIR", config_dir)
    return target_path


def test_map_erp_prices_maps_the_tariff_fields():
    mapped = map_erp_prices(erp_prices(), synced_at="2026-08-31T00:10:00+00:00")

    assert mapped == {
        "tariff_name": "2.0TD_SOM 2026-10-01",
        "effective_date": "2026-10-01",
        "energy_prices_eur_per_kwh": {"P1": 0.342, "P2": 0.281, "P3": 0.234},
        "contracted_power_prices_eur_per_kw_day": {"P1": 0.074529, "P2": 0.008666},
        "self_consumption_surplus_price_eur_per_kwh": 0.055,
        "social_bonus_eur_per_day": 0.0,
        "synced_at": "2026-08-31T00:10:00+00:00",
    }


def test_map_erp_prices_defaults_missing_surplus_to_zero():
    prices = erp_prices()
    del prices["ex"]

    mapped = map_erp_prices(prices, synced_at="2026-08-31T00:10:00+00:00")

    assert mapped["self_consumption_surplus_price_eur_per_kwh"] == 0.0


def test_map_erp_prices_rejects_missing_energy_period():
    prices = erp_prices()
    del prices["te"]["P3"]

    with pytest.raises(ERPPriceError, match="P3"):
        map_erp_prices(prices, synced_at="2026-08-31T00:10:00+00:00")


def test_update_pricing_config_preserves_form_controlled_values(pricing_config):
    updated = update_pricing_config(
        {
            "tariff_name": "2.0TD_SOM 2026-10-01",
            "effective_date": "2026-10-01",
            "energy_prices_eur_per_kwh": {"P1": 0.342, "P2": 0.281, "P3": 0.234},
            "synced_at": "2026-08-31T00:10:00+00:00",
        }
    )

    persisted = json.loads(pricing_config.read_text(encoding="utf-8"))
    assert persisted == updated
    assert load_pricing_config()["tariff_name"] == "2.0TD_SOM 2026-10-01"
    assert persisted["adjustment_service_eur_per_kwh"] == 0.019
    assert persisted["meter_rental_eur"] == 0.81
    assert persisted["electric_tax_rate"] == 0.0511269632
    assert persisted["vat_rate"] == 0.21


def test_sync_pricing_uses_a_31_day_lookahead(pricing_config, monkeypatch):
    captured_dates = []

    class FakeClient:
        def __init__(self, _settings):
            pass

        def fetch_tariff_prices(self, target_date):
            captured_dates.append(target_date)
            return erp_prices()

    monkeypatch.setattr("app.services.pricing_sync.ERPPriceClient", FakeClient)
    monkeypatch.setattr("app.services.pricing_sync.ERPSettings.from_environment", lambda: object())

    sync_pricing(datetime(2026, 8, 31, 12, tzinfo=UTC))

    assert captured_dates == [date(2026, 10, 1)]
    assert load_pricing_config()["effective_date"] == "2026-10-01"


def test_sync_pricing_keeps_existing_file_when_erp_fails(pricing_config, monkeypatch):
    before = pricing_config.read_text(encoding="utf-8")

    class FakeClient:
        def __init__(self, _settings):
            pass

        def fetch_tariff_prices(self, _target_date):
            raise ERPPriceError("ERP no disponible")

    monkeypatch.setattr("app.services.pricing_sync.ERPPriceClient", FakeClient)
    monkeypatch.setattr("app.services.pricing_sync.ERPSettings.from_environment", lambda: object())

    with pytest.raises(ERPPriceError, match="no disponible"):
        sync_pricing(datetime(2026, 8, 31, 12, tzinfo=UTC))

    assert pricing_config.read_text(encoding="utf-8") == before


def test_erp_client_calls_the_expected_xmlrpc_methods(monkeypatch):
    calls = []

    class CommonProxy:
        def login(self, database, user, password):
            calls.append(("login", database, user, password))
            return 17

    class ObjectsProxy:
        def execute(self, *args):
            calls.append(("execute", *args))
            if args[4] == "search":
                return [42]
            return erp_prices()

    def fake_server_proxy(url, **_kwargs):
        return CommonProxy() if url.endswith("/common") else ObjectsProxy()

    monkeypatch.setattr("app.services.erp_pricing.ServerProxy", fake_server_proxy)
    client = ERPPriceClient(
        ERPSettings(user="user", password="password", database="database", uri="https://erp.example", port=8069, municipi_id=28)
    )

    result = client.fetch_tariff_prices(date(2026, 10, 1))

    assert result["start_date"] == "2026-10-01"
    assert calls == [
        ("login", "database", "user", "password"),
        ("execute", "database", 17, "password", "giscedata.polissa.tarifa", "search", [("name", "=", "2.0TD")]),
        (
            "execute",
            "database",
            17,
            "password",
            "giscedata.polissa.tarifa",
            "get_tariff_prices",
            42,
            28,
            None,
            None,
            False,
            "2026-10-01",
            {},
        ),
    ]


def test_next_sync_is_scheduled_for_the_next_midnight_window():
    now = datetime(2026, 9, 1, 0, 0, tzinfo=MADRID_TIMEZONE)

    seconds = _seconds_until_next_sync(now)

    assert 0 < seconds <= 70 * 60


def test_compare_allows_tariffs_without_surplus_compensation():
    pricing = {
        "tariff_name": "2.0TD",
        "effective_date": "2026-10-01",
        "currency": "EUR",
        "energy_prices_eur_per_kwh": {"P1": 0, "P2": 0, "P3": 0},
        "contracted_power_prices_eur_per_kw_day": {"P1": 0, "P2": 0},
        "self_consumption_surplus_price_eur_per_kwh": 0,
        "social_bonus_eur_per_day": 0,
    }
    payload = {
        "cups": "ES0210002100000000ZN0F",
        "titular": "Persona Persona",
        "billing_days": 1,
        "competitor_invoice_amount": 0,
        "energy_by_periods": {"P1": 0, "P2": 0, "P3": 0},
        "contracted_power_kw_by_periods": {"P1": 0, "P2": 0},
        "self_consumption_surplus_kwh": 6,
        "adjustment_service_eur_per_kwh": 0,
        "meter_rental_eur": 0,
        "vat_rate_percent": 0,
        "electric_tax_rate_percent": 0,
    }

    with patch("app.services.calculator.load_pricing_config", return_value=pricing):
        report = build_comparison_report(payload)

    assert report["breakdown"]["flux_solar_kwh"] == 6.0
    assert report["breakdown"]["costs"]["surplus_compensation_eur"] == 0.0
