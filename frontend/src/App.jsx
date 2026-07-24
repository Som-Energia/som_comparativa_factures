import { useEffect, useState } from 'react'

const apiBaseUrl = '/api'

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
  contracted_power_kw_by_periods: {
    P1: '',
    P2: '',
  },
  self_consumption_surplus_kwh: '',
  meter_rental_eur: '',
  vat_rate_percent: '21',
  electric_tax_rate_percent: '5.11',
}

const initialTemplateFiles = {
  content: '',
  theme: '',
  assets: '',
}

function App() {
  const [screen, setScreen] = useState('compare')

  return (
    <main className="page-shell">
      <section className="hero-card">
        <p className="eyebrow">MVP comparativa</p>
        <h1>Simulacio de factura Som Energia</h1>
        <p className="hero-copy">
          Calcula comparatives i gestiona versions de plantilla PDF sense exposar el shell tècnic.
        </p>
        <div className="screen-switcher">
          <button type="button" className={screen === 'compare' ? '' : 'tertiary'} onClick={() => setScreen('compare')}>
            Comparativa
          </button>
          <button type="button" className={screen === 'templates' ? '' : 'tertiary'} onClick={() => setScreen('templates')}>
            Editor de plantilles
          </button>
        </div>
      </section>

      {screen === 'compare' ? <CompareScreen /> : <TemplateEditorScreen />}
    </main>
  )
}

function CompareScreen() {
  const [form, setForm] = useState(initialForm)
  const [inputMode, setInputMode] = useState('form')
  const [rawJson, setRawJson] = useState('')
  const [errors, setErrors] = useState({})
  const [preview, setPreview] = useState(null)
  const [loadingPreview, setLoadingPreview] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [openingHtmlPreview, setOpeningHtmlPreview] = useState(false)

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

  function updatePowerPeriod(period, value) {
    setForm((current) => ({
      ...current,
      contracted_power_kw_by_periods: {
        ...current.contracted_power_kw_by_periods,
        [period]: value,
      },
    }))
  }

  function buildPayload() {
    if (inputMode === 'json') {
      try {
        const payload = JSON.parse(rawJson)
        if (!payload || Array.isArray(payload)) {
          throw new Error('El JSON ha de contenir un objecte de comparativa.')
        }
        return payload
      } catch (error) {
        if (error instanceof SyntaxError) {
          throw new Error('El JSON no és vàlid.')
        }
        throw error
      }
    }

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
      contracted_power_kw_by_periods: {
        P1: Number(form.contracted_power_kw_by_periods.P1),
        P2: Number(form.contracted_power_kw_by_periods.P2),
      },
      self_consumption_surplus_kwh: Number(form.self_consumption_surplus_kwh),
      meter_rental_eur: Number(form.meter_rental_eur),
      vat_rate_percent: Number(form.vat_rate_percent),
      electric_tax_rate_percent: Number(form.electric_tax_rate_percent),
    }

    const templateVersion = form.template_version.trim()
    if (templateVersion) {
      payload.template_version = templateVersion
    }

    return payload
  }

  function getPayload() {
    try {
      return buildPayload()
    } catch (error) {
      setErrors({ raw_json: error.message })
      return null
    }
  }

  function changeInputMode(mode) {
    setInputMode(mode)
    setErrors({})
    setPreview(null)
  }

  async function handlePreview(event) {
    event.preventDefault()
    const payload = getPayload()
    if (!payload) {
      return
    }

    setLoadingPreview(true)
    setErrors({})

    const response = await fetch(`${apiBaseUrl}/compare`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
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
    const payload = getPayload()
    if (!payload) {
      return
    }

    setDownloading(true)
    setErrors({})

    const response = await fetch(`${apiBaseUrl}/reports/comparison.pdf`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
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

  async function handleOpenHtmlPreview() {
    const payload = getPayload()
    if (!payload) {
      return
    }

    const previewWindow = window.open('', '_blank')
    setOpeningHtmlPreview(true)
    setErrors({})

    const response = await fetch(`${apiBaseUrl}/reports/comparison.preview`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })

    setOpeningHtmlPreview(false)

    if (!response.ok) {
      const data = await response.json()
      previewWindow?.close()
      setErrors(data.errors || {})
      return
    }

    const url = URL.createObjectURL(await response.blob())
    if (previewWindow) {
      previewWindow.location.href = url
    } else {
      window.open(url, '_blank', 'noopener,noreferrer')
    }
    window.setTimeout(() => URL.revokeObjectURL(url), 60000)
  }

  return (
    <div className="layout">
      <form className="form-card" onSubmit={handlePreview} autoComplete="on">
        <div className="input-mode-switcher" role="group" aria-label="Mode d'entrada">
          <button type="button" className={inputMode === 'form' ? '' : 'tertiary'} onClick={() => changeInputMode('form')}>
            Formulari
          </button>
          <button type="button" className={inputMode === 'json' ? '' : 'tertiary'} onClick={() => changeInputMode('json')}>
            JSON
          </button>
        </div>

        {inputMode === 'form' ? (
          <>
        <section className="form-section">
          <h2>Titular i contracte</h2>
          <label>
            Titular
            <input
              name="titular"
              autoComplete="name"
              value={form.titular}
              onChange={(event) => updateField('titular', event.target.value)}
            />
            <FieldError error={errors.titular} />
          </label>
          <label>
            CUPS
            <input
              name="cups"
              autoComplete="on"
              value={form.cups}
              onChange={(event) => updateField('cups', event.target.value)}
            />
            <FieldError error={errors.cups} />
          </label>
        </section>

        <section className="form-section">
          <h2>Dades de la factura</h2>
          <label>
            Dies d'energia facturada
            <input
              type="number"
              name="billing_days"
              autoComplete="on"
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
              name="competitor_invoice_amount"
              autoComplete="on"
              min="0"
              step="0.01"
              value={form.competitor_invoice_amount}
              onChange={(event) => updateField('competitor_invoice_amount', event.target.value)}
            />
            <FieldError error={errors.competitor_invoice_amount} />
          </label>
          <label>
            Lloguer del comptador (EUR)
            <input
              type="number"
              name="meter_rental_eur"
              autoComplete="on"
              min="0"
              step="0.01"
              value={form.meter_rental_eur}
              onChange={(event) => updateField('meter_rental_eur', event.target.value)}
            />
            <FieldError error={errors.meter_rental_eur} />
          </label>
          <div className="two-column-grid">
            <label>
              IVA (%)
              <input
                type="number"
                name="vat_rate_percent"
                autoComplete="on"
                min="0"
                max="100"
                step="0.01"
                value={form.vat_rate_percent}
                onChange={(event) => updateField('vat_rate_percent', event.target.value)}
              />
              <FieldError error={errors.vat_rate_percent} />
            </label>
            <label>
              IESE (%)
              <input
                type="number"
                name="electric_tax_rate_percent"
                autoComplete="on"
                min="0"
                max="100"
                step="0.01"
                value={form.electric_tax_rate_percent}
                onChange={(event) => updateField('electric_tax_rate_percent', event.target.value)}
              />
              <FieldError error={errors.electric_tax_rate_percent} />
            </label>
          </div>
          <label>
            Versio de plantilla (opcional)
            <input
              value={form.template_version}
              onChange={(event) => updateField('template_version', event.target.value)}
              placeholder="v1"
            />
            <small className="field-help">
              Si el deixeu buit, es farà servir la versió publicada.
            </small>
            <FieldError error={errors.template_version} />
          </label>
        </section>

        <section className="form-section">
          <h2>Potència i autoconsum</h2>
          <div className="two-column-grid">
            {['P1', 'P2'].map((period) => (
              <label key={period}>
                Potència contractada {period} (kW)
                <input
                  type="number"
                  name={`contracted_power_kw_${period}`}
                  autoComplete="on"
                  min="0"
                  step="0.01"
                  value={form.contracted_power_kw_by_periods[period]}
                  onChange={(event) => updatePowerPeriod(period, event.target.value)}
                />
                <FieldError error={errors[`contracted_power_kw_by_periods.${period}`]} />
              </label>
            ))}
          </div>
          <label>
            Excedents d'autoconsum (kWh)
            <input
              type="number"
              name="self_consumption_surplus_kwh"
              autoComplete="on"
              min="0"
              step="0.01"
              value={form.self_consumption_surplus_kwh}
              onChange={(event) => updateField('self_consumption_surplus_kwh', event.target.value)}
            />
            <FieldError error={errors.self_consumption_surplus_kwh} />
          </label>
        </section>

        <section className="form-section">
          <h2>Consum per períodes</h2>
          <div className="period-grid">
            {['P1', 'P2', 'P3'].map((period) => (
              <label key={period}>
                {period} (kWh)
                <input
                  type="number"
                  name={`energy_kwh_${period}`}
                  autoComplete="on"
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

          </>
        ) : (
          <section className="form-section">
            <h2>Entrada JSON</h2>
            <p className="section-copy">
              Enganxeu el payload de comparativa. Aquest serà el punt d’entrada per a una futura extracció de PDF a JSON.
            </p>
            <label>
              JSON de la factura
              <textarea
                className="json-input"
                name="raw_json"
                autoComplete="off"
                spellCheck="false"
                value={rawJson}
                onChange={(event) => setRawJson(event.target.value)}
                placeholder={'{\n  "cups": "ES0210002100000000ZN0F",\n  "titular": "Persona Persona"\n}'}
              />
              <FieldError error={errors.raw_json} />
            </label>
          </section>
        )}

        <div className="actions">
          <button type="submit" disabled={loadingPreview}>
            {loadingPreview ? 'Calculant...' : 'Veure resum'}
          </button>
          <button type="button" className="secondary" disabled={!preview || downloading} onClick={handleDownload}>
            {downloading ? 'Generant PDF...' : 'Descarregar PDF'}
          </button>
          <button type="button" className="tertiary" disabled={openingHtmlPreview} onClick={handleOpenHtmlPreview}>
            {openingHtmlPreview ? 'Obrint preview...' : 'Obrir preview HTML'}
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
              <p><strong>Flux Solar:</strong> {formatKwh(preview.breakdown.flux_solar_kwh)}</p>
              {preview.breakdown.flux_solar_kwh > 0 && (
                <p className="field-help">Disponible com a descompte en factures posteriors.</p>
              )}
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
  )
}

function TemplateEditorScreen() {
  const [versions, setVersions] = useState([])
  const [publishedVersion, setPublishedVersion] = useState('')
  const [selectedVersion, setSelectedVersion] = useState('')
  const [versionStatus, setVersionStatus] = useState('')
  const [files, setFiles] = useState(initialTemplateFiles)
  const [activeFile, setActiveFile] = useState('content')
  const [previewHtml, setPreviewHtml] = useState('')
  const [previewError, setPreviewError] = useState('')
  const [editorErrors, setEditorErrors] = useState({})
  const [versionMessage, setVersionMessage] = useState('')
  const [newVersion, setNewVersion] = useState('')
  const [loadingVersions, setLoadingVersions] = useState(true)
  const [loadingVersionDetail, setLoadingVersionDetail] = useState(false)
  const [creatingVersion, setCreatingVersion] = useState(false)
  const [savingVersion, setSavingVersion] = useState(false)
  const [publishingAction, setPublishingAction] = useState('')

  useEffect(() => {
    loadVersions()
  }, [])

  useEffect(() => {
    if (!selectedVersion) {
      return
    }

    loadVersionDetail(selectedVersion)
  }, [selectedVersion])

  useEffect(() => {
    if (!selectedVersion || loadingVersionDetail || !files.content || !files.theme || !files.assets) {
      return
    }

    const timeoutId = window.setTimeout(async () => {
      const response = await fetch(`${apiBaseUrl}/templates/comparison/versions/${selectedVersion}/preview`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ files }),
      })
      const data = await response.json()

      if (!response.ok) {
        setPreviewHtml('')
        setPreviewError(data.errors?.template_version || 'No s\'ha pogut renderitzar el preview.')
        return
      }

      setPreviewError('')
      setPreviewHtml(data.html)
    }, 450)

    return () => window.clearTimeout(timeoutId)
  }, [selectedVersion, files, loadingVersionDetail])

  async function loadVersions(preferredVersion) {
    setLoadingVersions(true)
    const response = await fetch(`${apiBaseUrl}/templates/comparison/versions`)
    const data = await response.json()
    setLoadingVersions(false)

    if (!response.ok) {
      setEditorErrors(data.errors || {})
      return
    }

    setVersions(data.versions)
    setPublishedVersion(data.published_version)
    const resolvedVersion = resolvePreferredVersion(data.versions, preferredVersion || selectedVersion)
    setSelectedVersion(resolvedVersion)
  }

  function resolvePreferredVersion(versionList, preferredVersion) {
    if (preferredVersion && versionList.some((item) => item.version === preferredVersion)) {
      return preferredVersion
    }

    const draft = versionList.find((item) => item.status === 'draft')
    return draft?.version || versionList[0]?.version || ''
  }

  async function loadVersionDetail(version) {
    setLoadingVersionDetail(true)
    setVersionMessage('')
    const response = await fetch(`${apiBaseUrl}/templates/comparison/versions/${version}`)
    const data = await response.json()
    setLoadingVersionDetail(false)

    if (!response.ok) {
      setEditorErrors(data.errors || {})
      return
    }

    setEditorErrors({})
    setVersionStatus(data.status)
    setFiles(data.files)
  }

  function updateFileContent(fileKey, value) {
    setFiles((current) => ({ ...current, [fileKey]: value }))
    setEditorErrors({})
    setVersionMessage('')
  }

  async function handleCreateVersion() {
    if (!selectedVersion || !newVersion.trim()) {
      setEditorErrors({ target_version: 'Cal indicar una nova versió.' })
      return
    }

    setCreatingVersion(true)
    setVersionMessage('')
    const response = await fetch(`${apiBaseUrl}/templates/comparison/versions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source_version: selectedVersion, target_version: newVersion.trim() }),
    })
    const data = await response.json()
    setCreatingVersion(false)

    if (!response.ok) {
      setEditorErrors(data.errors || {})
      return
    }

    setEditorErrors({})
    setVersionMessage(`S'ha creat la versió ${data.version} a partir de ${selectedVersion}.`)
    setNewVersion('')
    await loadVersions(data.version)
  }

  async function handleSaveVersion() {
    setSavingVersion(true)
    setVersionMessage('')
    const response = await fetch(`${apiBaseUrl}/templates/comparison/versions/${selectedVersion}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ files }),
    })
    const data = await response.json()
    setSavingVersion(false)

    if (!response.ok) {
      setEditorErrors(data.errors || {})
      return
    }

    setEditorErrors({})
    setFiles(data.files)
    setVersionStatus(data.status)
    setVersionMessage(`S'ha desat la versió ${selectedVersion}.`)
  }

  async function handlePublicationAction(action) {
    setPublishingAction(action)
    setVersionMessage('')
    const response = await fetch(`${apiBaseUrl}/templates/comparison/${action}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ template_version: selectedVersion }),
    })
    const data = await response.json()
    setPublishingAction('')

    if (!response.ok) {
      setEditorErrors(data.errors || {})
      return
    }

    setEditorErrors({})
    setVersionMessage(data.message)
    await loadVersions(selectedVersion)
  }

  const selectedMeta = versions.find((item) => item.version === selectedVersion)
  const isEditable = selectedMeta?.status === 'draft'
  const canRollback = selectedMeta?.status === 'historical'

  return (
    <section className="editor-layout">
      <div className="editor-panel editor-controls-panel">
        <div className="editor-header-row">
          <div>
            <p className="eyebrow">Editor YAML</p>
            <h2>Versions de plantilla</h2>
          </div>
          <span className="published-pill">Publicada: {publishedVersion || '...'}</span>
        </div>

        <div className="editor-toolbar">
          <label>
            Versió activa
            <select value={selectedVersion} onChange={(event) => setSelectedVersion(event.target.value)} disabled={loadingVersions}>
              {versions.map((item) => (
                <option key={item.version} value={item.version}>
                  {item.version} · {statusLabel(item.status)}
                </option>
              ))}
            </select>
          </label>
          <div className="status-card">
            <span className={`status-pill ${selectedMeta?.status || ''}`}>{statusLabel(selectedMeta?.status)}</span>
            <p>
              {selectedMeta?.status === 'draft' && 'Versió editable. La pots modificar i previsualitzar abans de publicar.'}
              {selectedMeta?.status === 'published' && 'Aquesta versió està en producció i queda bloquejada per evitar canvis directes.'}
              {selectedMeta?.status === 'historical' && 'Versió anterior. Pots fer rollback o clonar-la a una versió nova.'}
            </p>
          </div>
        </div>

        <div className="create-version-row">
          <label>
            Nova versió des de {selectedVersion || '...'}
            <input value={newVersion} onChange={(event) => setNewVersion(event.target.value)} placeholder="v2" />
          </label>
          <button type="button" className="secondary" disabled={!selectedVersion || creatingVersion} onClick={handleCreateVersion}>
            {creatingVersion ? 'Creant...' : 'Crear versió'}
          </button>
        </div>
        <FieldError error={editorErrors.target_version || editorErrors.source_version} />

        <div className="editor-tabs">
          {Object.keys(files).map((fileKey) => (
            <button
              key={fileKey}
              type="button"
              className={activeFile === fileKey ? '' : 'tertiary'}
              onClick={() => setActiveFile(fileKey)}
            >
              {fileKey}.yaml
            </button>
          ))}
        </div>

        <textarea
          className="yaml-editor"
          value={files[activeFile]}
          onChange={(event) => updateFileContent(activeFile, event.target.value)}
          disabled={loadingVersionDetail || !isEditable}
          spellCheck="false"
        />

        <div className="editor-actions">
          <button type="button" disabled={!isEditable || savingVersion} onClick={handleSaveVersion}>
            {savingVersion ? 'Desant...' : 'Desar versió'}
          </button>
          <button
            type="button"
            className="secondary"
            disabled={!isEditable || publishingAction !== ''}
            onClick={() => handlePublicationAction('publish')}
          >
            {publishingAction === 'publish' ? 'Publicant...' : 'Publicar'}
          </button>
          <button
            type="button"
            className="tertiary"
            disabled={!canRollback || publishingAction !== ''}
            onClick={() => handlePublicationAction('rollback')}
          >
            {publishingAction === 'rollback' ? 'Fent rollback...' : 'Fer rollback'}
          </button>
        </div>

        <FieldError error={editorErrors.template_version || editorErrors.files || editorErrors.template_versions} />
        <StatusMessage message={versionMessage} />
      </div>

      <div className="editor-panel preview-panel">
        <div className="editor-header-row">
          <div>
            <p className="eyebrow">Preview en viu</p>
            <h2>Render HTML</h2>
          </div>
        </div>
        {previewError ? <p className="preview-error">{previewError}</p> : null}
        {!previewError && !previewHtml ? <p className="placeholder">Carregant preview...</p> : null}
        <iframe className="preview-frame" title="Template preview" srcDoc={previewHtml} />
      </div>
    </section>
  )
}

function FieldError({ error }) {
  if (!error) {
    return null
  }

  return <span className="field-error">{error}</span>
}

function StatusMessage({ message }) {
  if (!message) {
    return null
  }

  return <p className="status-message">{message}</p>
}

function SummaryItem({ label, value }) {
  return (
    <div className="summary-item">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}

function statusLabel(status) {
  if (status === 'draft') {
    return 'Draft'
  }
  if (status === 'published') {
    return 'Publicada'
  }
  if (status === 'historical') {
    return 'Històrica'
  }
  return 'Sense estat'
}

function formatEuro(amount) {
  return new Intl.NumberFormat('ca-ES', {
    style: 'currency',
    currency: 'EUR',
  }).format(amount)
}

function formatKwh(amount) {
  return new Intl.NumberFormat('ca-ES', {
    maximumFractionDigits: 2,
  }).format(amount) + ' kWh'
}

export default App
