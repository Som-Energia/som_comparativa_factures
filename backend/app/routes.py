from __future__ import annotations

from io import BytesIO

from flask import Blueprint, Response, jsonify, request, send_file

from .config import (
    TemplateResolutionError,
    TemplateValidationError,
    create_comparison_template_version,
    get_comparison_template_version_files,
    get_published_comparison_template_version,
    list_comparison_template_versions,
    preview_comparison_template_version,
    publish_comparison_template_version,
    rollback_comparison_template_version,
    update_comparison_template_version_files,
)
from .services.calculator import ComparisonInputError, build_comparison_report
from .services.reporting import render_report_html, render_report_html_for_bundle, render_report_pdf


api = Blueprint("api", __name__)

SAMPLE_PREVIEW_PAYLOAD = {
    "cups": "ES0210002100000000ZN0F",
    "titular": "Persona Persona",
    "billing_days": 30,
    "competitor_invoice_amount": 54.0,
    "energy_by_periods": {
        "P1": 34.41,
        "P2": 41.55,
        "P3": 88.63,
    },
    "contracted_power_kw_by_periods": {
        "P1": 2.3,
        "P2": 2.3,
    },
    "self_consumption_surplus_kwh": 0,
    "meter_rental_eur": 0.81,
    "vat_rate_percent": 21,
    "electric_tax_rate_percent": 5.11,
}


@api.get("/health")
def healthcheck():
    return {"status": "ok"}


@api.post("/compare")
def compare():
    payload = request.get_json(silent=True) or {}

    try:
        report = build_comparison_report(payload)
    except ComparisonInputError as exc:
        return jsonify({"errors": exc.errors}), 400

    return jsonify(report)


@api.post("/reports/comparison.pdf")
def comparison_report_pdf():
    payload = request.get_json(silent=True) or {}
    template_version = _extract_template_version(payload)
    if isinstance(template_version, Response):
        return template_version

    try:
        report = build_comparison_report(payload)
    except ComparisonInputError as exc:
        return jsonify({"errors": exc.errors}), 400

    try:
        pdf_bytes = render_report_pdf(report, template_version=template_version)
    except TemplateValidationError as exc:
        return jsonify({"errors": {"template_version": str(exc)}}), 422
    except TemplateResolutionError as exc:
        return jsonify({"errors": {"template_version": str(exc)}}), 404

    filename = f"comparison-report-{report['customer']['cups']}.pdf"
    return send_file(
        BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )


@api.get("/reports/comparison.preview")
def comparison_report_preview():
    template_version = _extract_template_version(request.args)
    if isinstance(template_version, Response):
        return template_version

    report = build_comparison_report(SAMPLE_PREVIEW_PAYLOAD)

    try:
        html = render_report_html(report, template_version=template_version)
    except TemplateValidationError as exc:
        return jsonify({"errors": {"template_version": str(exc)}}), 422
    except TemplateResolutionError as exc:
        return jsonify({"errors": {"template_version": str(exc)}}), 404

    return Response(html, mimetype="text/html")


@api.get("/templates/comparison/publication")
def comparison_template_publication_status():
    try:
        published_version = get_published_comparison_template_version()
    except TemplateResolutionError as exc:
        return jsonify({"errors": {"publication": str(exc)}}), 404

    return jsonify({"published_version": published_version})


@api.post("/templates/comparison/publish")
def comparison_template_publish():
    return _update_template_publication(action="publish")


@api.post("/templates/comparison/rollback")
def comparison_template_rollback():
    return _update_template_publication(action="rollback")


@api.get("/templates/comparison/versions")
def comparison_template_versions():
    try:
        published_version = get_published_comparison_template_version()
        versions = list_comparison_template_versions()
    except TemplateResolutionError as exc:
        return jsonify({"errors": {"template_versions": str(exc)}}), 404

    return jsonify(
        {
            "published_version": published_version,
            "versions": [
                {"version": version.version, "status": version.status}
                for version in versions
            ],
        }
    )


@api.get("/templates/comparison/versions/<version>")
def comparison_template_version_detail(version: str):
    try:
        payload = get_comparison_template_version_files(version)
    except (TemplateResolutionError, TemplateValidationError) as exc:
        return jsonify({"errors": {"template_version": str(exc)}}), 404

    return jsonify(payload)


@api.post("/templates/comparison/versions")
def comparison_template_create_version():
    payload = request.get_json(silent=True) or {}
    source_version = _extract_required_text(payload, "source_version")
    target_version = _extract_required_text(payload, "target_version")
    if isinstance(source_version, Response):
        return source_version
    if isinstance(target_version, Response):
        return target_version

    try:
        version_payload = create_comparison_template_version(source_version=source_version, target_version=target_version)
    except TemplateValidationError as exc:
        return jsonify({"errors": {"target_version": str(exc)}}), 422
    except TemplateResolutionError as exc:
        return jsonify({"errors": {"source_version": str(exc)}}), 404

    return jsonify(version_payload), 201


@api.put("/templates/comparison/versions/<version>")
def comparison_template_update_version(version: str):
    payload = request.get_json(silent=True) or {}
    files = _extract_template_files(payload)
    if isinstance(files, Response):
        return files

    try:
        version_payload = update_comparison_template_version_files(version, files)
    except TemplateValidationError as exc:
        return jsonify({"errors": {"template_version": str(exc)}}), 422
    except TemplateResolutionError as exc:
        return jsonify({"errors": {"template_version": str(exc)}}), 404

    return jsonify(version_payload)


@api.post("/templates/comparison/versions/<version>/preview")
def comparison_template_preview_version(version: str):
    payload = request.get_json(silent=True) or {}
    files = _extract_template_files(payload)
    if isinstance(files, Response):
        return files

    report = build_comparison_report(SAMPLE_PREVIEW_PAYLOAD)

    try:
        bundle = preview_comparison_template_version(version, files)
        html = render_report_html_for_bundle(report, bundle)
    except TemplateValidationError as exc:
        return jsonify({"errors": {"template_version": str(exc)}}), 422
    except TemplateResolutionError as exc:
        return jsonify({"errors": {"template_version": str(exc)}}), 404

    return jsonify({"html": html})


def _extract_template_version(source) -> str | None | Response:
    template_version_raw = source.get("template_version")
    if template_version_raw is None:
        return None

    template_version = str(template_version_raw).strip()
    if not template_version:
        response = jsonify({"errors": {"template_version": "La versio de plantilla no pot ser buida."}})
        response.status_code = 400
        return response

    return template_version


def _update_template_publication(*, action: str):
    payload = request.get_json(silent=True) or {}
    template_version = _extract_template_version(payload)
    if isinstance(template_version, Response):
        return template_version

    if template_version is None:
        return jsonify({"errors": {"template_version": "Cal indicar una versio de plantilla."}}), 400

    try:
        if action == "publish":
            bundle = publish_comparison_template_version(template_version)
            message = f"La versio {bundle.version} s'ha publicat correctament."
        else:
            bundle = rollback_comparison_template_version(template_version)
            message = f"S'ha fet rollback a la versio {bundle.version}."
    except TemplateValidationError as exc:
        return jsonify({"errors": {"template_version": str(exc)}}), 422
    except TemplateResolutionError as exc:
        return jsonify({"errors": {"template_version": str(exc)}}), 404

    return jsonify({"published_version": bundle.version, "message": message})


def _extract_required_text(source, key: str) -> str | Response:
    raw_value = source.get(key)
    if raw_value is None:
        response = jsonify({"errors": {key: f"Cal indicar {key}."}})
        response.status_code = 400
        return response

    value = str(raw_value).strip()
    if not value:
        response = jsonify({"errors": {key: f"{key} no pot ser buit."}})
        response.status_code = 400
        return response

    return value


def _extract_template_files(source) -> dict[str, str] | Response:
    files = source.get("files")
    if not isinstance(files, dict):
        response = jsonify({"errors": {"files": "Cal indicar els fitxers de plantilla."}})
        response.status_code = 400
        return response

    required = {"content", "theme", "assets"}
    missing = sorted(required - set(files))
    if missing:
        response = jsonify({"errors": {"files": f"Falten fitxers obligatoris: {', '.join(missing)}."}})
        response.status_code = 400
        return response

    extracted_files = {}
    for key in required:
        value = files.get(key)
        if not isinstance(value, str):
            response = jsonify({"errors": {"files": f"El fitxer {key} ha de ser text."}})
            response.status_code = 400
            return response
        extracted_files[key] = value

    return extracted_files
