import json

import pytest

from app.config import (
    TemplateResolutionError,
    TemplateValidationError,
    get_published_comparison_template_version,
    publish_comparison_template_version,
    resolve_comparison_template_bundle,
    rollback_comparison_template_version,
)

from conftest import TEST_DRAFT_VERSION, add_valid_version


def test_resolves_the_version_pointed_to_by_published_json(template_store):
    add_valid_version(template_store, TEST_DRAFT_VERSION)
    (template_store / "published.json").write_text('{"current_version": "v99"}\n', encoding="utf-8")

    bundle = resolve_comparison_template_bundle()

    assert bundle.version == "v99"


def test_publish_updates_the_published_pointer_after_validation(template_store):
    add_valid_version(template_store, TEST_DRAFT_VERSION)

    bundle = publish_comparison_template_version("v99")

    assert bundle.version == "v99"
    assert get_published_comparison_template_version() == "v99"
    assert json.loads((template_store / "published.json").read_text(encoding="utf-8")) == {"current_version": "v99"}


def test_rollback_republishes_a_previous_valid_version(template_store):
    add_valid_version(template_store, TEST_DRAFT_VERSION)
    publish_comparison_template_version("v99")

    rollback_comparison_template_version("v1")

    assert get_published_comparison_template_version() == "v1"


def test_invalid_version_is_not_published(template_store):
    invalid_version_dir = template_store / "versions" / "v99"
    invalid_version_dir.mkdir()

    with pytest.raises(TemplateResolutionError):
        publish_comparison_template_version("v99")

    assert get_published_comparison_template_version() == "v1"


def test_version_with_inconsistent_manifest_is_not_published(template_store):
    add_valid_version(template_store, TEST_DRAFT_VERSION)
    content_path = template_store / "versions" / "v99" / "content.yaml"
    content_path.write_text(content_path.read_text(encoding="utf-8").replace("template_version: 99", "template_version: 1"), encoding="utf-8")

    with pytest.raises(TemplateValidationError):
        publish_comparison_template_version("v99")

    assert get_published_comparison_template_version() == "v1"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"current_version": ""},
        {"current_version": "v1", "unexpected": True},
        {"current_version": "v99"},
    ],
)
def test_invalid_published_pointer_is_rejected(template_store, payload):
    (template_store / "published.json").write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(TemplateResolutionError):
        resolve_comparison_template_bundle()


def test_malformed_published_json_is_rejected(template_store):
    (template_store / "published.json").write_text("{not-json", encoding="utf-8")

    with pytest.raises(TemplateResolutionError):
        resolve_comparison_template_bundle()
