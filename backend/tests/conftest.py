from pathlib import Path
from shutil import copytree

import pytest

import app.config as template_config


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
