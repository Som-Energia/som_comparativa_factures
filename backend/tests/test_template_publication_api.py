from app import create_app

from conftest import add_valid_version


def test_get_publication_status_returns_current_version(template_store):
    client = create_app().test_client()

    response = client.get("/api/templates/comparison/publication")

    assert response.status_code == 200
    assert response.get_json() == {"published_version": "v1"}


def test_publish_endpoint_updates_the_published_version(template_store):
    add_valid_version(template_store, 2)
    client = create_app().test_client()

    response = client.post("/api/templates/comparison/publish", json={"template_version": "v2"})

    assert response.status_code == 200
    assert response.get_json()["published_version"] == "v2"


def test_rollback_endpoint_updates_the_published_version(template_store):
    add_valid_version(template_store, 2)
    client = create_app().test_client()
    client.post("/api/templates/comparison/publish", json={"template_version": "v2"})

    response = client.post("/api/templates/comparison/rollback", json={"template_version": "v1"})

    assert response.status_code == 200
    assert response.get_json()["published_version"] == "v1"


def test_publish_endpoint_requires_template_version(template_store):
    client = create_app().test_client()

    response = client.post("/api/templates/comparison/publish", json={})

    assert response.status_code == 400
    assert response.get_json()["errors"]["template_version"] == "Cal indicar una versio de plantilla."


def test_publish_endpoint_returns_validation_error_for_invalid_bundle(template_store):
    add_valid_version(template_store, 2)
    version_content = template_store / "versions" / "v2" / "content.yaml"
    version_content.write_text(
        version_content.read_text(encoding="utf-8").replace("template_version: 2", "template_version: 1"),
        encoding="utf-8",
    )
    client = create_app().test_client()

    response = client.post("/api/templates/comparison/publish", json={"template_version": "v2"})

    assert response.status_code == 422
    assert "template_version" in response.get_json()["errors"]
