from datetime import UTC, date, datetime
import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

import app.config as app_config
from app.config import load_pricing_config, update_pricing_config
from app.services.calculator import build_comparison_report
from app.services.erp_pricing import ERPPriceClient, ERPPriceError, ERPSettings, map_erp_adjustment_prices, map_erp_prices
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


def erp_adjustment_prices(**overrides):
    prices = {
        "tariff": "2.0TD", "type": "ssaa", "date": "2026-08-01",
        "prices": {
            f"P{period}": {"value": period / 1000, "uom": "€/kWh"}
            for period in range(1, 7)
        },
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


def test_map_adjustment_prices_preserves_periods_and_zero():
    prices = erp_adjustment_prices()
    prices["prices"]["P2"]["value"] = 0
    assert map_erp_adjustment_prices(prices) == {
        "adjustment_service_prices_eur_per_kwh": {"P1": 0.001, "P2": 0, "P3": 0.003},
        "adjustment_service_price_date": "2026-08-01",
    }


@pytest.mark.parametrize("overrides", [
    {"tariff": "3.0TD"}, {"type": "index"}, {"date": "invalid"},
    {"error": "Missing configuration", "error_code": "MissingSimulationConfig", "prices": None},
    {"prices": {"P1": {"value": 0.1, "uom": "€/kWh"}}},
])
def test_map_adjustment_prices_rejects_invalid_response(overrides):
    with pytest.raises(ERPPriceError):
        map_erp_adjustment_prices(erp_adjustment_prices(**overrides))


@pytest.mark.parametrize("entry", [
    {"value": -0.1, "uom": "€/kWh"}, {"value": "NaN", "uom": "€/kWh"},
    {"value": "Infinity", "uom": "€/kWh"}, {"value": "invalid", "uom": "€/kWh"},
    {"value": 0.1, "uom": "€/MWh"}, {"value": 0.1}, {},
])
def test_map_adjustment_prices_rejects_invalid_period(entry):
    prices = erp_adjustment_prices()
    prices["prices"]["P3"] = entry
    with pytest.raises(ERPPriceError):
        map_erp_adjustment_prices(prices)


def test_legacy_pricing_is_read_and_migrated_on_sync(pricing_config):
    legacy = json.loads(pricing_config.read_text(encoding="utf-8"))
    del legacy["adjustment_service_prices_eur_per_kwh"]
    del legacy["adjustment_service_price_date"]
    legacy["adjustment_service_eur_per_kwh"] = 0.02
    pricing_config.write_text(json.dumps(legacy), encoding="utf-8")

    loaded = load_pricing_config()
    assert loaded["adjustment_service_prices_eur_per_kwh"] == {"P1": 0.02, "P2": 0.02, "P3": 0.02}
    assert loaded["adjustment_service_price_date"] is None
    assert json.loads(pricing_config.read_text(encoding="utf-8")) == legacy

    update_pricing_config(map_erp_adjustment_prices(erp_adjustment_prices()))
    persisted = json.loads(pricing_config.read_text(encoding="utf-8"))
    assert "adjustment_service_eur_per_kwh" not in persisted
    assert persisted["adjustment_service_prices_eur_per_kwh"]["P3"] == 0.003
    assert persisted["adjustment_service_price_date"] == "2026-08-01"


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
    assert persisted["adjustment_service_prices_eur_per_kwh"] == {"P1": 0.019, "P2": 0.019, "P3": 0.019}
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

        def fetch_adjustment_prices(self):
            return erp_adjustment_prices()

    monkeypatch.setattr("app.services.pricing_sync.ERPPriceClient", FakeClient)
    monkeypatch.setattr("app.services.pricing_sync.ERPSettings.from_environment", lambda: object())

    sync_pricing(datetime(2026, 8, 31, 12, tzinfo=UTC))

    assert captured_dates == [date(2026, 10, 1)]
    assert load_pricing_config()["effective_date"] == "2026-10-01"
    assert load_pricing_config()["adjustment_service_prices_eur_per_kwh"] == {"P1": 0.001, "P2": 0.002, "P3": 0.003}
    assert load_pricing_config()["adjustment_service_price_date"] == "2026-08-01"


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


@pytest.mark.parametrize("response", [erp_adjustment_prices(), {"error": "Missing", "error_code": "MissingSimulationConfig"}, False])
def test_erp_client_calls_adjustment_helper_and_checks_errors(monkeypatch, response):
    common = type("Common", (), {"login": lambda *_args: 17})()
    objects = Mock()
    objects.execute.return_value = response
    monkeypatch.setattr("app.services.erp_pricing.ServerProxy", lambda url, **_kw: common if url.endswith("/common") else objects)
    client = ERPPriceClient(ERPSettings("user", "password", "database", "https://erp.example", 8069, 28))
    if isinstance(response, dict) and "prices" in response:
        assert client.fetch_adjustment_prices() == response
    else:
        with pytest.raises(ERPPriceError):
            client.fetch_adjustment_prices()
    objects.execute.assert_called_once_with(
        "database", 17, "password", "giscedata.polissa.tarifa",
        "get_last_month_average_prices_www", "2.0TD", "ssaa",
    )


def test_sync_preserves_all_prices_when_adjustment_response_is_invalid(pricing_config, monkeypatch):
    before = pricing_config.read_bytes()
    client = Mock()
    client.fetch_tariff_prices.return_value = erp_prices()
    client.fetch_adjustment_prices.return_value = erp_adjustment_prices(prices={})
    monkeypatch.setattr("app.services.pricing_sync.ERPPriceClient", lambda _settings: client)
    monkeypatch.setattr("app.services.pricing_sync.ERPSettings.from_environment", lambda: object())

    with pytest.raises(ERPPriceError):
        sync_pricing(datetime(2026, 8, 31, 12, tzinfo=UTC))
    assert pricing_config.read_bytes() == before


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
        "adjustment_service_prices_eur_per_kwh": {"P1": 0, "P2": 0, "P3": 0},
    }
    payload = {
        "cups": "ES0210002100000000ZN0F",
        "titular": "Persona Persona",
        "billing_days": 1,
        "competitor_invoice_amount": 0,
        "energy_by_periods": {"P1": 0, "P2": 0, "P3": 0},
        "contracted_power_kw_by_periods": {"P1": 0, "P2": 0},
        "self_consumption_surplus_kwh": 6,
        "meter_rental_eur": 0,
        "vat_rate_percent": 0,
        "electric_tax_rate_percent": 0,
    }

    with patch("app.services.calculator.load_pricing_config", return_value=pricing):
        report = build_comparison_report(payload)

    assert report["breakdown"]["flux_solar_kwh"] == 6.0
    assert report["breakdown"]["costs"]["surplus_compensation_eur"] == 0.0
