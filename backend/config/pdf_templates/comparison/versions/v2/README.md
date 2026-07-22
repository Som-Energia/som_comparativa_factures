## Contracte editable del template `comparison/versions/v1`

Aquest directori defineix el contracte de configuracio per al PDF de comparativa.
La renderitzacio continua controlada pel backend; aquests YAML nomes declaren dades segures i limitades.

### Fitxers

- `content.yaml`: copy, labels i estructura textual.
- `theme.yaml`: tokens visuals limitats.
- `assets.yaml`: assets registrats i els seus metadades.

### Que es editable

- Textos plans.
- Llistes de bullets.
- Colors, marges i tipografia dins dels tokens permesos.
- Rutes d'assets relatives al directori d'assets del template.

### Que NO es editable

- Jinja, HTML, Markdown o CSS lliure.
- Claus fora del contracte.
- Nous blocs de layout fora de les seccions previstes.
- URLs remotes, `data:` URIs o rutes absolutes del sistema.

### Regles globals

- Tots els fitxers es codifiquen en UTF-8.
- Tots els textos son text pla.
- Interpolacio permesa nomes amb tokens `{path}` d'aquesta allowlist:
  - `{customer.titular}`
  - `{customer.cups}`
  - `{input.billing_days}`
  - `{pricing.tariff_name}`
  - `{pricing.effective_date}`
  - `{comparison.savings_label}`
- Cap camp pot contenir `<`, `>`, `{%`, `{{`, `}}` o `</`.
- Claus desconegudes s'han de rebutjar en validacio.
- Cada manifest ha de declarar el mateix numero que la seva versio de directori: `v1` usa `template_version: 1`, `v2` usa `template_version: 2`.

### Publicacio i rollback

La versio productiva es la indicada a `backend/config/pdf_templates/comparison/published.json`. Cal publicar-la amb `python manage_templates.py publish comparison vN`, que valida tot el bundle abans d'actualitzar el punter. Per fer rollback, s'executa `python manage_templates.py rollback comparison vN` amb una versio valida anterior.

### Contracte de `content.yaml`

| Ruta | Tipus | Obligatori | Limits / regles |
| --- | --- | --- | --- |
| `meta.template_id` | string | si | valor fix `comparison` |
| `meta.template_version` | integer | si | valor fix `1` |
| `meta.locale` | string | si | valor fix `ca` |
| `hero.title` | string | si | 1-80 caracters |
| `hero.intro` | list[string] | si | 1-2 items, cada item 1-320 caracters |
| `hero.customer_labels.titular` | string | si | 1-30 caracters |
| `hero.customer_labels.cups` | string | si | 1-30 caracters |
| `hero.badge_text` | string | si | 1-120 caracters, tokens permesos |
| `summary.title` | string | si | 1-80 caracters |
| `summary.columns.current_cost` | string | si | 1-40 caracters |
| `summary.columns.som_cost` | string | si | 1-40 caracters |
| `summary.columns.savings_positive` | string | si | 1-40 caracters |
| `summary.columns.savings_negative` | string | si | 1-40 caracters |
| `invoice_card.title` | string | si | 1-60 caracters |
| `invoice_card.labels.titular` | string | si | 1-30 caracters |
| `invoice_card.labels.cups` | string | si | 1-30 caracters |
| `invoice_card.labels.billing_days` | string | si | 1-30 caracters |
| `energy_table.title` | string | si | 1-60 caracters |
| `energy_table.columns.period` | string | si | 1-20 caracters |
| `energy_table.columns.kwh` | string | si | 1-20 caracters |
| `energy_table.columns.unit_price` | string | si | 1-20 caracters |
| `energy_table.columns.amount` | string | si | 1-20 caracters |
| `breakdown.title` | string | si | 1-60 caracters |
| `legal.disclaimer` | string | si | 1-240 caracters |
| `cta.title` | string | si | 1-80 caracters |
| `cta.body` | list[string] | si | 1-2 items, cada item 1-320 caracters |
| `cta.services_title` | string | si | 1-60 caracters |
| `cta.services` | list[string] | si | 1-6 items, cada item 1-120 caracters |
| `cta.primary_action` | object\|null | si | `null` o CTA primaria controlada |
| `cta.primary_action.label` | string | si si hi ha CTA | 1-40 caracters |
| `cta.primary_action.url` | string | si si hi ha CTA | URL absoluta `https://`, 1-200 caracters |

### Contracte de `theme.yaml`

| Ruta | Tipus | Obligatori | Limits / regles |
| --- | --- | --- | --- |
| `meta.template_id` | string | si | valor fix `comparison` |
| `meta.template_version` | integer | si | valor fix `1` |
| `page.size` | string | si | enum: `A4` |
| `page.margin_mm.top` | integer | si | 10-30 |
| `page.margin_mm.right` | integer | si | 10-30 |
| `page.margin_mm.bottom` | integer | si | 10-30 |
| `page.margin_mm.left` | integer | si | 10-30 |
| `colors.background` | string | si | hex `#RRGGBB` |
| `colors.ink` | string | si | hex `#RRGGBB` |
| `colors.muted` | string | si | hex `#RRGGBB` |
| `colors.brand` | string | si | hex `#RRGGBB` |
| `colors.accent` | string | si | hex `#RRGGBB` |
| `colors.soft` | string | si | hex `#RRGGBB` |
| `colors.line` | string | si | hex `#RRGGBB` |
| `colors.surface` | string | si | hex `#RRGGBB` |
| `colors.inverse_text` | string | si | hex `#RRGGBB` |
| `typography.font_family` | string | si | 1-80 caracters; llista CSS controlada pel backend |
| `typography.body_size_px` | integer | si | 10-14 |
| `typography.h1_size_px` | integer | si | 24-36 |
| `typography.h2_size_px` | integer | si | 20-30 |
| `typography.h3_size_px` | integer | si | 16-22 |
| `shape.card_radius_px` | integer | si | 0-24 |
| `shape.badge_radius_px` | integer | si | 8-999 |
| `spacing.card_padding_px` | integer | si | 8-24 |
| `spacing.table_cell_px` | integer | si | 6-16 |

### Contracte de `assets.yaml`

| Ruta | Tipus | Obligatori | Limits / regles |
| --- | --- | --- | --- |
| `meta.template_id` | string | si | valor fix `comparison` |
| `meta.template_version` | integer | si | valor fix `1` |
| `registry` | object | si | cataleg d'assets aprovats per id |
| `registry.<asset_id>.path` | string | si | ruta relativa, 1-120 caracters, extensio `.png`, `.jpg`, `.jpeg` o `.svg` |
| `registry.<asset_id>.alt` | string | si | 1-80 caracters per logos, 1-120 per il.lustracions |
| `registry.<asset_id>.max_width_px` | integer | si | 40-240 per logos, 80-320 per il.lustracions |
| `slots.logo` | string\|null | si | `null` o id d'un asset aprovat de `registry` |
| `slots.hero_illustration` | string\|null | si | `null` o id d'un asset aprovat de `registry` |

Regles addicionals d'assets:

- Les rutes son relatives a `backend/assets/pdf_templates/comparison/versions/v1/`.
- No es permeten fitxers de mes de 2 MB.
- No es permeten esquemes remots (`http://`, `https://`) ni `data:`.
- El template consumeix assets resolts per slot (`logo`, `hero_illustration`), no paths lliures.

### Mapeig directe amb el template actual

| Template actual | Contracte nou |
| --- | --- |
| Hero `h1` | `content.hero.title` |
| Hero `p` introductoris | `content.hero.intro[]` |
| Labels de titular i CUPS | `content.hero.customer_labels.*` |
| Badge de tarifa | `content.hero.badge_text` |
| Titol del resum | `content.summary.title` |
| Capcaleres de la taula resum | `content.summary.columns.*` |
| Titol i labels de la targeta de factura | `content.invoice_card.*` |
| Titol i capcaleres de la taula d'energia | `content.energy_table.*` |
| Titol del detall del calcul | `content.breakdown.title` |
| Disclaimer legal | `content.legal.disclaimer` |
| Bloc comercial final | `content.cta.*` |
| Colors CSS `:root` | `theme.colors.*` |
| Marges `@page` | `theme.page.margin_mm.*` |
| Tipografia base i headings | `theme.typography.*` |
| Ratis de badge i card | `theme.shape.*` |
| Padding principal de taules i cards | `theme.spacing.*` |

### Superficie bloquejada al backend

Aquests valors continuen vivint al motor de calcul i no s'editen des del YAML:

- `report.customer.*`
- `report.input.*`
- `report.pricing.*`
- `report.comparison.*`
- `report.breakdown.*`

El renderer nomes pot injectar-los en punts predefinits del layout.
