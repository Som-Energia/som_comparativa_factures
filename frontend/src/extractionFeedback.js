export const optionalCostFields = new Set(['competitor_energy_eur', 'competitor_power_eur'])
export const optionalIdentityFields = new Set(['cups', 'titular'])

export function optionalIdentityIssueFields(issues, form) {
  return new Set(issues
    .filter(({ field }) => optionalIdentityFields.has(field)
      && (form[field] == null || String(form[field]).trim() === ''))
    .map(({ field }) => field))
}

export function optionalCostIssueFields(issues, form) {
  return new Set(issues
    .filter(({ field }) => optionalCostFields.has(field)
      && (form[field] === '' || form[field] == null))
    .map(({ field }) => field))
}

export function extractionSummary(fileName, issueCount, optionalIssueCount = 0, identityIssueCount = 0) {
  const source = `Dades extretes de ${fileName}.`
  const identityNote = identityIssueCount > 0 ? ' Hi ha dades identificatives opcionals sense extreure; podeu deixar-les en blanc.' : ''
  if (issueCount > 0) {
    return `${source} Cal revisar ${issueCount === 1 ? '1 camp marcat' : `${issueCount} camps marcats`} al formulari.${optionalIssueCount > 0 ? ' També hi ha imports opcionals sense extreure; aquests no impedeixen calcular la simulació.' : ''}${identityNote}`
  }
  if (optionalIssueCount > 0) {
    return `${source} Podeu continuar amb la simulació. Els imports opcionals per al correu no s’han pogut extreure.${identityNote}`
  }
  if (identityIssueCount > 0) return `${source} Podeu continuar amb la simulació.${identityNote}`
  return `${source} No hi ha cap camp pendent de revisar.`
}
