import assert from 'node:assert/strict'
import { test } from 'node:test'
import { extractionSummary, optionalCostIssueFields, optionalIdentityIssueFields } from './extractionFeedback.js'

const energy = 'competitor_energy_eur'
const power = 'competitor_power_eur'
const missingCosts = [{ field: energy }, { field: power }]

test('un o dos imports opcionals absents permeten continuar sense reclamar revisió', () => {
  for (const issues of [missingCosts.slice(0, 1), missingCosts]) {
    const optional = optionalCostIssueFields(issues, { [energy]: '', [power]: '' })
    const message = extractionSummary('factura.pdf', 0, optional.size)
    assert.match(message, /Podeu continuar amb la simulació/)
    assert.match(message, /imports opcionals per al correu/)
    assert.doesNotMatch(message, /Cal revisar/)
  }
})

test('les dades necessàries pendents mantenen l’avís encara que faltin imports opcionals', () => {
  const message = extractionSummary('factura.pdf', 2, 2)
  assert.match(message, /Cal revisar 2 camps marcats/)
  assert.match(message, /imports opcionals sense extreure; aquests no impedeixen/)
  assert.doesNotMatch(message, /Podeu continuar/)
  assert.match(extractionSummary('factura.pdf', 1, 0), /Cal revisar 1 camp marcat/)
})

test('els imports completats, inclòs zero numèric o escrit, no mantenen l’avís d’absència', () => {
  for (const value of [0, '0', '0.00', 12.5, '12.50']) {
    assert.equal(optionalCostIssueFields(missingCosts, { [energy]: value, [power]: value }).size, 0)
  }
  assert.deepEqual([...optionalCostIssueFields(missingCosts, { [energy]: 0, [power]: '' })], [power])
})

test('no es confonen els camps necessaris amb imports opcionals', () => {
  const issues = [...missingCosts, { field: 'energy_by_periods.P1' }, { field: energy }]
  assert.deepEqual([...optionalCostIssueFields(issues, { [energy]: null, [power]: undefined })], [energy, power])
})

test('l’extracció completa no mostra avisos d’imports absents', () => {
  assert.equal(optionalCostIssueFields([], {}).size, 0)
  const message = extractionSummary('factura.pdf', 0, 0)
  assert.match(message, /No hi ha cap camp pendent/)
  assert.doesNotMatch(message, /sense extreure|Cal revisar/)
})

test('titular i CUPS absents es comuniquen com a opcionals, sense exigir revisió', () => {
  const issues = [{ field: 'cups' }, { field: 'titular' }, { field: 'billing_days' }]
  for (const empty of ['', null, undefined, '  ']) {
    const fields = optionalIdentityIssueFields(issues, { cups: empty, titular: empty })
    assert.deepEqual([...fields], ['cups', 'titular'])
    const message = extractionSummary('factura.pdf', 0, 0, fields.size)
    assert.match(message, /Podeu continuar/)
    assert.match(message, /dades identificatives opcionals/)
    assert.doesNotMatch(message, /Cal revisar/)
  }
})

test('els identificadors opcionals no amaguen avisos necessaris i deixen d’avisar en completar-los', () => {
  const issues = [{ field: 'cups' }, { field: 'titular' }]
  assert.equal(optionalIdentityIssueFields(issues, { cups: 'ES1234123456789012JY', titular: 'Persona' }).size, 0)
  const message = extractionSummary('factura.pdf', 1, 2, 2)
  assert.match(message, /Cal revisar 1 camp/)
  assert.match(message, /imports opcionals/)
  assert.match(message, /dades identificatives opcionals/)
})
