import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from 'recharts'
import { formatNumeric, isIdLikeColumn, isNumericCol, toNumber } from '../lib/format'

const MAX_CHART_ROWS = 15

function getTableData(result) {
  const sqlSteps = (result.steps || []).filter(s => s.tool === 'run_sql')
  if (!sqlSteps.length) return null
  try {
    const data = JSON.parse(sqlSteps[sqlSteps.length - 1].result)
    if (data.error || !data.rows?.length || !data.columns?.length) return null
    return { columns: data.columns, rows: data.rows, truncated: !!data.truncated }
  } catch {
    return null
  }
}

function downloadCSV(columns, rows, answer) {
  const filename = (answer || 'results')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 50) + '.csv'

  const escape = v => {
    const s = String(v ?? '')
    return (s.includes(',') || s.includes('"') || s.includes('\n'))
      ? `"${s.replace(/"/g, '""')}"` : s
  }

  const csv = [
    columns.map(escape).join(','),
    ...rows.map(r => columns.map(c => escape(r[c])).join(',')),
  ].join('\n')

  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-white border border-gray-200 rounded-xl shadow-lg px-4 py-2.5 text-sm">
      <p className="font-semibold text-gray-900">{label}</p>
      <p className="text-blue-600 font-bold mt-0.5">
        {Number(payload[0].value).toLocaleString()}
      </p>
    </div>
  )
}

export default function AnswerCard({ result, question }) {
  const tableData = getTableData(result)

  // Numeric columns are right-aligned; identifier-like ones (keys, years) are not formatted as quantities.
  const numericCols = tableData
    ? Object.fromEntries(tableData.columns.map(c => [c, isNumericCol(tableData.rows, c)]))
    : {}
  const formattedCols = tableData
    ? Object.fromEntries(tableData.columns.map(c => [c, numericCols[c] && !isIdLikeColumn(c)]))
    : {}

  const chartable = tableData &&
    tableData.rows.length >= 2 &&
    tableData.columns.length === 2 &&
    numericCols[tableData.columns[1]] &&
    !isIdLikeColumn(tableData.columns[1])

  const allChartRows = chartable
    ? tableData.rows.map(r => ({
        name: String(r[tableData.columns[0]]),
        value: toNumber(r[tableData.columns[1]]),
      }))
    : []
  const chartRows = allChartRows.slice(0, MAX_CHART_ROWS)

  const unverified = result.answer_check?.verified === false

  return (
    <div className="mt-6 bg-white border border-gray-200 rounded-2xl shadow-sm overflow-hidden">

      {/* Answer text */}
      <div className="px-8 pt-7 pb-5">
        {question && (
          <p className="text-[12px] text-gray-400 mb-2">{question}</p>
        )}
        <p className="text-[17px] font-semibold text-gray-900 leading-snug">
          {result.answer}
        </p>
        {unverified && (
          <p role="note" className="mt-3 text-[12px] text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
            Some numbers in this answer could not be matched to the query results. Check the table or the SQL before relying on them.
          </p>
        )}
      </div>

      {/* Table */}
      {tableData && (
        <div className="border-t border-gray-100">

          {/* Toolbar */}
          <div className="flex items-center justify-between px-6 py-3 bg-gray-50 border-b border-gray-100">
            <span className="text-[11px] font-bold tracking-widest text-gray-400 uppercase">
              {tableData.truncated
                ? `First ${tableData.rows.length} rows (more exist)`
                : `${tableData.rows.length} row${tableData.rows.length !== 1 ? 's' : ''}`}
            </span>
            <button
              onClick={() => downloadCSV(tableData.columns, tableData.rows, question || result.answer)}
              className="flex items-center gap-1.5 text-[12px] font-medium text-gray-500 hover:text-blue-600 border border-gray-200 hover:border-blue-400 bg-white hover:bg-blue-50/60 rounded-lg px-3 py-1.5 transition-all cursor-pointer shadow-sm"
            >
              <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M8 2v9"/>
                <path d="M4 7l4 4 4-4"/>
                <path d="M2 13h12"/>
              </svg>
              Export CSV
            </button>
          </div>

          {/* Table body */}
          <div className="overflow-x-auto">
            <table className="w-full">
              <caption className="sr-only">Query results</caption>
              <thead>
                <tr>
                  {tableData.columns.map(col => (
                    <th
                      key={col}
                      scope="col"
                      className={`px-6 py-2.5 text-[10.5px] font-bold tracking-wider text-gray-500 uppercase bg-gray-50 border-b border-gray-100 ${
                        numericCols[col] ? 'text-right' : 'text-left'
                      }`}
                    >
                      {col.replace(/_/g, ' ')}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {tableData.rows.map((row, i) => (
                  <tr
                    key={i}
                    className={`border-b border-gray-50 last:border-b-0 hover:bg-blue-50/30 transition-colors ${
                      i % 2 === 1 ? 'bg-gray-50/40' : 'bg-white'
                    }`}
                  >
                    {tableData.columns.map(col => (
                      <td
                        key={col}
                        className={`px-6 py-3 text-[13px] text-gray-800 ${
                          numericCols[col] ? 'text-right tabular-nums font-medium' : 'text-left'
                        }`}
                      >
                        {formattedCols[col] ? formatNumeric(row[col]) : String(row[col] ?? '')}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Chart */}
      {chartable && (
        <div className="border-t border-gray-100 px-6 pt-5 pb-7">
          <p className="text-[10.5px] font-bold tracking-widest text-gray-400 uppercase mb-4">
            Chart{allChartRows.length > MAX_CHART_ROWS ? ` (top ${MAX_CHART_ROWS} of ${allChartRows.length})` : ''}
          </p>
          <ResponsiveContainer width="100%" height={chartRows.length * 52 + 16}>
            <BarChart
              data={chartRows}
              layout="vertical"
              margin={{ top: 0, right: 60, left: 8, bottom: 0 }}
              barCategoryGap="30%"
            >
              <CartesianGrid horizontal={false} stroke="#f3f4f6" strokeDasharray="4 4" />
              <XAxis
                type="number"
                axisLine={false}
                tickLine={false}
                tick={{ fontSize: 12, fill: '#9ca3af' }}
                tickFormatter={v => Number(v).toLocaleString()}
              />
              <YAxis
                type="category"
                dataKey="name"
                axisLine={false}
                tickLine={false}
                tick={{ fontSize: 13, fill: '#374151', fontWeight: 500 }}
                width={90}
              />
              <Tooltip content={<CustomTooltip />} cursor={{ fill: '#f0f7ff' }} />
              <Bar dataKey="value" radius={[0, 6, 6, 0]} maxBarSize={32}>
                {chartRows.map((_, i) => (
                  <Cell
                    key={i}
                    fill={i === 0 ? '#2563eb' : i === 1 ? '#3b82f6' : '#60a5fa'}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

    </div>
  )
}
