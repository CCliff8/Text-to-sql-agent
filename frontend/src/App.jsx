import { useState, useRef } from 'react'
import AnswerCard from './components/AnswerCard'
import TracePanel from './components/TracePanel'

const SUGGESTIONS = [
  { label: 'Top 3 nations by customers', q: 'What are the top 3 nations by number of customers?' },
  { label: 'Revenue by region',          q: 'What is the total revenue by region?' },
  { label: 'Biggest customers',          q: 'Who are the top 5 customers by total order value?' },
]

export default function App() {
  const [query, setQuery]       = useState('')
  const [loading, setLoading]   = useState(false)
  const [result, setResult]     = useState(null)
  const [error, setError]       = useState(null)
  const [showSQL, setShowSQL]   = useState(false)
  const [showTrace, setShowTrace] = useState(false)
  const inputRef = useRef(null)

  async function ask(question) {
    if (!question.trim()) return
    setLoading(true)
    setResult(null)
    setError(null)
    setShowSQL(false)
    setShowTrace(false)
    try {
      const res = await fetch('/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: question.trim() }),
      })
      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || 'Something went wrong.')
      }
      setResult(await res.json())
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  function handleSubmit(e) {
    e.preventDefault()
    ask(query)
  }

  function handlePill(q) {
    setQuery(q)
    ask(q)
    inputRef.current?.focus()
  }

  return (
    <div className="min-h-screen bg-[#f0f2f5]">
      <div className="mx-auto max-w-2xl px-6 pb-24">

        {/* Hero */}
        <div className="pt-20 pb-10 text-center">
          <h1 className="text-[42px] font-extrabold tracking-tight text-gray-900 leading-tight mb-3">
            Ask your data a question
          </h1>
        </div>

        {/* Search bar */}
        <form onSubmit={handleSubmit} className="flex items-center gap-2 bg-white border border-gray-200 rounded-2xl shadow-sm px-4 py-2 focus-within:border-blue-500 focus-within:ring-2 focus-within:ring-blue-100 transition-all">
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="e.g. What are the top 3 nations by number of customers?"
            className="flex-1 bg-transparent text-gray-900 text-[15px] placeholder-gray-400 outline-none py-1"
          />
          <button
            type="submit"
            disabled={loading}
            className="bg-blue-600 hover:bg-blue-700 disabled:opacity-60 text-white font-semibold text-[15px] rounded-xl px-6 py-2.5 transition-colors cursor-pointer shrink-0"
          >
            {loading ? 'Asking…' : 'Ask'}
          </button>
        </form>

        {/* Suggestion pills */}
        <div className="flex gap-3 mt-4 justify-center flex-wrap">
          {SUGGESTIONS.map(({ label, q }) => (
            <button
              key={label}
              onClick={() => handlePill(q)}
              className="bg-white border border-gray-300 hover:border-blue-500 hover:text-blue-600 text-gray-600 text-[13px] rounded-full px-4 py-1.5 transition-colors cursor-pointer whitespace-nowrap"
            >
              {label}
            </button>
          ))}
        </div>

        {/* Loading state */}
        {loading && (
          <div className="mt-6 bg-white border border-gray-200 rounded-2xl shadow-sm p-8 flex flex-col items-center gap-4">
            <div className="w-8 h-8 border-[3px] border-blue-600 border-t-transparent rounded-full animate-spin" />
            <p className="text-gray-500 text-sm font-medium">
              Analysing your question and querying the database…
            </p>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="mt-6 bg-red-50 border border-red-200 rounded-2xl p-5 text-red-700 text-sm">
            {error}
          </div>
        )}

        {/* Result */}
        {result && !loading && (
          <>
            <AnswerCard result={result} />

            {/* Action buttons */}
            <div className="flex gap-2 mt-3">
              <button
                onClick={() => setShowSQL(v => !v)}
                className="text-[13px] text-gray-600 border border-gray-200 hover:border-blue-500 hover:text-blue-600 bg-white rounded-lg px-4 py-1.5 transition-colors cursor-pointer"
              >
                {showSQL ? '↑ Hide SQL' : '› Show SQL'}
              </button>
              <button
                onClick={() => setShowTrace(v => !v)}
                className="text-[13px] text-gray-600 border border-gray-200 hover:border-blue-500 hover:text-blue-600 bg-white rounded-lg px-4 py-1.5 transition-colors cursor-pointer"
              >
                {showTrace ? '↑ Hide reasoning' : '› Show how I got this'}
              </button>
            </div>

            {/* SQL panel */}
            {showSQL && result.sql && (
              <pre className="mt-3 bg-white border border-gray-200 rounded-xl p-4 text-[12.5px] text-gray-800 overflow-x-auto leading-relaxed font-mono">
                {result.sql}
              </pre>
            )}

            {/* Trace panel */}
            {showTrace && (
              <TracePanel steps={result.steps || []} sql={result.sql} />
            )}

            {/* Meta */}
            <p className="mt-4 text-center text-[11.5px] text-gray-400">
              {result.model === 'claude-haiku-4-5-20251001' ? 'Haiku 4.5' : 'Sonnet 4.6'}
              <span className="mx-1.5 text-gray-300">·</span>
              {result.iterations} iteration{result.iterations !== 1 ? 's' : ''}
              <span className="mx-1.5 text-gray-300">·</span>
              {result.routed_to}
            </p>
          </>
        )}

        {/* Footer */}
        <p className="mt-16 text-center text-[12px] text-gray-400">
          Read-only access to the TPC-H sample database
        </p>

      </div>
    </div>
  )
}
