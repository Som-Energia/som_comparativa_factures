import { useRef, useState } from 'react'
import { buildEmailHtml, initialEmailDraft } from './email'

const fields = [
  ['retailer', 'Comercialitzadora actual'],
  ['renewable', 'Origen renovable certificat (%, actual)'],
  ['nonprofit', 'Sense ànim de lucre (actual)'],
  ['beneficiaries', 'Destinació dels beneficis (actual)'],
  ['ocu', 'Valoració OCU (actual)'],
  ['permanence', 'Permanència (actual)'],
]

const suggestionMessages = {
  suggested: 'Proposta automàtica calculada amb els imports de consum i potència. Podeu corregir-la manualment.',
  missing_data: 'Per proposar el motiu automàtic, completeu els imports de consum i potència actuals al formulari i torneu a calcular. També podeu seleccionar el motiu manualment.',
  other_costs: 'La diferència no s’explica prou pels imports de consum i potència; pot dependre d’altres conceptes. Reviseu-la abans de seleccionar un motiu manualment.',
  no_difference: 'No es proposa cap motiu perquè els imports són iguals o la diferència és de dos cèntims com a màxim.',
}

export default function EmailComposer({ report, retailer, locale, stale }) {
  const [draft, setDraft] = useState(() => initialEmailDraft(report, retailer, locale))
  const [status, setStatus] = useState('')
  const emailRef = useRef(null)
  const [theme] = useState(() => {
    const styles = getComputedStyle(document.documentElement)
    const token = (name) => styles.getPropertyValue(name).trim()
    return {
      text: token('--color-text'), surface: token('--color-tile'),
      tablePanel: token('--color-email-table'), tip: token('--color-email-tip'), divider: token('--color-divider'),
      link: token('--color-link'),
      button: token('--color-button'), buttonText: token('--color-button-text'),
    }
  })
  const html = buildEmailHtml(report, draft, theme)

  function update(field, value) {
    setDraft((current) => ({ ...current, [field]: value, ...(field === 'reason' ? { reasonManual: true } : {}) }))
    setStatus('')
  }

  function selectEmail() {
    const selection = window.getSelection()
    const range = document.createRange()
    range.selectNodeContents(emailRef.current)
    selection.removeAllRanges()
    selection.addRange(range)
    setStatus('Correu seleccionat. Premeu Ctrl+C (o Cmd+C) i enganxeu-lo al gestor de correu.')
  }

  async function copyEmail() {
    try {
      if (!navigator.clipboard?.write || !window.ClipboardItem) {
        selectEmail()
        return
      }
      await navigator.clipboard.write([new ClipboardItem({
        'text/html': new Blob([html], { type: 'text/html' }),
        'text/plain': new Blob([emailRef.current.innerText], { type: 'text/plain' }),
      })])
      setStatus('Correu copiat amb format. Ja el podeu enganxar al gestor de correu.')
    } catch {
      selectEmail()
    }
  }

  return (
    <section className="form-card email-composer" aria-labelledby="email-heading">
      <div className="section-heading-row">
        <h2 id="email-heading" tabIndex={-1}>Preparar correu</h2>
        <button type="button" disabled={stale} onClick={copyEmail}>Copiar correu amb format</button>
      </div>
      <p role="status">{status}</p>
      <p>Reviseu el redactat i completeu les dades que falten. Els imports corresponen al resultat calculat. Cada nou càlcul reinicia l’esborrany.</p>
      <p>Idioma del correu: <strong>{draft.language === 'es' ? 'Castellà' : 'Català'}</strong> (segons l’idioma seleccionat per al PDF). Canviar l’idioma també reinicia l’esborrany.</p>
      {stale && <p role="alert" className="field-error">Les dades del formulari han canviat. Premeu «Veure resum» per actualitzar els imports abans de copiar el correu.</p>}
      <div className="email-workspace">
        <div className="email-fields">
          <h3>Dades del correu</h3>
          <div className="two-column-grid">
            {fields.map(([field, label]) => (
              <label key={field}>{label}
                {field === 'nonprofit' ? (
                  <select value={draft.nonprofit} onChange={(event) => update('nonprofit', event.target.value)}>
                    <option value="❌ No">❌ No</option>
                    <option value="✅ Sí">✅ Sí</option>
                    <option value="❓">❓</option>
                  </select>
                ) : (
                  <input value={draft[field]} placeholder={field === 'retailer' ? 'Comercialitzadora actual' : 'No disponible'} onChange={(event) => update(field, event.target.value)} />
                )}
              </label>
            ))}
          </div>
          <p className="field-help">Podeu copiar aquests emojis i enganxar-los als camps: ✅ Sí · ❌ No · ❓ · 🏆 · 💡.</p>
          {report.comparison.savings !== 0 && <>
            <label>{report.comparison.savings > 0 ? 'Motiu de l’estalvi' : 'Motiu del sobrecost'}
              <select value={draft.reason} onChange={(event) => update('reason', event.target.value)}>
                <option value="">Sense especificar</option>
                <option value="energy">Consum {report.comparison.savings > 0 ? 'més car' : 'més econòmic'} a la comercialitzadora actual</option>
                <option value="power">Potència {report.comparison.savings > 0 ? 'més cara' : 'més econòmica'} a la comercialitzadora actual</option>
                <option value="both">Consum i potència {report.comparison.savings > 0 ? 'més cars' : 'més econòmics'} a la comercialitzadora actual</option>
              </select>
            </label>
            <p className="field-help">{draft.reasonManual ? 'Selecció manual. ' : ''}{suggestionMessages[report.reason_suggestion?.status || 'missing_data']}</p>
            {draft.reasonManual && <button type="button" className="tertiary" onClick={() => {
              setDraft((current) => ({ ...current, reason: report.reason_suggestion?.reason || '', reasonManual: false }))
              setStatus('')
            }}>Restablir proposta automàtica</button>}
          </>}
        </div>
        <div className="email-result">
          <h3>Correu preparat</h3>
          <div className="email-document" ref={emailRef} dangerouslySetInnerHTML={{ __html: html }} />
          <p className="field-help">Recordeu adjuntar el PDF de la simulació al correu.</p>
        </div>
      </div>
    </section>
  )
}
