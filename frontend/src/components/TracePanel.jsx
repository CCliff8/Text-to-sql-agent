import { SqlCode } from '../lib/sql'

function extractTables(sql) {
  if (!sql) return []
  const matches = [...sql.matchAll(/(?:FROM|JOIN)\s+([a-zA-Z_]\w*)/gi)]
  const seen = new Set()
  return matches
    .map(m => m[1].toLowerCase())
    .filter(t => { if (seen.has(t)) return false; seen.add(t); return true })
}

function SchemaStep({ result }) {
  let tables = []
  try { tables = Object.keys(JSON.parse(result)) } catch {}
  return (
    <>
      <p className="text-[13px] font-medium text-gray-800 mb-2">Schema inspection</p>
      <div className="flex flex-wrap gap-1.5">
        {tables.map(t => (
          <span key={t} className="font-mono text-[11.5px] bg-gray-50 border border-gray-200 text-gray-600 px-2 py-0.5 rounded-md">
            {t}
          </span>
        ))}
      </div>
    </>
  )
}

function SampleStep({ input, result }) {
  const table = input?.table_name || '?'
  let cols = [], rowCount = 0
  try {
    const d = JSON.parse(result)
    cols = d.columns || []
    rowCount = d.rows?.length || 0
  } catch {}
  return (
    <>
      <p className="text-[13px] font-medium text-gray-800 mb-2">
        Sampled table <code className="font-mono text-[12px] bg-gray-100 text-gray-700 px-1.5 py-0.5 rounded">{table}</code>
      </p>
      <div className="flex flex-wrap gap-1.5 mb-1.5">
        {cols.slice(0, 10).map(c => (
          <span key={c} className="font-mono text-[11.5px] bg-gray-50 border border-gray-200 text-gray-600 px-2 py-0.5 rounded-md">
            {c}
          </span>
        ))}
        {cols.length > 10 && (
          <span className="text-[11px] text-gray-400 self-center">+{cols.length - 10} more</span>
        )}
      </div>
      <p className="text-[12px] text-gray-400"><strong className="text-gray-500">{rowCount}</strong> sample rows</p>
    </>
  )
}

function SqlStep({ input, result }) {
  const query = input?.query?.trim() || ''
  let rowCount = null, truncated = false, isError = false, errorMsg = ''
  try {
    const d = JSON.parse(result)
    if (d.error) { isError = true; errorMsg = d.error }
    else { rowCount = d.row_count ?? d.rows?.length; truncated = !!d.truncated }
  } catch {}
  return (
    <>
      <p className="text-[13px] font-medium text-gray-800 mb-2">SQL query</p>
      <pre className={`text-[12px] leading-relaxed font-mono rounded-lg p-3 overflow-x-auto ${
        isError
          ? 'bg-red-50 border border-red-200 text-red-800'
          : 'bg-gray-50 border border-gray-200 text-gray-800'
      }`}>
        <SqlCode sql={query} />
      </pre>
      {isError
        ? <p className="text-[12px] text-red-500 mt-1.5">Error: {errorMsg}</p>
        : rowCount != null && (
          <p className="text-[12px] text-gray-400 mt-1.5">
            <strong className="text-gray-500">{rowCount}{truncated ? '+' : ''}</strong> rows returned{truncated ? ' (truncated)' : ''}
          </p>
        )
      }
    </>
  )
}

export default function TracePanel({ steps, sql, id }) {
  const tables = extractTables(sql)

  return (
    <div id={id} className="mt-3 bg-white border border-gray-200 rounded-2xl shadow-sm overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-2 bg-gray-50 border-b border-gray-100 px-5 py-3">
        <span className="text-[13.5px] font-semibold text-gray-800">How I got this</span>
        <span className="text-[11px] font-semibold bg-gray-200 text-gray-600 rounded-full px-2 py-0.5">
          {steps.length} steps
        </span>
      </div>

      {/* Steps */}
      {steps.map((step, i) => (
        <div key={i} className="flex gap-3 px-5 py-4 border-b border-gray-50 last:border-b-0">
          <div className="shrink-0 w-[22px] h-[22px] mt-0.5 rounded-full bg-blue-50 border border-blue-200 text-blue-600 text-[11px] font-bold flex items-center justify-center">
            {i + 1}
          </div>
          <div className="flex-1 min-w-0">
            {step.tool === 'get_schema' && <SchemaStep result={step.result} />}
            {step.tool === 'sample_table' && <SampleStep input={step.input} result={step.result} />}
            {step.tool === 'run_sql' && <SqlStep input={step.input} result={step.result} />}
            {!['get_schema','sample_table','run_sql'].includes(step.tool) && (
              <p className="text-[13px] font-medium text-gray-800">{step.tool}</p>
            )}
          </div>
        </div>
      ))}

      {/* Tables used */}
      {tables.length > 0 && (
        <div className="bg-gray-50 border-t border-gray-100 px-5 py-3">
          <p className="text-[10.5px] font-bold tracking-widest text-gray-400 uppercase mb-2">Tables used</p>
          <div className="flex flex-wrap gap-1.5">
            {tables.map(t => (
              <span key={t} className="font-mono text-[11.5px] bg-white border border-gray-200 text-gray-600 px-2 py-0.5 rounded-md">
                {t}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
