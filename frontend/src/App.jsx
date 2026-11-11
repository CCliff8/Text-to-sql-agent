import { useEffect, useRef, useState } from 'react'
import AnswerCard from './components/AnswerCard'
import TracePanel from './components/TracePanel'
import { SqlBlock } from './lib/sql'
import { askStream, fetchSuggestions } from './lib/api'
import { formatCost } from './lib/format'

const MAX_HISTORY = 5

function describeStep(step) {
  let data = {}
  try { data = JSON.parse(step.result) } catch { /* keep empty */ }
  if (step.tool === 'run_sql') {
    if (data.error) return 'A query failed, fixing it…'
    return `Ran a query (${data.row_count ?? 0}${data.truncated ? '+' : ''} rows)`
  }
  if (step.tool === 'sample_table') return `Looked at sample rows from ${step.input?.table_name ?? 'a table'}`
  if (step.tool === 'get_schema') return 'Checked the database schema'
  return step.tool
}

const toggleClass =
  'text-[13px] text-gray-600 border border-gray-200 hover:border-blue-500 hover:text-blue-600 bg-white rounded-lg px-4 py-1.5 transition-colors cursor-pointer'

export default function App() {
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [liveSteps, setLiveSteps] = useState([])
  const [result, setResult] = useState(null)
  const [asked, setAsked] = useState('')
  const [error, setError] = useState(null)
  const [showSQL, setShowSQL] = useState(false)
  const [showTrace, setShowTrace] = useState(false)
  const [history, setHistory] = useState([])
  const [suggestions, setSuggestions] = useState([])
  const inputRef = useRef(null)
  const abortRef = useRef(null)

  useEffect(() => {
    fetchSuggestions().then(setSuggestions)
    return () => abortRef.current?.abort()
  }, [])

  async function ask(question, { fresh = false } = {}) {
    const text = question.trim()
    if (!text) return

    abortRef.current?.abort() // a newer question supersedes any in flight
    const controller = new AbortController()
    abortRef.current = controller

    const priorTurns = fresh ? [] : history
    if (fresh) setHistory([])

    setLoading(true)
    setLiveSteps([])
    setResult(null)
    setError(null)
    setShowSQL(false)
    setShowTrace(false)
    setAsked(text)

    try {
      const res = await askStream(text, priorTurns, {
        signal: controller.signal,
        onStep: step => setLiveSteps(s => [...s, describeStep(step)]),
      })
      if (controller.signal.aborted) return
      setResult(res)
      if (res.answer) {
        setHistory([...priorTurns, { question: text, answer: res.answer }].slice(-MAX_HISTORY))
        setQuery('')
      }
    } catch (e) {
      if (e.name === 'AbortError') return
      setError(e.message)
    } finally {
      if (abortRef.current === controller) setLoading(false)
    }
  }

  function handleSubmit(e) {
    e.preventDefault()
    ask(query)
  }

  function handlePill(q) {
    setQuery(q)
    ask(q, { fresh: true })
    inputRef.current?.focus()
  }

  function newConversation() {
    abortRef.current?.abort()
    setHistory([])
    setResult(null)
    setError(null)
    setLoading(false)
    setAsked('')
    setQuery('')
    inputRef.current?.focus()
  }

  const failed = result && !result.answer
  const showResult = result && !loading

  return (
    <div className="min-h-screen bg-[#f0f2f5]">
      <div className="mx-auto max-w-2xl px-6 pb-24">

        {/* Hero */}
        <header className="pt-20 pb-10 text-center">
          <h1 className="text-[42px] font-extrabold tracking-tight text-gray-900 leading-tight mb-3">
            Ask your data a question
          </h1>
          <p className="text-gray-500 text-base">
            Type it in plain English. You&apos;ll get an answer, not a query.
          </p>
        </header>

        {/* Search bar */}
        <form
          role="search"
          onSubmit={handleSubmit}
          className="flex items-center gap-2 bg-white border border-gray-200 rounded-2xl shadow-sm px-4 py-2 focus-within:border-blue-500 focus-within:ring-2 focus-within:ring-blue-100 transition-all"
        >
          <input
            ref={inputRef}
            type="text"
            aria-label="Your question"
            value={query}
            maxLength={500}
            onChange={e => setQuery(e.target.value)}
            placeholder={history.length ? 'Ask a follow-up…' : 'e.g. What are the top 3 nations by number of customers?'}
            className="flex-1 bg-transparent text-gray-900 text-[15px] placeholder-gray-400 outline-none py-1"
          />
          <button
            type="submit"
            disabled={loading || !query.trim()}
            className="bg-blue-600 hover:bg-blue-700 disabled:opacity-60 disabled:cursor-not-allowed text-white font-semibold text-[15px] rounded-xl px-6 py-2.5 transition-colors cursor-pointer shrink-0"
          >
            {loading ? 'Asking…' : 'Ask'}
          </button>
        </form>

        {/* Suggestion pills / conversation state */}
        {history.length === 0 ? (
          <div className="flex gap-3 mt-4 justify-center flex-wrap">
            {suggestions.map(({ label, q }) => (
              <button
                key={label}
                type="button"
                onClick={() => handlePill(q)}
                className="bg-white border border-gray-300 hover:border-blue-500 hover:text-blue-600 text-gray-600 text-[13px] rounded-full px-4 py-1.5 transition-colors cursor-pointer whitespace-nowrap"
              >
                {label}
              </button>
            ))}
          </div>
        ) : (
          <p className="mt-4 text-center text-[12.5px] text-gray-500">
            Follow-up mode · {history.length} earlier question{history.length !== 1 ? 's' : ''} in context ·{' '}
            <button type="button" onClick={newConversation} className="text-blue-600 hover:underline cursor-pointer">
              Start over
            </button>
          </p>
        )}

        {/* Loading state with live progress */}
        {loading && (
          <div
            role="status"
            aria-live="polite"
            className="mt-6 bg-white border border-gray-200 rounded-2xl shadow-sm p-8 flex flex-col items-center gap-4"
          >
            <div className="w-8 h-8 border-[3px] border-blue-600 border-t-transparent rounded-full animate-spin" aria-hidden="true" />
            <p className="text-gray-500 text-sm font-medium">
              {liveSteps.length ? liveSteps[liveSteps.length - 1] : 'Analysing your question and querying the database…'}
            </p>
            {liveSteps.length > 1 && (
              <ol className="text-[12px] text-gray-400 space-y-0.5 text-center">
                {liveSteps.slice(0, -1).map((s, i) => <li key={i}>✓ {s}</li>)}
              </ol>
            )}
          </div>
        )}

        {/* Error */}
        {error && (
          <div role="alert" className="mt-6 bg-red-50 border border-red-200 rounded-2xl p-5 text-red-700 text-sm">
            {error}
          </div>
        )}

        {/* Result */}
        {showResult && (
          <>
            {failed ? (
              <div role="alert" className="mt-6 bg-red-50 border border-red-200 rounded-2xl p-5 text-red-700 text-sm">
                {result.error || 'No answer was produced.'}
              </div>
            ) : (
              <AnswerCard result={result} question={asked} />
            )}

            {/* Action buttons */}
            <div className="flex gap-2 mt-3">
              {result.sql && !failed && (
                <button
                  type="button"
                  onClick={() => setShowSQL(v => !v)}
                  aria-expanded={showSQL}
                  aria-controls="sql-panel"
                  className={toggleClass}
                >
                  {showSQL ? '↑ Hide SQL' : '› Show SQL'}
                </button>
              )}
              {result.steps?.length > 0 && (
                <button
                  type="button"
                  onClick={() => setShowTrace(v => !v)}
                  aria-expanded={showTrace}
                  aria-controls="trace-panel"
                  className={toggleClass}
                >
                  {showTrace ? '↑ Hide reasoning' : '› Show how I got this'}
                </button>
              )}
            </div>

            {showSQL && result.sql && <SqlBlock id="sql-panel" sql={result.sql} />}
            {showTrace && <TracePanel id="trace-panel" steps={result.steps || []} sql={result.sql} />}

            {/* Meta */}
            <p className="mt-4 text-center text-[11.5px] text-gray-400">
              {result.model_label || result.model}
              <span className="mx-1.5 text-gray-300">·</span>
              {result.iterations} iteration{result.iterations !== 1 ? 's' : ''}
              <span className="mx-1.5 text-gray-300">·</span>
              {result.routed_to}
              {formatCost(result.cost_usd) && (
                <>
                  <span className="mx-1.5 text-gray-300">·</span>
                  {formatCost(result.cost_usd)}
                </>
              )}
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
