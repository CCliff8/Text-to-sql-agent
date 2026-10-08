# Text-to-SQL Analyst Agent

An AI agent that answers business questions in plain English by autonomously inspecting a database schema, writing SQL, executing it, and self-correcting on errors.

Built with a Python/FastAPI backend and a React frontend.

---

## What it does

1. You type a question: *"Who are the top 5 customers by total order value?"*
2. A **router** classifies the complexity and picks the cheapest model that can handle it
3. The **agent** calls tools in a loop — inspects the schema, writes SQL, runs it, self-corrects if it fails
4. You get a plain-English answer with an interactive bar chart
5. You can expand **"Show SQL"** and **"Show how I got this"** to see every step the agent took

---

## Architecture

```
User question
     │
     ▼
┌─────────────┐
│  router.py  │  Classifies complexity
│             │  Simple  → Haiku 4.5   (fast, cheap)
└──────┬──────┘  Complex → Sonnet 4.6  (stronger reasoning)
       │
       ▼
┌─────────────────────────────────────────┐
│              agent.py                   │
│                                         │
│  Proactive routing: right model from    │
│  turn 1, no wasted calls                │
│                                         │
│  Reactive fallback: if Haiku struggles  │
│  after 3 turns → hands off to Sonnet,   │
│  same conversation, no context lost     │
│                                         │
│  Tool loop:                             │
│    1. get_schema  → understand the DB   │
│    2. sample_table → check data formats │
│    3. run_sql     → execute query       │
│    4. self-correct on SQL errors        │
│    5. return plain-English answer       │
└──────────────────┬──────────────────────┘
                   │
                   ▼
         ┌──────────────────┐
         │    tools.py      │
         │  Read-only       │
         │  DuckDB (SQL)    │
         │  SELECT only     │
         └────────┬─────────┘
                  │
                  ▼
         ┌──────────────────┐
         │   tpch.duckdb    │
         │  TPC-H benchmark │
         │  8 tables        │
         │  600K+ rows      │
         └──────────────────┘
```

---

## Tech stack

| Layer | Technology |
|---|---|
| LLM API | Anthropic Claude (Haiku 4.5 + Sonnet 4.6) |
| Backend | FastAPI + Uvicorn |
| Database | DuckDB (embedded, zero config) |
| Dataset | TPC-H benchmark (scale 0.1) |
| Frontend | React 19 + Vite |
| Styling | Tailwind CSS v4 |
| Charts | Recharts |

---

## Prerequisites

- **Python 3.9+**
- **Node.js 18+** and npm
- An **Anthropic API key** — get one at [console.anthropic.com](https://console.anthropic.com)

---

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/CCliff8/Text_to_sql_agent.git
cd Text_to_sql_agent
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Add your API key

```bash
cp .env.example .env
```

Open `.env` and replace the placeholder with your real key:

```
ANTHROPIC_API_KEY=sk-ant-...
```

### 4. Load the database

```bash
python db_setup.py
```

Downloads and loads the TPC-H benchmark into a local `tpch.duckdb` file (~27 MB). Only needs to run once.

### 5. Install frontend dependencies

```bash
cd frontend
npm install
```

---

## Running the app

You need two terminals.

**Terminal 1 — Python backend:**

```bash
cd text_to_sql
python3 -m uvicorn api:app --port 8000 --reload
```

**Terminal 2 — React frontend:**

```bash
cd text_to_sql/frontend
npm run dev
```

Open **http://localhost:5173** in your browser.

---

## Project structure

```
text_to_sql/
├── api.py              # FastAPI server — exposes POST /ask
├── agent.py            # Agentic loop with two-layer model routing
├── router.py           # Heuristic complexity classifier
├── tools.py            # Tool definitions + safe SQL execution
├── evals.py            # Evaluation framework (40 test cases)
├── compare_runs.py     # Compare two eval runs (before/after)
├── db_setup.py         # DuckDB + TPC-H data loader
├── test_cases.json     # 40 calibrated Q&A test cases
├── requirements.txt    # Python dependencies
├── .env.example        # Template for environment variables
└── frontend/           # React app
    ├── src/
    │   ├── App.jsx           # Main page + state management
    │   └── components/
    │       ├── AnswerCard.jsx # Answer text + Recharts bar chart
    │       └── TracePanel.jsx # Step-by-step agent trace
    ├── vite.config.js        # Vite + Tailwind + API proxy
    └── package.json
```


## Running evaluations

The project includes a 40-case benchmark with verified expected answers.

```bash
# Full suite (~$0.40, ~10 min)
python evals.py

# Specific cases only
python evals.py q001 q002 q003

# Compare two runs
python compare_runs.py eval_results_before.json eval_results_after.json
```

---

## Cost guide

| Run | Cases | Estimated cost |
|---|---|---|
| Quick smoke test | 5 | ~$0.02 |
| Full eval suite | 40 | ~$0.40 |

The two-layer router keeps costs low — roughly half of queries go to Haiku, which is significantly cheaper than Sonnet.

---
