import { useEffect, useState } from 'react'

const apiBaseUrl = 'http://localhost:5000/api'

const initialForm = {
  cups: '',
  titular: '',
  billing_days: '',
  competitor_invoice_amount: '',
  template_version: '',
  energy_by_periods: {
    P1: '',
    P2: '',
    P3: '',
  },
}

function App() {
  const [form, setForm] = useState(initialForm)
  const [errors, setErrors] = useState({})
  const [preview, setPreview] = useState(null)
  const [loadingPreview, setLoadingPreview] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [publishedVersion, setPublishedVersion] = useState(null)
  const [loadingPublication, setLoadingPublication] = useState(true)
  const [publishingAction, setPublishingAction] = useState('')
  const [publicationMessage, setPublicationMessage] = useState('')

  useEffect(() => {
    let cancelled = false

    async function loadPublicationStatus() {
      setLoadingPublication(true)

      const response = await fetch(`${apiBaseUrl}/templates/comparison/publication`)
      const data = await response.json()

      if (cancelled) {
        return
      }

      setLoadingPublication(false)
      if (!response.ok) {
        setErrors((current) => ({ ...current, ...(data.errors || {}) }))
        return
      }

      setPublishedVersion(data.published_version)
    }

    loadPublicationStatus()

    return () => {
      cancelled = true
    }
  }, [])

  function updateField(name, value) {
    setForm((current) => ({ ...current, [name]: value }))
  }

  function updatePeriod(period, value) {
    setForm((current) => ({
      ...current,
      energy_by_periods: {
        ...current.energy_by_periods,
        [period]: value,
      },
    }))
  }

  function buildPayload() {
    const payload = {
      cups: form.cups,
      titular: form.titular,
      billing_days: Number(form.billing_days),
      competitor_invoice_amount: Number(form.competitor_invoice_amount),
      energy_by_periods: {
        P1: Number(form.energy_by_periods.P1),
        P2: Number(form.energy_by_periods.P2),
        P3: Number(form.energy_by_periods.P3),
      },
    }

    const templateVersion = form.template_version.trim()
    if (templateVersion) {
      payload.template_version = templateVersion
    }

    return payload
  }

  async function handlePreview(event) {
    event.preventDefault()
    setLoadingPreview(true)
    setErrors({})

    const response = await fetch(`${apiBaseUrl}/compare`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(buildPayload()),
    })

    const data = await response.json()
    setLoadingPreview(false)

    if (!response.ok) {
      setPreview(null)
      setErrors(data.errors || {})
      return
    }

    setPreview(data)
  }

  async function handleDownload() {
    setDownloading(true)
    setErrors({})

    const response = await fetch(`${apiBaseUrl}/reports/comparison.pdf`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(buildPayload()),
    })

    setDownloading(false)

    if (!response.ok) {
      const data = await response.json()
      setErrors(data.errors || {})
      return
    }

    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = 'comparison-report.pdf'
    link.click()
    URL.revokeObjectURL(url)
  }

  async function handleTemplatePublication(action) {
    const templateVersion = form.template_version.trim()
    if (!templateVersion) {
      setErrors((current) => ({ ...current, template_version: 'Cal indicar una versio de plantilla.' }))
      return
    }

    setPublishingAction(action)
    setPublicationMessage('')
    setErrors((current) => ({ ...current, template_version: undefined, publication: undefined }))

    const response = await fetch(`${apiBaseUrl}/templates/comparison/${action}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ template_version: templateVersion }),
    })

    const data = await response.json()
    setPublishingAction('')

    if (!response.ok) {
      setErrors((current) => ({ ...current, ...(data.errors || {}) }))
      return
    }

    setErrors((current) => ({ ...current, template_version: undefined, publication: undefined }))
    setPublishedVersion(data.published_version)
    setPublicationMessage(data.message)
  }

  function handleOpenHtmlPreview() {
    const templateVersion = form.template_version.trim()
    const previewUrl = new URL(`${apiBaseUrl}/reports/comparison.preview`)

    if (templateVersion) {
      previewUrl.searchParams.set('template_version', templateVersion)
    }

    window.open(previewUrl.toString(), '_blank', 'noopener,noreferrer')
  }

  return (
    <main className="page-shell">
      <section className="hero-card">
        <p className="eyebrow">MVP comparativa</p>
        <h1>Simulacio de factura Som Energia</h1>
        <p className="hero-copy">
          Formulari d'una sola pantalla per calcular la comparativa i descarregar l'informe en PDF.
        </p>
      </section>

      <div className="layout">
        <form className="form-card" onSubmit={handlePreview}>
          <section className="form-section">
            <h2>Titular i contracte</h2>
            <label>
              Titular
              <input value={form.titular} onChange={(event) => updateField('titular', event.target.value)} />
              <FieldError error={errors.titular} />
            </label>
            <label>
              CUPS
              <input value={form.cups} onChange={(event) => updateField('cups', event.target.value)} />
              <FieldError error={errors.cups} />
            </label>
          </section>

          <section className="form-section">
            <h2>Dades de la factura</h2>
            <label>
              Dies d'energia facturada
              <input
                type="number"
                min="1"
                value={form.billing_days}
                onChange={(event) => updateField('billing_days', event.target.value)}
              />
              <FieldError error={errors.billing_days} />
            </label>
            <label>
              Import factura competència
              <input
                type="number"
                min="0"
                step="0.01"
                value={form.competitor_invoice_amount}
                onChange={(event) => updateField('competitor_invoice_amount', event.target.value)}
              />
              <FieldError error={errors.competitor_invoice_amount} />
            </label>
            <label>
              Versio de plantilla (opcional)
              <input
                value={form.template_version}
                onChange={(event) => updateField('template_version', event.target.value)}
                placeholder="v1"
              />
              <small className="field-help">
                Si el deixeu buit, es fara servir la versio publicada. El preview HTML usa dades de mostra representatives.
              </small>
              <FieldError error={errors.template_version} />
            </label>
          </section>

          <section className="form-section template-admin-section">
            <div className="section-heading-row">
              <h2>Publicació de plantilla</h2>
              <span className="published-pill">
                {loadingPublication ? 'Carregant...' : `Publicada: ${publishedVersion || 'No disponible'}`}
              </span>
            </div>
            <p className="section-copy">
              La versió indicada al camp superior es pot publicar directament o utilitzar-se com a rollback cap a una versió anterior vàlida.
            </p>
            <div className="template-admin-actions">
              <button
                type="button"
                className="secondary"
                disabled={publishingAction !== '' || loadingPublication}
                onClick={() => handleTemplatePublication('publish')}
              >
                {publishingAction === 'publish' ? 'Publicant...' : 'Publicar versió'}
              </button>
              <button
                type="button"
                className="tertiary"
                disabled={publishingAction !== '' || loadingPublication}
                onClick={() => handleTemplatePublication('rollback')}
              >
                {publishingAction === 'rollback' ? 'Fent rollback...' : 'Fer rollback'}
              </button>
            </div>
            <FieldError error={errors.publication} />
            <StatusMessage message={publicationMessage} />
          </section>

          <section className="form-section">
            <h2>Consum per períodes</h2>
            <div className="period-grid">
              {['P1', 'P2', 'P3'].map((period) => (
                <label key={period}>
                  {period} (kWh)
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    value={form.energy_by_periods[period]}
                    onChange={(event) => updatePeriod(period, event.target.value)}
                  />
                  <FieldError error={errors[`energy_by_periods.${period}`]} />
                </label>
              ))}
            </div>
          </section>

          <div className="actions">
            <button type="submit" disabled={loadingPreview}>
              {loadingPreview ? 'Calculant...' : 'Veure resum'}
            </button>
            <button type="button" className="secondary" disabled={!preview || downloading} onClick={handleDownload}>
              {downloading ? 'Generant PDF...' : 'Descarregar PDF'}
            </button>
            <button type="button" className="tertiary" onClick={handleOpenHtmlPreview}>
              Obrir preview HTML
            </button>
          </div>
        </form>

        <aside className="summary-card">
          <h2>Resum</h2>
          {!preview && <p className="placeholder">Ompliu el formulari i premeu "Veure resum".</p>}

          {preview && (
            <>
              <div className="summary-grid">
                <SummaryItem label="Cost actual" value={formatEuro(preview.comparison.competitor_total)} />
                <SummaryItem label="Cost Som Energia" value={formatEuro(preview.comparison.som_total)} />
                <SummaryItem label={preview.comparison.savings_label} value={formatEuro(preview.comparison.savings)} />
              </div>

              <section className="mini-section">
                <h3>Dades</h3>
                <p><strong>Titular:</strong> {preview.customer.titular}</p>
                <p><strong>CUPS:</strong> {preview.customer.cups}</p>
                <p><strong>Dies:</strong> {preview.input.billing_days}</p>
              </section>

              <section className="mini-section">
                <h3>Detall</h3>
                <ul className="totals-list">
                  {preview.breakdown.totals.map((item) => (
                    <li key={item.label} className={item.is_total ? 'total-row' : ''}>
                      <span>{item.label}</span>
                      <strong>{formatEuro(item.amount)}</strong>
                    </li>
                  ))}
                </ul>
              </section>
            </>
          )}
        </aside>
      </div>
    </main>
  )
}

function FieldError({ error }) {
  if (!error) {
    return null
  }

  return <span className="field-error">{error}</span>
}

function SummaryItem({ label, value }) {
  return (
    <div className="summary-item">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}

function StatusMessage({ message }) {
  if (!message) {
    return null
  }

  return <p className="status-message">{message}</p>
}

function formatEuro(amount) {
  return new Intl.NumberFormat('ca-ES', {
    style: 'currency',
    currency: 'EUR',
  }).format(amount)
}

export default App
