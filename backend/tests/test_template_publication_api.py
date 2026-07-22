from app import create_app

from conftest import TEST_DRAFT_VERSION, add_valid_version


def test_get_publication_status_returns_current_version(template_store):
    client = create_app().test_client()

    response = client.get("/api/templates/comparison/publication")

    assert response.status_code == 200
    assert response.get_json() == {"published_version": "v1"}


def test_publish_endpoint_updates_the_published_version(template_store):
    add_valid_version(template_store, TEST_DRAFT_VERSION)
    client = create_app().test_client()

    response = client.post("/api/templates/comparison/publish", json={"template_version": "v99"})

    assert response.status_code == 200
    assert response.get_json()["published_version"] == "v99"


def test_rollback_endpoint_updates_the_published_version(template_store):
    add_valid_version(template_store, TEST_DRAFT_VERSION)
    client = create_app().test_client()
    client.post("/api/templates/comparison/publish", json={"template_version": "v99"})

    response = client.post("/api/templates/comparison/rollback", json={"template_version": "v1"})

    assert response.status_code == 200
    assert response.get_json()["published_version"] == "v1"


def test_publish_endpoint_requires_template_version(template_store):
    client = create_app().test_client()

    response = client.post("/api/templates/comparison/publish", json={})

    assert response.status_code == 400
    assert response.get_json()["errors"]["template_version"] == "Cal indicar una versio de plantilla."


def test_publish_endpoint_returns_validation_error_for_invalid_bundle(template_store):
    add_valid_version(template_store, TEST_DRAFT_VERSION)
    version_content = template_store / "versions" / "v99" / "content.yaml"
    version_content.write_text(
        version_content.read_text(encoding="utf-8").replace("template_version: 99", "template_version: 1"),
        encoding="utf-8",
    )
    client = create_app().test_client()

    response = client.post("/api/templates/comparison/publish", json={"template_version": "v99"})

    assert response.status_code == 422
    assert "template_version" in response.get_json()["errors"]


def test_versions_endpoint_lists_statuses(template_store):
    add_valid_version(template_store, TEST_DRAFT_VERSION)
    client = create_app().test_client()

    response = client.get("/api/templates/comparison/versions")

    assert response.status_code == 200
    assert response.get_json() == {
        "published_version": "v1",
        "versions": [
            {"version": "v99", "status": "draft"},
            {"version": "v2", "status": "draft"},
            {"version": "v1", "status": "published"},
        ],
    }


def test_version_detail_returns_yaml_files(template_store):
    client = create_app().test_client()

    response = client.get("/api/templates/comparison/versions/v1")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["version"] == "v1"
    assert payload["status"] == "published"
    assert "meta:" in payload["files"]["content"]
    assert "meta:" in payload["files"]["theme"]
    assert "registry:" in payload["files"]["assets"]


def test_create_version_clones_from_existing_version(template_store):
    client = create_app().test_client()

    response = client.post(
        "/api/templates/comparison/versions",
        json={"source_version": "v1", "target_version": "v99"},
    )

    assert response.status_code == 201
    payload = response.get_json()
    assert payload["version"] == "v99"
    assert payload["status"] == "draft"
    assert "template_version: 99" in payload["files"]["content"]


def test_update_version_rejects_published_versions(template_store):
    client = create_app().test_client()
    detail = client.get("/api/templates/comparison/versions/v1").get_json()

    response = client.put(
        "/api/templates/comparison/versions/v1",
        json={"files": detail["files"]},
    )

    assert response.status_code == 422
    assert "no es editable" in response.get_json()["errors"]["template_version"]


def test_update_version_saves_a_draft(template_store):
    add_valid_version(template_store, TEST_DRAFT_VERSION)
    client = create_app().test_client()
    detail = client.get("/api/templates/comparison/versions/v99").get_json()
    detail["files"]["content"] = detail["files"]["content"].replace(
        "Simulacio de factura Som Energia",
        "Nova simulacio comercial",
    )

    response = client.put(
        "/api/templates/comparison/versions/v99",
        json={"files": detail["files"]},
    )

    assert response.status_code == 200
    assert "Nova simulacio comercial" in response.get_json()["files"]["content"]


def test_preview_version_renders_html_from_unsaved_yaml(template_store):
    add_valid_version(template_store, TEST_DRAFT_VERSION)
    client = create_app().test_client()
    detail = client.get("/api/templates/comparison/versions/v99").get_json()
    detail["files"]["content"] = detail["files"]["content"].replace(
        "Simulacio de factura Som Energia",
        "Preview de prova",
    )

    response = client.post(
        "/api/templates/comparison/versions/v99/preview",
        json={"files": detail["files"]},
    )

    assert response.status_code == 200
    assert "Preview de prova" in response.get_json()["html"]
