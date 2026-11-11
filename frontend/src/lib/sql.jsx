// Tiny dependency-free SQL highlighter + copy button.
import { useState } from 'react'

const TOKEN = new RegExp(
  [
    '(?<comment>--[^\\n]*|/\\*[\\s\\S]*?\\*/)',
    "(?<string>'(?:[^']|'')*')",
    '(?<number>\\b\\d+(?:\\.\\d+)?\\b)',
    '(?<keyword>\\b(?:SELECT|DISTINCT|FROM|WHERE|GROUP\\s+BY|ORDER\\s+BY|HAVING|LIMIT|OFFSET|JOIN|LEFT|RIGHT|INNER|OUTER|CROSS|FULL|ON|USING|AS|AND|OR|NOT|IN|IS|NULL|LIKE|ILIKE|BETWEEN|CASE|WHEN|THEN|ELSE|END|WITH|UNION|ALL|EXISTS|DESC|ASC|FILTER|OVER|PARTITION\\s+BY|INTERVAL|DATE|CAST|EXPLAIN)\\b)',
    '(?<fn>\\b[A-Za-z_][A-Za-z0-9_]*(?=\\s*\\())',
  ].join('|'),
  'gi',
)

const CLASS = {
  comment: 'text-gray-400 italic',
  string: 'text-emerald-700',
  number: 'text-amber-700',
  keyword: 'text-blue-700 font-semibold',
  fn: 'text-purple-700',
}

function highlight(sql) {
  const out = []
  let last = 0
  for (const m of sql.matchAll(TOKEN)) {
    if (m.index > last) out.push(sql.slice(last, m.index))
    const kind = Object.keys(m.groups).find(k => m.groups[k] !== undefined)
    out.push(<span key={m.index} className={CLASS[kind]}>{m[0]}</span>)
    last = m.index + m[0].length
  }
  if (last < sql.length) out.push(sql.slice(last))
  return out
}

export function SqlCode({ sql, className = '' }) {
  return <code className={className}>{highlight(sql)}</code>
}

export function SqlBlock({ sql, id }) {
  const [copied, setCopied] = useState(false)

  async function copy() {
    try {
      await navigator.clipboard.writeText(sql)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch { /* clipboard unavailable (insecure context): ignore */ }
  }

  return (
    <div id={id} className="relative mt-3 bg-white border border-gray-200 rounded-xl">
      <button
        type="button"
        onClick={copy}
        aria-label="Copy SQL to clipboard"
        className="absolute top-2 right-2 text-[11.5px] text-gray-500 hover:text-blue-600 border border-gray-200 hover:border-blue-400 bg-white rounded-md px-2.5 py-1 transition-colors cursor-pointer"
      >
        {copied ? 'Copied ✓' : 'Copy'}
      </button>
      <pre className="p-4 pr-20 text-[12.5px] text-gray-800 overflow-x-auto leading-relaxed font-mono">
        <SqlCode sql={sql} />
      </pre>
    </div>
  )
}
