import assert from 'node:assert/strict'
import { test } from 'node:test'
import { buildEmailHtml, initialEmailDraft } from './email.js'

const report = (savings) => ({
  comparison: { competitor_total: 54, som_total: 54 - savings, savings },
  input: { billing_days: 28 },
})
const theme = {
  text: '#0b2e34', surface: '#fff', tablePanel: '#cdff80', tip: '#ff632b', divider: '#ced5d0', link: '#0c4c27',
  button: '#cdff80', buttonText: '#0b2e34',
}
const htmlFor = (savings, overrides = {}) => {
  const data = report(savings)
  return buildEmailHtml(data, { ...initialEmailDraft(data, 'Companyia'), ...overrides }, theme)
}

test('el resultat i la diferència distingeixen estalvi, sobrecost i igualtat', () => {
  const saving = htmlFor(10)
  assert.match(saving, /El resultat és <strong style="background-color:#cdff80;color:#0b2e34;">favorable<\/strong>/)
  assert.match(saving, /Diferència<\/td><td colspan="2"[^>]*>10,00\s€<\/td>/)
  assert.match(saving, /54,00\s€/)
  assert.match(saving, /44,00\s€/)
  assert.match(saving, /10,00\s€/)
  assert.match(saving, /període facturat \(28 dies\)/)
  const higher = htmlFor(-10)
  assert.match(higher, /és superior/)
  assert.match(higher, /Diferència<\/td><td colspan="2"[^>]*>10,00\s€<\/td>/)
  assert.match(higher, /64,00\s€/)
  assert.match(higher, /El resultat és <strong>desfavorable<\/strong>/)
  assert.doesNotMatch(higher, /<strong[^>]*>favorable<\/strong>|-10,00/)
  assert.match(htmlFor(0), /és igual/)
  assert.match(htmlFor(0), /0,00\s€/)
})

test('les dades absents no inventen característiques de la comercialitzadora', () => {
  const html = htmlFor(10, { retailer: '', renewable: '  ' })
  assert.match(html, /Comercialitzadora actual/)
  assert.equal((html.match(/No disponible/g) || []).length, 3)
  assert.match(html, /Accionistes/)
  assert.match(html, /❌ No/)
  assert.match(htmlFor(10, { renewable: '42%', permanence: '12 mesos' }), /42%/)
  assert.match(htmlFor(10, { permanence: '12 mesos' }), /12 mesos/)
})

test('el motiu només apareix si se selecciona i hi ha estalvi', () => {
  assert.doesNotMatch(htmlFor(10), /El principal motiu/)
  for (const [reason, text] of [['energy', 'del consum'], ['power', 'de la potència'], ['both', 'del consum i de la potència']]) {
    assert.ok(htmlFor(10, { reason }).includes(`preus ${text}`))
    assert.doesNotMatch(htmlFor(-10, { reason }), /El principal motiu/)
    assert.doesNotMatch(htmlFor(0, { reason }), /El principal motiu/)
  }
})

test('el motiu proposat es preselecciona i es pot substituir o deixar buit manualment', () => {
  for (const savings of [10, -10]) {
    const data = { ...report(savings), reason_suggestion: { reason: 'energy', status: 'suggested' } }
    const draft = initialEmailDraft(data, '')
    assert.equal(draft.reason, 'energy')
    assert.equal(draft.reasonManual, false)
    const html = buildEmailHtml(data, draft, theme)
    assert.match(html, /del consum/)
    assert.doesNotMatch(html, /de la potència que|cost de la potència/)
    const manual = buildEmailHtml(data, { ...draft, reason: 'power' }, theme)
    assert.match(manual, /de la potència/)
    const unspecified = buildEmailHtml(data, { ...draft, reason: '' }, theme)
    assert.doesNotMatch(unspecified, /El principal motiu|menor cost/)
  }
})

test('el motiu desfavorable és manual i distingeix consum, potència i tots dos en ambdós idiomes', () => {
  for (const language of ['ca', 'es']) {
    const data = report(-10)
    const draft = initialEmailDraft(data, '', language)
    const render = (reason) => buildEmailHtml(data, { ...draft, reason }, theme)
    assert.doesNotMatch(render(''), /menor cost/)
    const parts = language === 'ca'
      ? ['del consum', 'de la potència', 'del consum i de la potència']
      : ['del consumo', 'de la potencia', 'del consumo y de la potencia']
    for (const [index, reason] of ['energy', 'power', 'both'].entries()) {
      const html = render(reason)
      assert.ok(html.includes(`${language === 'ca' ? 'menor cost' : 'menor coste'} ${parts[index]}`))
      assert.match(html, /oferta temporal/)
      assert.doesNotMatch(html, /més elevats|más elevados/)
    }
  }
})

test('les plantilles desfavorables inclouen tendència, recomanacions i OCU del document', () => {
  for (const language of ['ca', 'es']) {
    const data = report(-10)
    const html = buildEmailHtml(data, initialEmailDraft(data, '', language), theme)
    assert.match(html, /servicios\/tendencia-/)
    assert.match(html, /satisfaccion-proveedores-energia/)
    assert.match(html, language === 'ca' ? /més enllà del preu/ : /más allá del precio/)
    assert.doesNotMatch(html, /100 €|diferències entre les dues tarifes|diferencias entre ambas tarifas/)
    const favorable = buildEmailHtml(report(10), initialEmailDraft(report(10), '', language), theme)
    assert.doesNotMatch(favorable, /servicios\/tendencia-|satisfaccion-proveedores-energia/)
  }
})

test('el castellà tradueix taula, resultat, motiu, enllaços i elements destacats', () => {
  for (const savings of [10, -10, 0]) {
    const data = report(savings)
    data.input.locale = 'es'
    const draft = { ...initialEmailDraft(data, ''), reason: 'both' }
    const html = buildEmailHtml(data, draft, theme)
    assert.match(html, /lang="es"/)
    for (const text of ['Comercializadora actual', 'Coste del período facturado (28 días)', 'Diferencia', 'Sin ánimo de lucro', 'Accionistas', 'Valoración OCU', 'Permanencia', 'Atentamente,']) {
      assert.ok(html.includes(text), text)
    }
    assert.match(html, /border-radius:999px;[^>]*>¿Te unes a Som Energia\?<\/a>/)
    assert.match(html, /<span style="color:#ff632b;">Consejo<\/span>/)
    assert.doesNotMatch(html, /somenergia\.coop\/ca\/|ca\.support|El resultat|Accionistes|Consell/)
    if (savings > 0) {
      assert.match(html, /El resultado es <strong[^>]+>favorable<\/strong>/)
      assert.match(html, /precios del consumo y de la potencia.*más elevados/)
      assert.match(html, /article\/1332-/)
      assert.match(html, /article\/144-/)
    } else if (savings < 0) {
      assert.match(html, /El resultado es <strong>desfavorable<\/strong>/)
    } else {
      assert.match(html, /es igual/)
      assert.doesNotMatch(html, /El principal motivo|menor coste/)
    }
  }
})

test('el redactat editable conserva enllaços HTTPS i escapa qualsevol HTML introduït', () => {
  const html = htmlFor(10, {
    retailer: '<img src=x onerror=alert(1)>',
    intro: '<script>alert(1)</script>',
    body: '[Serveis](https://example.org/?a=1&b=2)\n\n[No segur](javascript:alert(1))',
  })
  assert.doesNotMatch(html, /<script|<img|href="javascript:/)
  assert.match(html, /&lt;script&gt;/)
  assert.match(html, /&lt;img/)
  assert.match(html, /<a href="https:\/\/example.org\/\?a=1&amp;b=2" style="[^"]*color:#0c4c27;text-decoration:underline;">Serveis<\/a>/)
})

test('el correu inclou els enllaços del model, els estils inline i el nou redactat', () => {
  const html = htmlFor(10, { intro: 'Bon dia,\n\n💡 Text personalitzat', body: 'Comiat personalitzat', nonprofit: '✅ Sí' })
  assert.match(html, /Text personalitzat/)
  assert.match(html, /Comiat personalitzat/)
  assert.match(html, /💡 Text personalitzat/)
  assert.match(html, /✅ Sí/)
  assert.doesNotMatch(html, /Gràcies per aportar/)
  assert.match(html, /<thead><tr style="background-color:#cdff80;">/)
  assert.match(html, /<tr style="font-weight:bold;">/)
  assert.match(html, /role="rowheader"/)
  assert.equal((htmlFor(10).match(/<a href="https:/g) || []).length, 6)
  assert.match(htmlFor(10), /<p style="[^"]*text-align:center;margin:24px 0;"><a[^>]+background-color:#cdff80;[^>]+border-radius:999px;[^>]+text-decoration:none;[^>]*>Vols unir-te a Som Energia\?<\/a><\/p>/)
  assert.match(htmlFor(10), /font-size:16px;[^>]*>Vols unir-te a Som Energia\?/)
  assert.match(htmlFor(10), /<p style="[^"]*">💡 <span style="color:#ff632b;">Consell<\/span>: Per omplir/)
  assert.doesNotMatch(htmlFor(10), /Outfit|\d(?:\.\d+)?rem/)
  for (const tag of htmlFor(10).matchAll(/<(?:p|a|th|td)\b[^>]*>/g)) {
    assert.ok(tag[0].includes('font-family:Arial, Helvetica, sans-serif;'), tag[0])
    assert.ok(tag[0].includes('font-size:16px;'), tag[0])
  }
  for (const tag of html.matchAll(/<td\b[^>]*(?:role="rowheader"|width="35%")[^>]*>/g)) {
    assert.ok(tag[0].includes('align="left"'), tag[0])
    assert.ok(tag[0].includes('text-align:left;'), tag[0])
  }
  assert.match(htmlFor(10), /border-radius:999px;padding:8px 18px;/)
})

test('les cel·les de conceptes eviten el centrat per defecte després del filtre de FreeScout', () => {
  for (const language of ['ca', 'es']) {
    const data = report(10)
    const html = buildEmailHtml(data, initialEmailDraft(data, 'Companyia', language), theme)
    // Les cel·les normals continuen a l’esquerra encara que es perdi l’alineació.
    assert.doesNotMatch(html, /<th\b|!important/)
    assert.equal((html.match(/role="rowheader" align="left"/g) || []).length, 7)
    assert.match(html, /role="columnheader" align="left" width="35%"/)
    assert.match(html, /colspan="2" align="center"[^>]*font-weight:bold;/)
  }
})
