from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"
ASSETS_DIR = Path(__file__).resolve().parents[1] / "assets"
PDF_TEMPLATES_DIR = CONFIG_DIR / "pdf_templates"


class TemplateResolutionError(Exception):
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


@lru_cache(maxsize=1)
def load_pricing_config() -> dict:
    with (CONFIG_DIR / "pricing.json").open("r", encoding="utf-8") as handle:
        return json.load(handle)


def resolve_comparison_template_bundle(version: str | None = None) -> TemplateBundle:
    return _resolve_template_bundle("comparison", version=version)


def _resolve_template_bundle(template_id: str, version: str | None = None) -> TemplateBundle:
    template_dir = PDF_TEMPLATES_DIR / template_id
    resolved_version = version or _load_published_template_version(template_dir)
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
    )
    _validate_template_bundle(bundle)
    return bundle


def _load_published_template_version(template_dir: Path) -> str:
    published_path = template_dir / "published.json"
    if not published_path.is_file():
        raise TemplateResolutionError(
            f"Falta el fitxer de publicacio del template '{template_dir.name}'."
        )

    with published_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    version = str(payload.get("current_version", "")).strip()
    if not version:
        raise TemplateResolutionError(
            f"El fitxer de publicacio del template '{template_dir.name}' no defineix 'current_version'."
        )
    return version


def _validate_template_bundle(bundle: TemplateBundle) -> None:
    missing_files = [
        str(path.relative_to(Path(__file__).resolve().parents[1]))
        for path in (bundle.content_path, bundle.theme_path, bundle.assets_manifest_path)
        if not path.is_file()
    ]
    if missing_files:
        raise TemplateResolutionError(
            f"La versio '{bundle.version}' del template '{bundle.template_id}' esta incompleta: {', '.join(missing_files)}."
        )

    if not bundle.assets_dir.is_dir():
        assets_path = bundle.assets_dir.relative_to(Path(__file__).resolve().parents[1])
        raise TemplateResolutionError(
            f"La versio '{bundle.version}' del template '{bundle.template_id}' no te directori d'assets: {assets_path}."
        )
