# Text-to-SQL Analyst Agent

Ask business questions in plain English. The agent inspects the schema, writes SQL, runs it in a sandbox, fixes its own errors, and answers with a table, a chart and the SQL behind it.

**Stack:** Python · FastAPI (SSE streaming) · DuckDB · Anthropic Claude (Haiku 4.5 + Sonnet 4.6) · React 19 · Vite · Tailwind v4 · Recharts

---

## Features

- **Cost-aware routing:** a heuristic router sends simple questions to Haiku and complex ones to Sonnet. If Haiku has not finished within 4 turns, the same conversation escalates to Sonnet.
- **Self-correcting loop:** the schema is already in the prompt (and prompt-cached). The agent calls `run_sql` or `sample_table` and retries failed queries, up to 5 errors.
- **Sandboxed SQL:** one `SELECT`/`EXPLAIN` per query, read-only connection, external access disabled, 15 s timeout, 100-row cap.
- **Answer verification:** numbers in the answer are cross-checked against the query result, and the UI warns when any can't be matched.
- **Live UI:** streamed progress, follow-up questions ("and for 1996?"), results table, bar chart, CSV export, copyable SQL, and a "how I got this" trace.
- **Cost tracking:** every response includes token usage and an estimated `cost_usd`.
- **Evals and tests:** a 40-case benchmark with gold SQL, plus 144 pytest tests and CI.

## How it works

```
question ──► router.py ──► agent.py (tool loop) ──► tools.py ──► tpch.duckdb
             Haiku / Sonnet   run_sql, sample_table   sandbox       TPC-H, 8 tables
                              │                                     
                              └─► verify.py: check numbers ──► answer + table + chart
```

| File | Role |
|---|---|
| `api.py` | FastAPI: `POST /ask`, `POST /ask/stream` (SSE), `GET /config` |
| `agent.py` | Tool loop, routing, escalation, caching, usage and cost |
| `router.py` | Complexity classifier |
| `tools.py` | Tool definitions and sandboxed SQL execution |
| `verify.py` | Answer-vs-result number check |
| `config.py` | Models, limits, pricing, suggestions (single source of truth) |
| `db_setup.py` | Loads TPC-H (scale 0.1) into DuckDB |
| `evals.py`, `compare_runs.py` | Benchmark runner and before/after comparison |
| `frontend/` | React app (`components/`, `lib/` for SSE client, formatting, SQL highlighter) |

## Quick start

Requires Python 3.9+, Node 18+ and an [Anthropic API key](https://console.anthropic.com).

```bash
git clone https://github.com/CCliff8/Text-to-sql-agent.git
cd Text-to-sql-agent

python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # then set ANTHROPIC_API_KEY=sk-ant-...
python db_setup.py            # one-off, ~27 MB, needs network for DuckDB's tpch extension

cd frontend && npm install && cd ..
```

Run two terminals:

```bash
python3 -m uvicorn api:app --port 8000 --reload     # backend (repo root)
cd frontend && npm run dev                          # frontend
```

Open <http://localhost:5173>.

## Configuration

Defaults live in `config.py`. Override them in `.env`:

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | none | Required |
| `HAIKU_MODEL` / `SONNET_MODEL` | Haiku 4.5 / Sonnet 4.6 | Swap model versions |
| `QUERY_TIMEOUT_S` | `15` | Per-query timeout |
| `DUCKDB_MEMORY_LIMIT` / `DUCKDB_THREADS` | `1GB` / `2` | DuckDB resources |
| `RATE_LIMIT_PER_MIN` | `20` | Per-IP limit, `0` disables |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated |

## Security

- SQL runs on a read-only DuckDB connection with external access disabled (no `read_csv`, `glob` or HTTP) and a locked configuration.
- The API rate-limits per IP, caps question length (500 chars) and never returns internal error text.
- **There is no authentication.** Every request spends API credits, so keep it local or put it behind an authenticating reverse proxy.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```

The suite covers the sandbox, router, verifier, agent loop (with a scripted fake client), API, and eval harness. One test runs every gold query in `test_cases.json` against your local `tpch.duckdb`. CI runs pytest on Python 3.9 and 3.12, plus frontend lint and build.

## Evaluations

40 cases across categories. A case passes only if the **answer text** matches **and** at least one query the agent ran returns the same rows as the gold SQL, so a lucky number doesn't count.

```bash
python evals.py                    # full suite, 4 workers, temperature 0
python evals.py q001 q002          # specific cases
python evals.py --runs 3           # repeat to find flaky cases
python evals.py --workers 1 -v     # sequential, verbose
python compare_runs.py eval_results_before.json eval_results_after.json
```

Reports break accuracy down by category and router decision (Haiku vs Sonnet) and include real cost per question. Run it once to measure your own numbers, since prices in `config.py` are estimates.

## Troubleshooting

| Symptom | Fix |
|---|---|
| "The database has not been set up yet" | `python db_setup.py` |
| "API key is missing or invalid" | Check `ANTHROPIC_API_KEY` in `.env`, restart backend |
| Frontend network errors | Backend must be running on port 8000 |
| Queries time out | Raise `QUERY_TIMEOUT_S` or ask a narrower question |

## License

See [LICENSE](LICENSE).
