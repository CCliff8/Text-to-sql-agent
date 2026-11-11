// Small client for the FastAPI backend.

async function errorDetail(res) {
  try {
    const body = await res.json()
    if (typeof body.detail === 'string') return body.detail
    if (Array.isArray(body.detail)) return 'That question could not be processed (it may be too long).'
  } catch { /* not JSON */ }
  return `Request failed (${res.status}).`
}

export async function fetchSuggestions() {
  try {
    const res = await fetch('/config')
    if (!res.ok) return []
    return (await res.json()).suggestions ?? []
  } catch {
    return []
  }
}

function parseEvent(block) {
  let event = 'message'
  let data = ''
  for (const line of block.split('\n')) {
    if (line.startsWith('event: ')) event = line.slice(7)
    else if (line.startsWith('data: ')) data += line.slice(6)
  }
  return data ? { event, data: JSON.parse(data) } : null
}

/**
 * Ask a question and stream progress. `onStep` is called for every tool step the
 * agent completes; the promise resolves with the final result object.
 */
export async function askStream(question, history, { signal, onStep } = {}) {
  const res = await fetch('/ask/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, history }),
    signal,
  })
  if (!res.ok) throw new Error(await errorDetail(res))

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let result = null

  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let sep
    while ((sep = buffer.indexOf('\n\n')) !== -1) {
      const parsed = parseEvent(buffer.slice(0, sep))
      buffer = buffer.slice(sep + 2)
      if (!parsed) continue
      if (parsed.event === 'step') onStep?.(parsed.data)
      else if (parsed.event === 'result') result = parsed.data
      else if (parsed.event === 'error') throw new Error(parsed.data.detail || 'Something went wrong.')
    }
  }

  if (!result) throw new Error('The connection closed before an answer arrived.')
  return result
}
