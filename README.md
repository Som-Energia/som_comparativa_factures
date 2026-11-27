# webservice_factura

MVP per generar una comparativa de factura amb Som Energia a partir d'un formulari web i exportar-la a PDF.

## Arquitectura

- `frontend/`: React + Vite, formulari d'una sola pantalla i resum previ.
- `backend/`: Flask API amb validacio, calcul i render HTML a PDF.
- `backend/config/pricing.json`: font de veritat dels preus de tarifa, actualitzada diariament des de l'ERP.
- `backend/config/pdf_templates/comparison/published.json`: punter de la versio activa del template.
- `backend/config/pdf_templates/comparison/versions/v1/`: contracte editable de `content.yaml`, `theme.yaml` i `assets.yaml`.

## Estils del frontend

Els estils segueixen la imatge de [somenergia.coop](https://www.somenergia.coop/). Tota la configuració visual és a `frontend/src/tokens.css`, en dos nivells:

- `--som-*`: valors oficials de marca (colors, tipografia i radis). Només canvien si canvia la marca.
- `--color-*`, `--font-*`, `--radius-*`, `--space-*`...: paper de cada valor a l'aplicació. Són els que consumeix `frontend/src/styles.css`, que no conté colors escrits directament.

Per exemple, per fer que el botó principal sigui lila:

```css
--color-button: var(--som-lila);
--color-button-hover: var(--som-background-three);
```

La tipografia Outfit s'empaqueta amb l'aplicació (`@fontsource-variable/outfit`) i el logo i el favicon són a `frontend/public/`. Els PDF tenen el seu propi tema a `backend/config/pdf_templates/`.

## Preparar el correu de la comparativa

1. Carregueu una factura o introduïu les dades i premeu **Veure resum**.
2. A **Preparar correu**, reviseu la comercialitzadora extreta i completeu les característiques que falten. Els camps buits apareixen com a «No disponible».
3. Reviseu el correu preparat al costat dels camps; el redactat i els enllaços són els del model predefinit.
4. Premeu **Copiar correu amb format** a la capçalera de l’apartat, enganxeu-lo al gestor de correu i adjunteu-hi el PDF descarregat. Si el navegador no permet copiar amb format automàticament, el contingut queda seleccionat per copiar-lo amb Ctrl+C o Cmd+C.

El correu es prepara en català o castellà segons l’idioma del PDF, amb plantilles diferents per a estalvi i sobrecost i un redactat neutre per a la igualtat. Cada nou càlcul o canvi d’idioma reinicia l’esborrany; si canvieu les dades del formulari, cal recalcular abans de copiar. L’esborrany és temporal i es perd en sortir de la pantalla. La taula reutilitza els tokens visuals de l’aplicació i es copia amb estils inline per als clients de correu.

### Proposta automàtica del motiu

Els camps **Import del consum — companyia actual** i **Import de la potència — companyia actual** s’omplen des del PDF quan l’extracció és prou clara. Són opcionals, es poden corregir al formulari i no alteren el total de la simulació. Han de correspondre al mateix període, abans d’impostos, amb els descomptes aplicats i sense compensació d’excedents ni serveis addicionals o d’ajust facturats separadament.

En prémer **Veure resum**, es preselecciona consum, potència o tots dos segons la comparació amb els imports de Som Energia. Podeu canviar-ho, deixar-ho **Sense especificar** o prémer **Restablir proposta automàtica**.

- Calen els dos imports; l’absència d’un import no es tracta com un zero.
- Les diferències de fins a 0,02 € es tracten com a arrodoniment per a aquesta proposta.
- Per atribuir el motiu principal, la diferència neta de consum i potència abans d’impostos ha de tenir el mateix sentit que el resultat i explicar almenys la meitat de la diferència total. És un criteri conservador, sense assumir les bases fiscals de l’altra companyia.
- Quotes fixes sense desglossament comercial, imports contradictoris i descomptes no atribuïbles queden pendents de revisió. Els peatges i càrrecs informatius no substitueixen els imports comercials.

En aquesta entrega, els nous imports de **Holaluz** queden pendents perquè la seva extracció s’incorporarà amb la branca `IMP_extractor_hl_en`. Es poden completar manualment per obtenir la proposta del motiu. El suport de Holaluz que ja existia es conserva. **Canàries queda fora de l’abast** fins que el formulari estigui adaptat a la seva fiscalitat.

La funció substitueix l’obertura del preview HTML de la comparativa. El preview en viu de l’editor de plantilles PDF es manté.

### Compatibilitat amb FreeScout

El correu es genera en Arial de 16 px amb interlineat de 24 px. Les cel·les dels conceptes utilitzen `td` amb `align="left"` perquè el filtre de FreeScout no les converteixi en capçaleres centrades sense alineació.

El [filtre estàndard de FreeScout](https://github.com/freescout-help-desk/freescout/blob/dist/config/purifier.php) elimina `line-height`. En un missatge rebut de prova això feia que el text de 16 px heretés els 19 px d’interlineat del contenidor exterior. Els espais entre paràgrafs i després de la taula sí que es conservaven.

Per conservar els 24 px entre línies, qui administra **FreeScout** ha d’afegir `line-height` a la llista existent `settings.default.CSS.AllowedProperties` del seu `config/purifier.php`, mantenint la resta de propietats, i executar `php artisan freescout:clear-cache` al directori de FreeScout. Aquest ajust pertany a la instal·lació de FreeScout i s’ha de conservar en les seves actualitzacions; no s’aplica des d’aquest repositori.

Després cal copiar un correu nou, enganxar-lo en una resposta buida i enviar-lo a Gmail. Al missatge rebut s’ha de comprovar que les cel·les dels conceptes siguin `td` alineades a l’esquerra i que els paràgrafs conservin `line-height:24px`. El shorthand `font:16px/24px Arial` no resol el bloqueig: Chrome el descompon en propietats separades en enganxar i el filtre torna a eliminar l’interlineat.

## Contracte minim d'entrada de comparativa

```json
{
  "cups": "ES0210002100000000RN0F",
  "titular": "Persona Persona",
  "billing_days": 30,
  "competitor_invoice_amount": 54.0,
  "energy_by_periods": {
    "P1": 34.41,
    "P2": 41.55,
    "P3": 88.63
  },
  "contracted_power_kw_by_periods": {
    "P1": 2.3,
    "P2": 2.3
  },
  "self_consumption_surplus_kwh": 12.5,
  "meter_rental_eur": 0.81,
  "vat_rate_percent": 21,
  "electric_tax_rate_percent": 5.11
}
```

## Backend

El contracte de comparativa també admet `competitor_energy_eur` i `competitor_power_eur`, imports opcionals no negatius en EUR. Es poden ometre o enviar com a `null` o cadena buida. La resposta de `/api/compare` els conserva a `input` i afegeix `reason_suggestion`, amb `reason` (`energy`, `power`, `both` o cadena buida), `status` (`suggested`, `missing_data`, `other_costs`, `no_difference`) i les diferències per concepte, positives quan Som Energia és més econòmica.

```bash
cd backend
poetry install
poetry run python run.py
```

Endpoints:

- `POST /api/compare`: retorna resum JSON validat.
- `POST /api/invoices/extract-for-comparison`: rep un `multipart/form-data` amb el camp `pdf` i retorna les dades extretes, junt amb el payload preparat per a la comparativa. Disponible per a la interfície interna.
- `POST /api/invoices/extract`: API externa protegida. Rep el mateix camp `pdf`, requereix `Authorization: Bearer <INVOICE_EXTRACTOR_API_TOKEN>` i retorna les dades extretes amb les claus del contracte de comparativa.
- `POST /api/reports/comparison.pdf`: retorna el PDF.
  - Admet `locale: "ca"` (valor per defecte) o `locale: "es"` per escollir l'idioma del document.
- `GET /api/pricing`: retorna la configuració de preus activa que s'aplica als càlculs, incloent la data efectiva i la darrera sincronització ERP.
- `GET /api/health`: healthcheck.

Exemple de crida externa:

```bash
curl -X POST "https://comparativa.example.org/api/invoices/extract" \
  -H "Authorization: Bearer $INVOICE_EXTRACTOR_API_TOKEN" \
  -F "pdf=@/ruta/factura.pdf"
```

La resposta inclou les claus del contracte d'entrada de comparativa i conserva dades addicionals que poden ser útils per revisar l'extracció:

```json
{
  "retailer": "Iberdrola",
  "cups": "ES0210002100000000RN0F",
  "titular": "Persona Persona",
  "billing_days": 30,
  "competitor_invoice_amount": 54.0,
  "competitor_energy_eur": 30.0,
  "competitor_power_eur": 10.0,
  "energy_by_periods": {"P1": 34.41, "P2": 41.55, "P3": 88.63},
  "contracted_power_kw_by_periods": {"P1": 2.3, "P2": 2.3, "P3": 2.3},
  "self_consumption_surplus_kwh": null,
  "meter_rental_eur": 0.81,
  "vat_amount": 11.34,
  "vat_rate_percent": 21.0,
  "igic_lines": [
    {"name": "reducido", "percent": 0.0, "taxable_base_eur": 1.09, "amount_eur": 0.0},
    {"name": "normal", "percent": 7.0, "taxable_base_eur": 1.52, "amount_eur": 0.11}
  ],
  "igic_total_eur": 0.11,
  "electricity_tax": 1.35,
  "electric_tax_rate_percent": 5.11,
  "data_quality": {"status": "verified", "issues": []}
}
```

`POST /api/invoices/extract-for-comparison` retorna aquest objecte dins d'`extraction` i afegeix `comparison_input`, preparat per enviar directament a `POST /api/compare`. Aquest últim conserva únicament P1 i P2 de la potència contractada, perquè són els períodes que admet el càlcul actual.

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
| `BACKEND_IMAGE` | `harbor.somenergia.coop/comparativa/comparativa-backend:v0.1.0` | Imatge immutable del backend publicada a Harbor. |
| `FRONTEND_IMAGE` | `harbor.somenergia.coop/comparativa/comparativa-frontend:v0.1.0` | Imatge immutable del frontend publicada a Harbor. |
| `BACKEND_NODE_HOSTNAME` | `moll2` | Node Swarm que conté `/mnt/data/docker/comparativa`. El backend queda fixat a aquest node. |
| `INVOICE_EXTRACTOR_API_TOKEN` | valor aleatori secret | Token requerit per a l'endpoint extern d'extracció de factures. |

### Publicar imatges a Harbor

Inicieu sessio al registre i publiqueu les dues imatges amb un tag de versio immutable. El slug del projecte i els noms de repositori s'han de copiar de Harbor; l'script rep les referencies completes per no assumir-ne cap convencio.
L'script també actualitza el tag mutable `latest`; el stack de Portainer pot usar-lo per a desplegaments automàtics, mentre que els tags immutables de versió serveixen per identificar i recuperar desplegaments anteriors.

La versió de l'aplicació viu exclusivament a `VERSION`: el frontend la mostra, les imatges de frontend i backend la fan servir com a tag i determina el tag Git anotat, com `v0.3.0`. Quan la publicació d'ambdues imatges té èxit, l'script crea i puja aquest tag. Per evitar etiquetar codi que no correspon a les imatges, exigeix que l'arbre de treball estiga net i que el tag no existisca localment ni a `origin`. Per redeplegar automàticament un stack de Portainer Community Edition després de publicar les imatges, definiu un access token localment. No el deseu al repositori:

```bash
export PORTAINER_URL="https://portainer.example.org"
export PORTAINER_API_TOKEN="..."
export PORTAINER_STACK_NAME="som_comparativa_factures"
```

Amb aquestes variables, `publish-images.sh` conserva el `compose.yml` i les variables actuals del stack, força un pull de `latest` i en demana el redeploy mitjançant l'API de Portainer. Si el certificat de Portainer és autosignat, afegiu explícitament `PORTAINER_INSECURE_TLS=1`.

```bash
docker login harbor.somenergia.coop
./scripts/publish-images.sh \
  harbor.somenergia.coop/comparativa/comparativa-backend \
  harbor.somenergia.coop/comparativa/comparativa-frontend
```

Enganxeu `compose.yml` com a Stack a Portainer, afegiu les variables i desplegueu-lo. El fitxer esta preparat per Docker Swarm: les etiquetes de Traefik viuen al servei i el backend queda fixat al node indicat per `BACKEND_NODE_HOSTNAME`. Les dades persistents es desen al host sota `/mnt/data/docker/comparativa/`: `config/` conserva les plantilles, la versio publicada i `pricing.json`; `assets/` conserva els seus recursos. En el primer arrencada, el backend inicialitza directoris buits amb la configuracio inclosa a la imatge. Despres, `pricing.json` no se sobreescriu durant reinicis ni desplegaments.

### Sincronitzacio de preus ERP

El servei intern `pricing-sync` consulta diàriament a les 00:10, en hora `Europe/Madrid`, la tarifa `2.0TD` de l'ERP per a la data situada **38 dies en el futur**. Aquest marge afegeix una setmana als 31 dies per incorporar les tarifes publicades el dimecres o dijous anterior. La tarifa futura ja publicada s'aplica immediatament a la comparativa; `effective_date` n'indica la data d'entrada en vigor. Si la consulta falla o retorna dades invàlides, es conserva l'últim `pricing.json` vàlid.

Per exemple, el 26/11/2026 es consulta el 03/01/2027 i es pot incorporar la tarifa que entra en vigor l'01/01/2027. Si es publica després de les 00:10, es detectarà en la següent sincronització diària o en reiniciar el servei.

Els logs de `pricing-sync` a Portainer mostren l'arrencada i l'horari, la data consultada, l'inici de cada fase (tarifa, serveis d'ajust i desament), la tarifa i les dates rebudes, la confirmació de desament amb la durada i la propera execució amb zona horària. Els errors inclouen el traceback; l'última fase registrada permet localitzar la fallada. Els missatges de nivell `INFO` estan habilitats i no es registren les credencials ni les respostes completes de l'ERP. El camp `synced_at` de `GET /api/pricing` permet comprovar l'última sincronització desada.

La mateixa sincronització obté els serveis d'ajust amb `giscedata.polissa.tarifa.get_last_month_average_prices_www("2.0TD", "ssaa")`. Els preus P1, P2 i P3 es desen a `adjustment_service_prices_eur_per_kwh`, en €/kWh sense impostos, i s'apliquen al consum de cada període. El backend arrodoneix la suma a cèntims i inclou l'import a la base de l'impost elèctric. Aquest concepte ja no es demana al formulari; els valors enviats pel client no substitueixen els preus configurats.

`adjustment_service_price_date` conserva la data del registre retornat per l'ERP, independent de `effective_date`. El helper selecciona l'últim registre disponible, que no és necessàriament del mes anterior. La pantalla **Preus** mostra els imports i aquesta data. Si falla qualsevol consulta o validació, no s'actualitza cap dels preus.

En desplegar aquesta versió, l'ERP ha de tenir disponible el helper de la [PR #1522](https://github.com/Som-Energia/openerp_som_addons/pull/1522). El servei sincronitza també en arrencar. Fins a la primera sincronització correcta, el valor antic `adjustment_service_eur_per_kwh` es llegeix com un mateix preu per als tres períodes, sense atribuir-li cap data de l'ERP; la pantalla **Preus** indica que està pendent de sincronitzar. La primera actualització correcta desa el nou format i elimina el camp antic. La configuració inicial inclosa a la imatge també conserva aquests imports previs amb data nul·la.

El servei requereix aquestes variables addicionals, que nomes s'injecten a `pricing-sync`:

| Variable | Exemple | Descripcio |
| --- | --- | --- |
| `OOOP_USER` | `comparativa` | Usuari de lectura de l'ERP. |
| `OOOP_PWD` | valor secret | Contrasenya de l'usuari ERP. |
| `OOOP_DBNAME` | `somenergia` | Base de dades OpenERP. |
| `OOOP_URI` | `https://erp.example.org` | URL base de l'ERP. |
| `OOOP_PORT` | `443` | Port XML-RPC de l'ERP. |
| `TARIFF_MUNICIPI_ID` | `28` | Municipi de referencia per als preus peninsulars. Valor per defecte: `28`. |

No deseu les credencials ERP al repositori ni als logs. La sincronització actualitza energia, potència, compensació d'excedents, bo social i serveis d'ajust. El lloguer del comptador i els impostos continuen venint del formulari o de l'extracció de factura.

L'aplicacio no incorpora autenticacio: l'accés ha d'estar restringit per la VPN de l'organitzacio. Qualsevol usuari de la VPN pot gestionar les plantilles publicades.
