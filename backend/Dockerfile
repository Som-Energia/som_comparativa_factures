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
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir poetry==2.1.3

COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-root

COPY . ./
RUN cp -a /app/config /seed-config \
    && cp -a /app/assets /seed-assets \
    && chmod +x /app/docker-entrypoint.sh

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "120", "run:app"]
