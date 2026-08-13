FROM python:3.12-slim

ENV POETRY_VIRTUALENVS_CREATE=false \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        fonts-dejavu-core \
        libffi8 \
        libgdk-pixbuf-2.0-0 \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        shared-mime-info \
        unzip \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir poetry==2.1.3

COPY backend/pyproject.toml backend/poetry.lock ./
RUN poetry install --only main --no-root

COPY backend/ ./
RUN mkdir -p /seed-reference/reference
COPY ["assets/CA_PLANTILLA_Domèstic_Simulació_Factura_Som Energia.pdf", "/seed-reference/reference/comparison-v3.pdf"]
COPY ["assets/CA_PLANTILLA_Domèstic_Simulació_Factura_Som Energia.pdf", "/seed-reference/reference/comparison-v3-ca.pdf"]
COPY ["assets/ES_PLANTILLA_Domèstic_Simulació_Factura_Som Energia.pdf", "/seed-reference/reference/comparison-v3-es.pdf"]
COPY ["assets/CA_PLANTILLA_Domèstic_Simulació_Factura_Som Energia.docx", "/tmp/comparison-v3.docx"]
RUN unzip -j /tmp/comparison-v3.docx \
        word/fonts/Outfit-regular.ttf \
        word/fonts/OutfitSemiBold-regular.ttf \
        word/fonts/Outfit-bold.ttf \
        -d /seed-reference/reference \
    && rm /tmp/comparison-v3.docx
RUN cp -a /app/config /seed-config \
    && cp -a /app/assets /seed-assets \
    && chmod +x /app/docker-entrypoint.sh

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "120", "run:app"]
