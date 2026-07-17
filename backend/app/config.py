from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import re
import tempfile
from typing import Any
from urllib.parse import urlparse

import yaml


CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"
ASSETS_DIR = Path(__file__).resolve().parents[1] / "assets"
PDF_TEMPLATES_DIR = CONFIG_DIR / "pdf_templates"


class TemplateResolutionError(Exception):
    pass


class TemplateValidationError(TemplateResolutionError):
    pass


@dataclass(frozen=True)
class TemplateBundle:
    template_id: str
    version: str
    version_dir: Path
    content_path: Path
    theme_path: Path
    assets_manifest_path: Path
    assets_dir: Path
    content: dict[str, Any]
    theme: dict[str, Any]
    assets: dict[str, Any]


ALLOWED_TEMPLATE_TOKENS = {
    "customer.titular",
    "customer.cups",
    "input.billing_days",
    "pricing.tariff_name",
    "pricing.effective_date",
    "comparison.savings_label",
}
FORBIDDEN_TEXT_FRAGMENTS = ("{{", "{%", "}}", "</", "<", ">")
HEX_COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")
ALLOWED_ASSET_EXTENSIONS = {".png", ".jpg", ".jpeg", ".svg"}
MAX_ASSET_SIZE_BYTES = 2 * 1024 * 1024
TEMPLATE_VERSION_PATTERN = re.compile(r"^v([1-9][0-9]*)$")


@lru_cache(maxsize=1)
def load_pricing_config() -> dict:
    with (CONFIG_DIR / "pricing.json").open("r", encoding="utf-8") as handle:
        return json.load(handle)


def resolve_comparison_template_bundle(version: str | None = None) -> TemplateBundle:
    return _resolve_template_bundle("comparison", version=version)


def get_published_comparison_template_version() -> str:
    return _load_published_template_version(PDF_TEMPLATES_DIR / "comparison")


def publish_comparison_template_version(version: str) -> TemplateBundle:
    template_dir = PDF_TEMPLATES_DIR / "comparison"
    bundle = _resolve_template_bundle("comparison", version=version)
    _write_published_template_version(template_dir, bundle.version)
    return bundle


def rollback_comparison_template_version(version: str) -> TemplateBundle:
    return publish_comparison_template_version(version)


def _resolve_template_bundle(template_id: str, version: str | None = None) -> TemplateBundle:
    template_dir = PDF_TEMPLATES_DIR / template_id
    resolved_version = version or _load_published_template_version(template_dir)
    version_number = _extract_template_version_number(resolved_version)
    version_dir = template_dir / "versions" / resolved_version

    if not version_dir.is_dir():
        raise TemplateResolutionError(
            f"La versio '{resolved_version}' del template '{template_id}' no existeix."
        )

    bundle = TemplateBundle(
        template_id=template_id,
        version=resolved_version,
        version_dir=version_dir,
        content_path=version_dir / "content.yaml",
        theme_path=version_dir / "theme.yaml",
        assets_manifest_path=version_dir / "assets.yaml",
        assets_dir=ASSETS_DIR / "pdf_templates" / template_id / "versions" / resolved_version,
        content={},
        theme={},
        assets={},
    )
    _validate_template_bundle(bundle)

    content = _load_yaml_file(bundle.content_path)
    theme = _load_yaml_file(bundle.theme_path)
    assets_manifest = _load_yaml_file(bundle.assets_manifest_path)

    _validate_content_template(content, version_number)
    _validate_theme_template(theme, version_number)
    assets = _resolve_assets_manifest(assets_manifest, bundle.assets_dir, version_number)

    bundle = TemplateBundle(
        template_id=template_id,
        version=resolved_version,
        version_dir=version_dir,
        content_path=bundle.content_path,
        theme_path=bundle.theme_path,
        assets_manifest_path=bundle.assets_manifest_path,
        assets_dir=bundle.assets_dir,
        content=content,
        theme=theme,
        assets=assets,
    )
    return bundle


def _load_published_template_version(template_dir: Path) -> str:
    published_path = template_dir / "published.json"
    if not published_path.is_file():
        raise TemplateResolutionError(
            f"Falta el fitxer de publicacio del template '{template_dir.name}'."
        )

    try:
        with published_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except json.JSONDecodeError as exc:
        raise TemplateResolutionError(
            f"El fitxer de publicacio del template '{template_dir.name}' no es un JSON valid."
        ) from exc

    if not isinstance(payload, dict) or set(payload) != {"current_version"}:
        raise TemplateResolutionError(
            f"El fitxer de publicacio del template '{template_dir.name}' ha de contenir nomes 'current_version'."
        )

    version = payload["current_version"]
    if not isinstance(version, str):
        raise TemplateResolutionError(
            f"El fitxer de publicacio del template '{template_dir.name}' ha de definir 'current_version' com a text."
        )
    return _parse_template_version(version)


def _write_published_template_version(template_dir: Path, version: str) -> None:
    published_path = template_dir / "published.json"
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=template_dir,
        prefix=".published-",
        suffix=".json",
        delete=False,
    ) as handle:
        json.dump({"current_version": version}, handle, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
        temporary_path = Path(handle.name)

    try:
        os.replace(temporary_path, published_path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _parse_template_version(version: str) -> str:
    normalized_version = version.strip()
    if not TEMPLATE_VERSION_PATTERN.fullmatch(normalized_version):
        raise TemplateResolutionError("La versio de template ha de tenir el format 'v' seguit d'un enter positiu.")
    return normalized_version


def _extract_template_version_number(version: str) -> int:
    normalized_version = _parse_template_version(version)
    match = TEMPLATE_VERSION_PATTERN.fullmatch(normalized_version)
    assert match is not None
    return int(match.group(1))


def _validate_template_bundle(bundle: TemplateBundle) -> None:
    missing_files = [
        _describe_path(path)
        for path in (bundle.content_path, bundle.theme_path, bundle.assets_manifest_path)
        if not path.is_file()
    ]
    if missing_files:
        raise TemplateResolutionError(
            f"La versio '{bundle.version}' del template '{bundle.template_id}' esta incompleta: {', '.join(missing_files)}."
        )

    if not bundle.assets_dir.is_dir():
        assets_path = _describe_path(bundle.assets_dir)
        raise TemplateResolutionError(
            f"La versio '{bundle.version}' del template '{bundle.template_id}' no te directori d'assets: {assets_path}."
        )


def _load_yaml_file(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle)
    except yaml.YAMLError as exc:
        raise TemplateValidationError(f"El fitxer '{path.name}' no es un YAML valid.") from exc

    if not isinstance(payload, dict):
        raise TemplateValidationError(f"El fitxer '{path.name}' ha de definir un objecte YAML al nivell arrel.")

    return payload


def _validate_content_template(content: dict[str, Any], expected_version: int) -> None:
    _validate_exact_keys(content, "content", required={"meta", "hero", "summary", "invoice_card", "energy_table", "breakdown", "legal", "cta"})

    meta = _expect_dict(content["meta"], "content.meta")
    _validate_exact_keys(meta, "content.meta", required={"template_id", "template_version", "locale"})
    _validate_fixed_string(meta["template_id"], "content.meta.template_id", "comparison")
    _validate_integer(meta["template_version"], "content.meta.template_version", exact=expected_version)
    _validate_fixed_string(meta["locale"], "content.meta.locale", "ca")

    hero = _expect_dict(content["hero"], "content.hero")
    _validate_exact_keys(hero, "content.hero", required={"title", "intro", "customer_labels", "badge_text"})
    _validate_plain_string(hero["title"], "content.hero.title", min_length=1, max_length=80)
    _validate_string_list(hero["intro"], "content.hero.intro", min_items=1, max_items=2, min_length=1, max_length=320)
    hero_labels = _expect_dict(hero["customer_labels"], "content.hero.customer_labels")
    _validate_exact_keys(hero_labels, "content.hero.customer_labels", required={"titular", "cups"})
    _validate_plain_string(hero_labels["titular"], "content.hero.customer_labels.titular", min_length=1, max_length=30)
    _validate_plain_string(hero_labels["cups"], "content.hero.customer_labels.cups", min_length=1, max_length=30)
    _validate_plain_string(hero["badge_text"], "content.hero.badge_text", min_length=1, max_length=120, allow_tokens=True)

    summary = _expect_dict(content["summary"], "content.summary")
    _validate_exact_keys(summary, "content.summary", required={"title", "columns"})
    _validate_plain_string(summary["title"], "content.summary.title", min_length=1, max_length=80)
    summary_columns = _expect_dict(summary["columns"], "content.summary.columns")
    _validate_exact_keys(summary_columns, "content.summary.columns", required={"current_cost", "som_cost", "savings_positive", "savings_negative"})
    for key in ("current_cost", "som_cost", "savings_positive", "savings_negative"):
        _validate_plain_string(summary_columns[key], f"content.summary.columns.{key}", min_length=1, max_length=40)

    invoice_card = _expect_dict(content["invoice_card"], "content.invoice_card")
    _validate_exact_keys(invoice_card, "content.invoice_card", required={"title", "labels"})
    _validate_plain_string(invoice_card["title"], "content.invoice_card.title", min_length=1, max_length=60)
    invoice_labels = _expect_dict(invoice_card["labels"], "content.invoice_card.labels")
    _validate_exact_keys(invoice_labels, "content.invoice_card.labels", required={"titular", "cups", "billing_days"})
    for key in ("titular", "cups", "billing_days"):
        _validate_plain_string(invoice_labels[key], f"content.invoice_card.labels.{key}", min_length=1, max_length=30)

    energy_table = _expect_dict(content["energy_table"], "content.energy_table")
    _validate_exact_keys(energy_table, "content.energy_table", required={"title", "columns"})
    _validate_plain_string(energy_table["title"], "content.energy_table.title", min_length=1, max_length=60)
    energy_columns = _expect_dict(energy_table["columns"], "content.energy_table.columns")
    _validate_exact_keys(energy_columns, "content.energy_table.columns", required={"period", "kwh", "unit_price", "amount"})
    for key in ("period", "kwh", "unit_price", "amount"):
        _validate_plain_string(energy_columns[key], f"content.energy_table.columns.{key}", min_length=1, max_length=20)

    breakdown = _expect_dict(content["breakdown"], "content.breakdown")
    _validate_exact_keys(breakdown, "content.breakdown", required={"title"})
    _validate_plain_string(breakdown["title"], "content.breakdown.title", min_length=1, max_length=60)

    legal = _expect_dict(content["legal"], "content.legal")
    _validate_exact_keys(legal, "content.legal", required={"disclaimer"})
    _validate_plain_string(legal["disclaimer"], "content.legal.disclaimer", min_length=1, max_length=240)

    cta = _expect_dict(content["cta"], "content.cta")
    _validate_exact_keys(cta, "content.cta", required={"title", "body", "services_title", "services", "primary_action"})
    _validate_plain_string(cta["title"], "content.cta.title", min_length=1, max_length=80)
    _validate_string_list(cta["body"], "content.cta.body", min_items=1, max_items=2, min_length=1, max_length=320)
    _validate_plain_string(cta["services_title"], "content.cta.services_title", min_length=1, max_length=60)
    _validate_string_list(cta["services"], "content.cta.services", min_items=1, max_items=6, min_length=1, max_length=120)
    _validate_cta_action(cta["primary_action"], "content.cta.primary_action")


def _validate_theme_template(theme: dict[str, Any], expected_version: int) -> None:
    _validate_exact_keys(theme, "theme", required={"meta", "page", "colors", "typography", "shape", "spacing"})

    meta = _expect_dict(theme["meta"], "theme.meta")
    _validate_exact_keys(meta, "theme.meta", required={"template_id", "template_version"})
    _validate_fixed_string(meta["template_id"], "theme.meta.template_id", "comparison")
    _validate_integer(meta["template_version"], "theme.meta.template_version", exact=expected_version)

    page = _expect_dict(theme["page"], "theme.page")
    _validate_exact_keys(page, "theme.page", required={"size", "margin_mm"})
    _validate_fixed_string(page["size"], "theme.page.size", "A4")
    page_margin = _expect_dict(page["margin_mm"], "theme.page.margin_mm")
    _validate_exact_keys(page_margin, "theme.page.margin_mm", required={"top", "right", "bottom", "left"})
    for key in ("top", "right", "bottom", "left"):
        _validate_integer(page_margin[key], f"theme.page.margin_mm.{key}", min_value=10, max_value=30)

    colors = _expect_dict(theme["colors"], "theme.colors")
    _validate_exact_keys(colors, "theme.colors", required={"background", "ink", "muted", "brand", "accent", "soft", "line", "surface", "inverse_text"})
    for key in ("background", "ink", "muted", "brand", "accent", "soft", "line", "surface", "inverse_text"):
        _validate_hex_color(colors[key], f"theme.colors.{key}")

    typography = _expect_dict(theme["typography"], "theme.typography")
    _validate_exact_keys(typography, "theme.typography", required={"font_family", "body_size_px", "h1_size_px", "h2_size_px", "h3_size_px"})
    _validate_plain_string(typography["font_family"], "theme.typography.font_family", min_length=1, max_length=80)
    _validate_integer(typography["body_size_px"], "theme.typography.body_size_px", min_value=10, max_value=14)
    _validate_integer(typography["h1_size_px"], "theme.typography.h1_size_px", min_value=24, max_value=36)
    _validate_integer(typography["h2_size_px"], "theme.typography.h2_size_px", min_value=20, max_value=30)
    _validate_integer(typography["h3_size_px"], "theme.typography.h3_size_px", min_value=16, max_value=22)

    shape = _expect_dict(theme["shape"], "theme.shape")
    _validate_exact_keys(shape, "theme.shape", required={"card_radius_px", "badge_radius_px"})
    _validate_integer(shape["card_radius_px"], "theme.shape.card_radius_px", min_value=0, max_value=24)
    _validate_integer(shape["badge_radius_px"], "theme.shape.badge_radius_px", min_value=8, max_value=999)

    spacing = _expect_dict(theme["spacing"], "theme.spacing")
    _validate_exact_keys(spacing, "theme.spacing", required={"card_padding_px", "table_cell_px"})
    _validate_integer(spacing["card_padding_px"], "theme.spacing.card_padding_px", min_value=8, max_value=24)
    _validate_integer(spacing["table_cell_px"], "theme.spacing.table_cell_px", min_value=6, max_value=16)


def _validate_assets_template(assets_payload: dict[str, Any], assets_dir: Path, expected_version: int) -> None:
    _validate_exact_keys(assets_payload, "assets", required={"meta", "registry", "slots"})

    meta = _expect_dict(assets_payload["meta"], "assets.meta")
    _validate_exact_keys(meta, "assets.meta", required={"template_id", "template_version"})
    _validate_fixed_string(meta["template_id"], "assets.meta.template_id", "comparison")
    _validate_integer(meta["template_version"], "assets.meta.template_version", exact=expected_version)

    registry = _expect_dict(assets_payload["registry"], "assets.registry")
    for asset_id, entry in registry.items():
        if not isinstance(asset_id, str) or not asset_id:
            raise TemplateValidationError("assets.registry nomes admet ids de text no buits.")
        _validate_asset_id(asset_id, "assets.registry")
        max_alt_length = 80 if asset_id.startswith("logo") else 120
        min_width = 40 if asset_id.startswith("logo") else 80
        max_width = 240 if asset_id.startswith("logo") else 320
        _validate_asset_entry(entry, f"assets.registry.{asset_id}", assets_dir, min_width=min_width, max_width=max_width, max_alt_length=max_alt_length)

    slots = _expect_dict(assets_payload["slots"], "assets.slots")
    _validate_exact_keys(slots, "assets.slots", required={"logo", "hero_illustration"})
    _validate_asset_slot(slots["logo"], "assets.slots.logo", registry)
    _validate_asset_slot(slots["hero_illustration"], "assets.slots.hero_illustration", registry)


def _resolve_assets_manifest(assets_payload: dict[str, Any], assets_dir: Path, expected_version: int) -> dict[str, Any]:
    _validate_assets_template(assets_payload, assets_dir, expected_version)

    registry = assets_payload["registry"]
    slots = assets_payload["slots"]

    resolved_slots: dict[str, Any] = {}
    for slot_name, asset_id in slots.items():
        if asset_id is None:
            resolved_slots[slot_name] = None
            continue

        entry = registry[asset_id]
        resolved_path = _validate_asset_path(entry["path"], f"assets.registry.{asset_id}.path", assets_dir)
        resolved_slots[slot_name] = {
            "id": asset_id,
            "src": resolved_path.as_uri(),
            "alt": entry["alt"],
            "max_width_px": entry["max_width_px"],
        }

    return resolved_slots


def _validate_cta_action(value: Any, path: str) -> None:
    if value is None:
        return

    action = _expect_dict(value, path)
    _validate_exact_keys(action, path, required={"label", "url"})
    _validate_plain_string(action["label"], f"{path}.label", min_length=1, max_length=40)
    _validate_https_url(action["url"], f"{path}.url", min_length=1, max_length=200)


def _validate_asset_entry(value: Any, path: str, assets_dir: Path, *, min_width: int, max_width: int, max_alt_length: int) -> None:
    if value is None:
        return

    asset = _expect_dict(value, path)
    _validate_exact_keys(asset, path, required={"path", "alt", "max_width_px"})
    asset_path = _validate_asset_path(asset["path"], f"{path}.path", assets_dir)
    _validate_plain_string(asset["alt"], f"{path}.alt", min_length=1, max_length=max_alt_length)
    _validate_integer(asset["max_width_px"], f"{path}.max_width_px", min_value=min_width, max_value=max_width)

    if not asset_path.is_file():
        relative_path = asset_path.relative_to(assets_dir)
        raise TemplateValidationError(f"{path}.path referencia un asset inexistent: {relative_path}.")

    if asset_path.stat().st_size > MAX_ASSET_SIZE_BYTES:
        raise TemplateValidationError(f"{path}.path supera el limit de 2 MB.")


def _validate_asset_slot(value: Any, path: str, registry: dict[str, Any]) -> None:
    if value is None:
        return

    if not isinstance(value, str):
        raise TemplateValidationError(f"{path} ha de ser `null` o un id d'asset.")

    _validate_asset_id(value, path)
    if value not in registry:
        raise TemplateValidationError(f"{path} referencia un asset no declarat: {value}.")


def _validate_asset_id(value: str, path: str) -> None:
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", value):
        raise TemplateValidationError(f"{path} ha de fer servir ids en minuscules amb `a-z0-9._-`.")


def _validate_asset_path(value: Any, path: str, assets_dir: Path) -> Path:
    asset_path = _validate_plain_string(value, path, min_length=1, max_length=120)

    if asset_path.startswith(("http://", "https://", "data:")):
        raise TemplateValidationError(f"{path} no pot ser una URL remota ni un data URI.")

    relative_path = Path(asset_path)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise TemplateValidationError(f"{path} ha de ser una ruta relativa dins del directori d'assets.")

    if relative_path.suffix.lower() not in ALLOWED_ASSET_EXTENSIONS:
        raise TemplateValidationError(
            f"{path} ha de tenir una extensio valida: {', '.join(sorted(ALLOWED_ASSET_EXTENSIONS))}."
        )

    resolved_path = (assets_dir / relative_path).resolve()
    try:
        resolved_path.relative_to(assets_dir.resolve())
    except ValueError as exc:
        raise TemplateValidationError(f"{path} surt del directori d'assets permes.") from exc

    return resolved_path


def _expect_dict(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TemplateValidationError(f"{path} ha de ser un objecte.")
    return value


def _validate_exact_keys(payload: dict[str, Any], path: str, *, required: set[str]) -> None:
    missing = sorted(required - set(payload))
    if missing:
        raise TemplateValidationError(f"{path} no defineix les claus obligatories: {', '.join(missing)}.")

    unknown = sorted(set(payload) - required)
    if unknown:
        raise TemplateValidationError(f"{path} conté claus no permeses: {', '.join(unknown)}.")


def _validate_fixed_string(value: Any, path: str, expected: str) -> None:
    string_value = _validate_plain_string(value, path, min_length=len(expected), max_length=len(expected))
    if string_value != expected:
        raise TemplateValidationError(f"{path} ha de ser exactament '{expected}'.")


def _validate_plain_string(value: Any, path: str, *, min_length: int, max_length: int, allow_tokens: bool = False) -> str:
    if not isinstance(value, str):
        raise TemplateValidationError(f"{path} ha de ser un text pla.")

    if len(value) < min_length or len(value) > max_length:
        raise TemplateValidationError(f"{path} ha de tenir entre {min_length} i {max_length} caracters.")

    for fragment in FORBIDDEN_TEXT_FRAGMENTS:
        if fragment in value:
            raise TemplateValidationError(f"{path} conté sintaxi o markup no permes.")

    _validate_template_tokens(value, path, allow_tokens=allow_tokens)
    return value


def _validate_template_tokens(value: str, path: str, *, allow_tokens: bool) -> None:
    matches = re.findall(r"\{([^{}]+)\}", value)
    stripped_value = re.sub(r"\{([^{}]+)\}", "", value)

    if "{" in stripped_value or "}" in stripped_value:
        raise TemplateValidationError(f"{path} conté placeholders mal formats.")

    if matches and not allow_tokens:
        raise TemplateValidationError(f"{path} no permet placeholders de template.")

    for token in matches:
        if token not in ALLOWED_TEMPLATE_TOKENS:
            raise TemplateValidationError(f"{path} conté un placeholder no permes: {{{token}}}.")


def _validate_string_list(value: Any, path: str, *, min_items: int, max_items: int, min_length: int, max_length: int) -> None:
    if not isinstance(value, list):
        raise TemplateValidationError(f"{path} ha de ser una llista.")

    if len(value) < min_items or len(value) > max_items:
        raise TemplateValidationError(f"{path} ha de contenir entre {min_items} i {max_items} elements.")

    for index, item in enumerate(value):
        _validate_plain_string(item, f"{path}[{index}]", min_length=min_length, max_length=max_length)


def _validate_integer(value: Any, path: str, *, min_value: int | None = None, max_value: int | None = None, exact: int | None = None) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TemplateValidationError(f"{path} ha de ser un enter.")

    if exact is not None and value != exact:
        raise TemplateValidationError(f"{path} ha de valer exactament {exact}.")

    if min_value is not None and value < min_value:
        raise TemplateValidationError(f"{path} ha de ser com a minim {min_value}.")

    if max_value is not None and value > max_value:
        raise TemplateValidationError(f"{path} ha de ser com a maxim {max_value}.")


def _validate_hex_color(value: Any, path: str) -> None:
    color = _validate_plain_string(value, path, min_length=7, max_length=7)
    if not HEX_COLOR_PATTERN.fullmatch(color):
        raise TemplateValidationError(f"{path} ha de tenir format hex #RRGGBB.")


def _validate_https_url(value: Any, path: str, *, min_length: int, max_length: int) -> None:
    url = _validate_plain_string(value, path, min_length=min_length, max_length=max_length)
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise TemplateValidationError(f"{path} ha de ser una URL absoluta amb https.")


def _describe_path(path: Path) -> str:
    backend_root = Path(__file__).resolve().parents[1]
    try:
        return str(path.relative_to(backend_root))
    except ValueError:
        return str(path)
