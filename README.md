# webservice_factura

MVP per generar una comparativa de factura amb Som Energia a partir d'un formulari web i exportar-la a PDF.

## Arquitectura

- `frontend/`: React + Vite, formulari d'una sola pantalla i resum previ.
- `backend/`: Flask API amb validacio, calcul i render HTML a PDF.
- `backend/config/pricing.json`: configuracio de preus, impostos i literals de tarifa.
- `backend/config/pdf_templates/comparison/v1/`: contracte editable de `content.yaml`, `theme.yaml` i `assets.yaml`.

## Contracte minim d'entrada

```json
{
  "cups": "ES0210002100000000ZN0F",
  "titular": "Persona Persona",
  "billing_days": 30,
  "competitor_invoice_amount": 54.0,
  "energy_by_periods": {
    "P1": 34.41,
    "P2": 41.55,
    "P3": 88.63
  }
}
```

## Backend

```bash
cd backend
poetry install
poetry run python run.py
```

Endpoints:

- `POST /api/compare`: retorna resum JSON validat.
- `POST /api/reports/comparison.pdf`: retorna el PDF.
- `GET /api/health`: healthcheck.

## Frontend

```bash
cd frontend
npm install
npm run dev
```

Per defecte el frontend apunta a `http://localhost:5000/api`.

## Notes de disseny

- El calcul i el render del PDF estan separats.
- El PDF s'obte a partir d'una plantilla HTML/Jinja.
- El contracte editable del template viu a `backend/config/pdf_templates/comparison/v1/README.md`.
- El layout actual es un MVP inspirat en l'exemple aportat; falta iterar-lo per clonar fidelment la plantilla final.
