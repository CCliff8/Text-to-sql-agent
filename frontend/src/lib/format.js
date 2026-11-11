const clean = v => String(v ?? '').replace(/,/g, '').replace(/\$/g, '').trim()

// Identifier-like columns (custkey, year, rank...) are numbers but not quantities:
// "1995" must not become "1,995".
export function isIdLikeColumn(name) {
  return /(^|_)(key|id|year|month|day|rank|no|number)$/i.test(name) || /^(year|month|yr)$/i.test(name)
}

export function isNumericCol(rows, col) {
  const values = rows.map(r => r[col]).filter(v => v !== null && v !== undefined)
  return values.length > 0 && values.every(v => clean(v) !== '' && !isNaN(Number(clean(v))))
}

export function toNumber(value) {
  return parseFloat(clean(value))
}

export function formatNumeric(value) {
  const num = toNumber(value)
  if (isNaN(num)) return String(value ?? '')
  return Number.isInteger(num)
    ? num.toLocaleString()
    : num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

export function formatCost(usd) {
  if (!usd) return null
  return usd < 0.01 ? `$${usd.toFixed(4)}` : `$${usd.toFixed(3)}`
}
