# webservice_factura

MVP per generar una comparativa de factura amb Som Energia a partir d'un formulari web i exportar-la a PDF.

## Arquitectura

- `frontend/`: React + Vite, formulari d'una sola pantalla i resum previ.
- `backend/`: Flask API amb validacio, calcul i render HTML a PDF.
- `backend/config/pricing.json`: configuracio de preus, impostos i literals de tarifa.
- `backend/config/pdf_templates/comparison/published.json`: punter de la versio activa del template.
- `backend/config/pdf_templates/comparison/versions/v1/`: contracte editable de `content.yaml`, `theme.yaml` i `assets.yaml`.

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
- `GET /api/reports/comparison.preview`: retorna HTML renderitzat de preview amb dades de mostra i una versio publicada o seleccionada.
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
- La versio publicada del template es resol des de `backend/config/pdf_templates/comparison/published.json`.
- El contracte editable del template viu a `backend/config/pdf_templates/comparison/versions/v1/README.md`.

## Publicacio de plantilles

La plantilla productiva es la versio indicada per `published.json`. Per publicar una versio, el backend valida tot el bundle abans d'actualitzar aquest punter de manera atomica:

```bash
cd backend
poetry run python manage_templates.py publish comparison v1
```

El rollback es fa publicant una versio anterior valida:

```bash
poetry run python manage_templates.py rollback comparison v1
```
- El layout actual es un MVP inspirat en l'exemple aportat; falta iterar-lo per clonar fidelment la plantilla final.

## Desplegament a Portainer

El fitxer `compose.yml` defineix un stack productiu amb dos contenidors:

- `frontend`: Nginx serveix el build de React i reenvia `/api` al backend dins de la xarxa Docker.
- `backend`: Gunicorn executa Flask i genera els PDF. No publica cap port al host ni a Traefik.

El frontend es publica amb Traefik. Abans de crear el stack a Portainer, definiu aquestes variables amb els noms existents a la instancia `moll`:

| Variable | Exemple | Descripcio |
| --- | --- | --- |
| `APP_HOSTNAME` | `comparativa.moll.somenergia.coop` | Hostname public del servei. Cal crear-ne el registre DNS cap a Traefik. |
| `TRAEFIK_NETWORK` | `traefik-public` | Xarxa Docker externa a la qual esta connectat Traefik. |
| `TRAEFIK_ENTRYPOINT` | `websecure` | Entrypoint HTTPS configurat a Traefik. |
| `TRAEFIK_CERT_RESOLVER` | `letsencrypt` | Certificate resolver configurat a Traefik. |
| `BACKEND_IMAGE` | `harbor.somenergia.coop/comparativa/comparativa-backend:v0.1.0` | Imatge immutable del backend publicada a Harbor. |
| `FRONTEND_IMAGE` | `harbor.somenergia.coop/comparativa/comparativa-frontend:v0.1.0` | Imatge immutable del frontend publicada a Harbor. |

### Publicar imatges a Harbor

Inicieu sessio al registre i publiqueu les dues imatges amb un tag de versio immutable. El slug del projecte i els noms de repositori s'han de copiar de Harbor; l'script rep les referencies completes per no assumir-ne cap convencio.

```bash
docker login harbor.somenergia.coop
./scripts/publish-images.sh \
  harbor.somenergia.coop/comparativa/comparativa-backend:v0.1.0 \
  harbor.somenergia.coop/comparativa/comparativa-frontend:v0.1.0
```

Enganxeu `compose.yml` com a Stack a Portainer, afegiu les sis variables i desplegueu-lo. Les dades persistents es desen al host sota `/mnt/data/docker/comparativa/`: `config/` conserva les plantilles i la versio publicada, i `assets/` conserva els seus recursos. En el primer arrencada, el backend inicialitza directoris buits amb la configuracio inclosa a la imatge.

L'aplicacio no incorpora autenticacio: l'accés ha d'estar restringit per la VPN de l'organitzacio. Qualsevol usuari de la VPN pot gestionar les plantilles publicades.
