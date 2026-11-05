import json
from pathlib import Path
from shutil import copytree

import pytest

import app.config as template_config


TEST_DRAFT_VERSION = 99


@pytest.fixture
def reference_pricing(tmp_path, monkeypatch):
    pricing = {
        "tariff_name": "2.0TD Periodes",
        "effective_date": "2026-05-01",
        "currency": "EUR",
        "energy_prices_eur_per_kwh": {"P1": 0.226, "P2": 0.15, "P3": 0.124},
        "contracted_power_prices_eur_per_kw_day": {
            "P1": 0.0820109589041096,
            "P2": 0.0080958904109589,
        },
        "self_consumption_surplus_price_eur_per_kwh": 0.03,
        "adjustment_service_prices_eur_per_kwh": {"P1": 0, "P2": 0, "P3": 0},
        "adjustment_service_price_date": "2026-04-01",
        "social_bonus_eur_per_day": 0.024688,
        "meter_rental_eur": 0.81,
        "electric_tax_rate": 0.0511269632,
        "vat_rate": 0.21,
    }
    pricing_path = tmp_path / "pricing.json"
    pricing_path.write_text(json.dumps(pricing), encoding="utf-8")
    monkeypatch.setattr(template_config, "_pricing_path", lambda: pricing_path)
    return pricing


@pytest.fixture
def template_store(tmp_path, monkeypatch):
    source_templates_dir = template_config.PDF_TEMPLATES_DIR
    source_assets_dir = template_config.ASSETS_DIR
    templates_dir = tmp_path / "config" / "pdf_templates"
    assets_dir = tmp_path / "assets"

    copytree(source_templates_dir / "comparison", templates_dir / "comparison")
    copytree(source_assets_dir / "pdf_templates" / "comparison", assets_dir / "pdf_templates" / "comparison")

    monkeypatch.setattr(template_config, "PDF_TEMPLATES_DIR", templates_dir)
    monkeypatch.setattr(template_config, "ASSETS_DIR", assets_dir)
    return templates_dir / "comparison"


def add_valid_version(template_dir: Path, version: int) -> None:
    source_dir = template_dir / "versions" / "v1"
    version_dir = template_dir / "versions" / f"v{version}"
    copytree(source_dir, version_dir)

    assets_versions_dir = template_dir.parents[2] / "assets" / "pdf_templates" / "comparison" / "versions"
    copytree(assets_versions_dir / "v1", assets_versions_dir / f"v{version}")

    for filename in ("content.yaml", "theme.yaml", "assets.yaml"):
        path = version_dir / filename
        path.write_text(path.read_text(encoding="utf-8").replace("template_version: 1", f"template_version: {version}"), encoding="utf-8")
