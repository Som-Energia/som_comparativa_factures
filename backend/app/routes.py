from __future__ import annotations

from io import BytesIO

from flask import Blueprint, jsonify, request, send_file

from .config import TemplateResolutionError, TemplateValidationError
from .services.calculator import ComparisonInputError, build_comparison_report
from .services.reporting import render_report_pdf


api = Blueprint("api", __name__)


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
    template_version_raw = payload.get("template_version")
    template_version = None

    if template_version_raw is not None:
        template_version = str(template_version_raw).strip()
        if not template_version:
            return jsonify({"errors": {"template_version": "La versio de plantilla no pot ser buida."}}), 400

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
