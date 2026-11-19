import { emailCopy, emailTemplate } from './emailTemplates.js'

const euro = (value, locale) => new Intl.NumberFormat(locale, { style: 'currency', currency: 'EUR' }).format(value)
const bodyFontSize = '16px'
const emailFont = 'Arial, Helvetica, sans-serif'
const bodyTypography = `font-family:${emailFont};font-size:${bodyFontSize};line-height:24px;`
const tableTypography = bodyTypography
const unavailable = (value) => value.trim() || 'No disponible'
const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (char) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
})[char])

export function initialEmailDraft(report, retailer, locale = report.input?.locale || 'ca') {
  const { savings } = report.comparison
  const language = locale === 'es' ? 'es' : 'ca'
  return {
    language, retailer: retailer || '', renewable: '', nonprofit: '❌ No', beneficiaries: emailCopy[language].beneficiaries, ocu: '', permanence: '',
    reason: report.reason_suggestion?.reason || '',
    reasonManual: false,
    ...emailTemplate(savings, language),
  }
}

// Només admetem enllaços HTTPS; la resta del redactat es tracta com a text.
function paragraphs(text, theme) {
  const formatText = (value) => escapeHtml(value).replace(
    /(El resultat és|El resultado es) (desfavorable|favorable)\b/g,
    (_, prefix, result) => `${prefix} <strong${result === 'favorable' ? ` style="background-color:${theme.button};color:${theme.buttonText};"` : ''}>${result}</strong>`,
  )
  return text.split(/\n\s*\n/).filter(Boolean).map((paragraph) => {
    const callToAction = paragraph.trim().match(/^\[(Vols unir-te a Som Energia\?|¿Te unes a Som Energia\?)\]\((https:\/\/[^\s)]+)\)$/)
    if (callToAction) {
      return `<p style="${bodyTypography}text-align:center;margin:24px 0;"><a href="${escapeHtml(callToAction[2])}" style="${bodyTypography}display:inline-block;background-color:${theme.button};color:${theme.buttonText};border:1px solid transparent;border-radius:999px;padding:8px 18px;font-weight:400;text-decoration:none;text-align:center;">${escapeHtml(callToAction[1])}</a></p>`
    }
    const parts = []
    let cursor = 0
    for (const match of paragraph.matchAll(/\[([^\]\n]+)\]\((https:\/\/[^\s)]+)\)/g)) {
      parts.push(formatText(paragraph.slice(cursor, match.index)))
      parts.push(`<a href="${escapeHtml(match[2])}" style="${bodyTypography}color:${theme.link};text-decoration:underline;">${escapeHtml(match[1])}</a>`)
      cursor = match.index + match[0].length
    }
    parts.push(formatText(paragraph.slice(cursor)))
    const content = parts.join('').replace(/\n/g, '<br>')
    const formatted = /^💡 (Consell|Consejo):/.test(paragraph.trim())
      ? content.replace(/(Consell|Consejo):/, `<span style="color:${theme.tip};">$1</span>:`)
      : content
    return `<p style="${bodyTypography}margin:0;padding-bottom:24px;">${formatted}</p>`
  }).join('')
}

export function buildEmailHtml(report, draft, theme) {
  const { competitor_total: current, som_total: som, savings } = report.comparison
  const copy = emailCopy[draft.language] || emailCopy.ca
  const rows = [
    [`${copy.cost} (${report.input.billing_days} ${copy.days})`, euro(current, copy.locale), euro(som, copy.locale)],
    [copy.difference, euro(Math.abs(savings), copy.locale)],
    [copy.renewable, unavailable(draft.renewable), '100%'],
    [copy.nonprofit, unavailable(draft.nonprofit), '✅ Sí'],
    [copy.profits, unavailable(draft.beneficiaries), copy.cooperative],
    [copy.ocu, unavailable(draft.ocu), copy.best],
    [copy.permanence, unavailable(draft.permanence), '✅ No'],
  ]
  const cell = `${tableTypography}padding:12px;border-bottom:1px solid ${theme.divider};`
  const part = copy.reasonParts[draft.reason]
  const reason = part && savings !== 0 ? copy.reason(part, savings < 0) : ''
  // FreeScout filtra align als th; td conserva l’alineació i evita el centrat per defecte.
  return `<div lang="${draft.language === 'es' ? 'es' : 'ca'}" style="${bodyTypography}color:${theme.text};background-color:${theme.surface};padding:20px;">
    ${paragraphs(draft.intro, theme)}
    <table style="${tableTypography}width:100%;border-collapse:collapse;color:${theme.text};">
      <caption style="${tableTypography}text-align:left;font-weight:bold;padding:12px 0;">${copy.summary}</caption>
      <thead><tr style="background-color:${theme.tablePanel};"><td role="columnheader" align="left" width="35%" style="${cell}width:35%;text-align:left;font-weight:bold;">${copy.concept}</td><td role="columnheader" align="right" style="${cell}text-align:right;font-weight:bold;">${escapeHtml(draft.retailer.trim() || copy.retailer)}</td><td role="columnheader" align="right" style="${cell}text-align:right;font-weight:bold;">Som Energia</td></tr></thead>
      <tbody>${rows.map((row, index) => `<tr${index === 1 ? ' style="font-weight:bold;"' : ''}>${row.map((value, column) => column === 0
        ? `<td role="rowheader" align="left" style="${cell}width:35%;text-align:left;font-weight:${index < 2 ? 'bold' : 'normal'};">${escapeHtml(value)}</td>`
        : `<td${index === 1 ? ' colspan="2"' : ''} align="${index === 1 ? 'center' : 'right'}" style="${cell}text-align:${index === 1 ? 'center' : 'right'};${index === 1 ? 'font-weight:bold;' : ''}${index < 2 ? 'white-space:nowrap;font-variant-numeric:tabular-nums;' : ''}">${escapeHtml(value)}</td>`).join('')}</tr>`).join('')}</tbody>
    </table>
    <div style="padding-top:32px;">
    ${reason ? paragraphs(reason, theme) : ''}
    ${paragraphs(draft.body, theme)}
    </div>
  </div>`
}
