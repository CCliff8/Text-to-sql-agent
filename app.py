from dotenv import load_dotenv
load_dotenv()

import html as _html
import json
import re
import time
import streamlit as st

from agent import run_agent, MODEL_PRIMARY, MODEL_FALLBACK
from tools import execute_tool

st.set_page_config(page_title="Analyst", layout="centered", initial_sidebar_state="collapsed")

st.markdown("""
<style>
/* ── Force light mode ───────────────────────────────────────────── */
:root { color-scheme: light only !important; }
html, body,
[data-testid="stApp"],
[data-testid="stAppViewContainer"],
[data-testid="stMain"],
section[data-testid="stMain"],
section[data-testid="stMain"] > div,
[data-testid="block-container"] {
    background: #f0f2f5 !important;
}

/* ── Hide chrome ────────────────────────────────────────────────── */
#MainMenu, footer, header,
[data-testid="stToolbar"], [data-testid="stHeader"],
[data-testid="stDecoration"], [data-testid="stStatusWidget"],
.stDeployButton { display: none !important; }

/* ── Kill hover ghost overlays ──────────────────────────────────── */
[data-testid="column"]:hover,
[data-testid="column"] > div:hover,
[data-testid="stVerticalBlockBorderWrapper"]:hover,
div[class*="element-container"]:hover {
    background: transparent !important;
    border: none !important;
    outline: none !important;
}

/* ── Layout ─────────────────────────────────────────────────────── */
[data-testid="block-container"] {
    max-width: 720px !important;
    padding: 0 24px 80px !important;
}
.block-container { padding-top: 0 !important; }

/* ── Hero ───────────────────────────────────────────────────────── */
.hero { padding: 64px 0 32px; text-align: center; }
.hero h1 {
    color: #111827;
    font-size: 42px;
    font-weight: 800;
    letter-spacing: -0.025em;
    line-height: 1.15;
    margin: 0 0 12px;
}
.hero p { color: #6b7280; font-size: 16px; margin: 0; }

/* ── Search form ────────────────────────────────────────────────── */
div[data-testid="stForm"] {
    background: #ffffff !important;
    border: 1.5px solid #e5e7eb !important;
    border-radius: 16px !important;
    box-shadow: 0 1px 4px rgba(0,0,0,0.07) !important;
    padding: 6px 6px 6px 10px !important;
    transition: border-color .15s, box-shadow .15s !important;
}
div[data-testid="stForm"]:focus-within {
    border-color: #2563eb !important;
    box-shadow: 0 0 0 3px rgba(37,99,235,.1), 0 1px 4px rgba(0,0,0,0.07) !important;
}

/* ── Ask button ─────────────────────────────────────────────────── */
div[data-testid="stForm"] button[kind="primaryFormSubmit"] {
    background: #2563eb !important;
    border: none !important;
    border-radius: 12px !important;
    color: #ffffff !important;
    font-size: 15px !important;
    font-weight: 600 !important;
    height: 46px !important;
    padding: 0 28px !important;
    box-shadow: 0 1px 3px rgba(37,99,235,.25) !important;
}
div[data-testid="stForm"] button[kind="primaryFormSubmit"]:hover {
    background: #1d4ed8 !important;
}

/* ── All secondary buttons: white bg, gray border, dark text ────── */
button[data-testid="baseButton-secondary"],
[data-testid="stBaseButton-secondary"] {
    background: #ffffff !important;
    background-color: #ffffff !important;
    border: 1.5px solid #e5e7eb !important;
    border-radius: 8px !important;
    color: #374151 !important;
    font-size: 13px !important;
    font-weight: 400 !important;
}
button[data-testid="baseButton-secondary"]:hover,
[data-testid="stBaseButton-secondary"]:hover {
    background: #ffffff !important;
    background-color: #ffffff !important;
    border-color: #2563eb !important;
    color: #2563eb !important;
}

/* ── Suggestion pills ───────────────────────────────────────────── */
div.pill button,
div.pill [data-testid="baseButton-secondary"] {
    background: #ffffff !important;
    background-color: #ffffff !important;
    border: 1.5px solid #d1d5db !important;
    border-radius: 999px !important;
    color: #374151 !important;
    font-size: 13.5px !important;
    font-weight: 400 !important;
    padding: 6px 18px !important;
}
div.pill button:hover,
div.pill [data-testid="baseButton-secondary"]:hover {
    background: #ffffff !important;
    border-color: #2563eb !important;
    color: #2563eb !important;
}

/* ── Answer card ────────────────────────────────────────────────── */
.answer-card {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 16px;
    box-shadow: 0 1px 6px rgba(0,0,0,0.06);
    margin-top: 24px;
    overflow: hidden;
}
.answer-top { padding: 28px 30px 24px; }
.answer-eyebrow {
    color: #9ca3af;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: .09em;
    margin-bottom: 10px;
    text-transform: uppercase;
}
.answer-body {
    color: #111827;
    font-size: 21px;
    font-weight: 700;
    line-height: 1.5;
}

/* ── Bar chart ──────────────────────────────────────────────────── */
.chart-section { border-top: 1px solid #f3f4f6; padding: 20px 30px 26px; }
.chart-head {
    color: #9ca3af;
    display: flex;
    font-size: 12px;
    justify-content: space-between;
    margin-bottom: 16px;
}
.chart-row { align-items: center; display: flex; gap: 16px; margin-bottom: 13px; }
.chart-name { color: #374151; font-size: 14px; min-width: 90px; }
.chart-track { background: #f3f4f6; border-radius: 4px; flex: 1; height: 7px; overflow: hidden; }
.chart-fill  { background: #2563eb; border-radius: 4px; height: 100%; }
.chart-num   { color: #111827; font-size: 14px; font-weight: 600; min-width: 50px; text-align: right; }

/* ── Trace card ─────────────────────────────────────────────────── */
.trace-card {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 14px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.05);
    margin-top: 10px;
    overflow: hidden;
}
.trace-hdr {
    align-items: center;
    background: #f9fafb;
    border-bottom: 1px solid #f3f4f6;
    display: flex;
    gap: 8px;
    padding: 12px 20px;
}
.trace-title { color: #111827; font-size: 13.5px; font-weight: 600; }
.trace-badge {
    background: #f3f4f6;
    border-radius: 999px;
    color: #6b7280;
    font-size: 11px;
    font-weight: 600;
    padding: 2px 8px;
}
.trace-step { border-bottom: 1px solid #f9fafb; padding: 14px 20px; }
.trace-step:last-child { border-bottom: none; }
.step-row { align-items: flex-start; display: flex; gap: 12px; }
.step-num {
    background: #eff6ff;
    border: 1px solid #bfdbfe;
    border-radius: 50%;
    color: #2563eb;
    flex-shrink: 0;
    font-size: 11px;
    font-weight: 700;
    height: 22px;
    line-height: 22px;
    margin-top: 1px;
    min-width: 22px;
    text-align: center;
}
.step-content { flex: 1; }
.step-label { color: #111827; font-size: 13px; font-weight: 500; margin-bottom: 6px; }
.step-label code {
    background: #f3f4f6;
    border-radius: 4px;
    color: #374151;
    font-size: 12px;
    padding: 1px 6px;
}
.chips { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 6px; }
.chip {
    background: #f9fafb;
    border: 1px solid #e5e7eb;
    border-radius: 6px;
    color: #374151;
    font-family: monospace;
    font-size: 12px;
    padding: 2px 8px;
}
.sql-block {
    background: #f9fafb;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    color: #111827;
    font-family: "SF Mono", "Fira Code", monospace;
    font-size: 12.5px;
    line-height: 1.65;
    margin-top: 7px;
    overflow-x: auto;
    padding: 12px 16px;
    white-space: pre;
}
.sql-error { background: #fef2f2; border-color: #fca5a5; color: #991b1b; }
.result-note { color: #9ca3af; font-size: 12px; margin-top: 5px; }
.result-note strong { color: #6b7280; }
.tables-foot {
    background: #f9fafb;
    border-top: 1px solid #f3f4f6;
    padding: 12px 20px;
}
.tables-label {
    color: #9ca3af;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: .07em;
    margin-bottom: 7px;
    text-transform: uppercase;
}

/* ── Meta & footer ──────────────────────────────────────────────── */
.meta { color: #9ca3af; font-size: 12px; margin-top: 14px; text-align: center; }
.meta-dot { color: #d1d5db; margin: 0 5px; }
.footer { color: #9ca3af; font-size: 12px; margin-top: 60px; text-align: center; }

/* ── Spinner ────────────────────────────────────────────────────── */
[data-testid="stSpinner"] {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 12px;
    margin-top: 24px;
    padding: 20px 24px !important;
    text-align: center;
}
[data-testid="stSpinner"] p {
    color: #374151 !important;
    font-size: 14px !important;
    font-weight: 500 !important;
    margin: 0 !important;
}

/* ── Error ──────────────────────────────────────────────────────── */
.err-box {
    background: #fef2f2;
    border: 1px solid #fca5a5;
    border-radius: 12px;
    color: #991b1b;
    font-size: 14px;
    margin-top: 20px;
    padding: 16px 20px;
}
</style>
""", unsafe_allow_html=True)

# ── Session state ─────────────────────────────────────────────────────────────

for _k, _v in {
    "result": None,
    "chart_data": None,
    "search_query": "",
    "show_sql": False,
    "show_trace": False,
}.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

# ── Helpers ───────────────────────────────────────────────────────────────────

def _try_chart(sql):
    if not sql:
        return None
    try:
        raw = json.loads(execute_tool("run_sql", {"query": sql}))
        if "error" in raw or not raw.get("rows"):
            return None
        cols, rows = raw["columns"], raw["rows"]
        if len(cols) != 2 or len(rows) < 2:
            return None
        float(str(rows[0][cols[1]]).replace(",", "").replace("$", ""))
        return cols, rows
    except Exception:
        return None


def _bar_chart_html(cols, rows):
    lc, vc = cols
    try:
        vals = [float(str(r[vc]).replace(",", "").replace("$", "")) for r in rows]
    except Exception:
        return ""
    mx = max(vals) or 1
    bars = "".join(
        f'<div class="chart-row">'
        f'<span class="chart-name">{_html.escape(str(r[lc]))}</span>'
        f'<div class="chart-track"><div class="chart-fill" style="width:{v/mx*100:.1f}%"></div></div>'
        f'<span class="chart-num">{"%.0f" % v if v == int(v) else "%.2f" % v}</span>'
        f'</div>'
        for r, v in zip(rows, vals)
    )
    return (
        f'<div class="chart-section">'
        f'<div class="chart-head"><span>{_html.escape(lc)}</span><span>{_html.escape(vc)}</span></div>'
        f'{bars}</div>'
    )


def _extract_tables(sql):
    if not sql:
        return []
    found = re.findall(r"(?:FROM|JOIN)\s+([a-zA-Z_]\w*)", sql, re.IGNORECASE)
    seen, out = set(), []
    for t in found:
        tl = t.lower()
        if tl not in seen:
            seen.add(tl)
            out.append(tl)
    return out


def _render_trace(steps, final_sql):
    if not steps:
        return

    step_html = ""
    for i, s in enumerate(steps, 1):
        tool, inp, res = s["tool"], s["input"], s.get("result", "")

        if tool == "get_schema":
            try:
                tables = list(json.loads(res).keys())
            except Exception:
                tables = []
            chips = "".join(f'<span class="chip">{_html.escape(t)}</span>' for t in tables)
            body = (
                f'<div class="step-label">Schema inspection</div>'
                f'<div class="chips">{chips}</div>'
            )

        elif tool == "sample_table":
            tname = _html.escape(str(inp.get("table_name", "?")))
            try:
                data = json.loads(res)
                cols = data.get("columns", [])
                chips = "".join(f'<span class="chip">{_html.escape(c)}</span>' for c in cols[:10])
                extra = (
                    f'<span style="color:#9ca3af;font-size:11px;margin-left:4px">'
                    f'+{len(cols)-10} more</span>'
                ) if len(cols) > 10 else ""
                note = f'<div class="result-note"><strong>{len(data.get("rows", []))}</strong> sample rows</div>'
            except Exception:
                chips = extra = note = ""
            body = (
                f'<div class="step-label">Sampled table <code>{tname}</code></div>'
                f'<div class="chips">{chips}{extra}</div>{note}'
            )

        elif tool == "run_sql":
            query = _html.escape(inp.get("query", "").strip())
            try:
                data = json.loads(res)
                if "error" in data:
                    note = f'<div class="result-note" style="color:#dc2626">Error: {_html.escape(str(data["error"]))}</div>'
                    cls = "sql-block sql-error"
                else:
                    n = data.get("row_count", len(data.get("rows", [])))
                    trunc = " · truncated to 100" if data.get("truncated") else ""
                    note = f'<div class="result-note"><strong>{n}</strong> rows returned{trunc}</div>'
                    cls = "sql-block"
            except Exception:
                note, cls = "", "sql-block"
            body = (
                f'<div class="step-label">SQL query</div>'
                f'<div class="{cls}">{query}</div>{note}'
            )

        else:
            body = f'<div class="step-label">{_html.escape(tool)}</div>'

        step_html += (
            f'<div class="trace-step">'
            f'<div class="step-row">'
            f'<div class="step-num">{i}</div>'
            f'<div class="step-content">{body}</div>'
            f'</div></div>'
        )

    tables = _extract_tables(final_sql or "")
    tables_html = ""
    if tables:
        chips = "".join(f'<span class="chip">{_html.escape(t)}</span>' for t in tables)
        tables_html = (
            f'<div class="tables-foot">'
            f'<div class="tables-label">Tables used</div>'
            f'<div class="chips">{chips}</div>'
            f'</div>'
        )

    st.markdown(
        f'<div class="trace-card">'
        f'<div class="trace-hdr">'
        f'<span class="trace-title">How I got this</span>'
        f'<span class="trace-badge">{len(steps)} steps</span>'
        f'</div>'
        f'{step_html}{tables_html}'
        f'</div>',
        unsafe_allow_html=True,
    )


# ══════════════════════════════════════════════════════════════════════════════
# PAGE
# ══════════════════════════════════════════════════════════════════════════════

# Hero
st.markdown("""
<div class="hero">
    <h1>Ask your data a question</h1>
    <p>Type it in plain English. You'll get an answer, not a query.</p>
</div>
""", unsafe_allow_html=True)

# Search bar
with st.form("search_form", clear_on_submit=False):
    col_in, col_btn = st.columns([6, 1])
    with col_in:
        question = st.text_input(
            "q",
            value=st.session_state.search_query,
            placeholder="e.g. What are the top 3 nations by number of customers?",
            label_visibility="collapsed",
        )
    with col_btn:
        submitted = st.form_submit_button("Ask")

# Suggestion pills
SUGGESTIONS = [
    ("Top 3 nations by customers", "What are the top 3 nations by number of customers?"),
    ("Revenue by region",          "What is the total revenue by region?"),
    ("Biggest customers",          "Who are the top 5 customers by total order value?"),
]
pill_cols = st.columns(len(SUGGESTIONS))
for i, (label, full_q) in enumerate(SUGGESTIONS):
    with pill_cols[i]:
        st.markdown('<div class="pill">', unsafe_allow_html=True)
        if st.button(label, key=f"pill_{i}"):
            st.session_state.search_query = full_q
            st.session_state.result = None
            st.session_state.chart_data = None
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

# Run agent
if submitted and question.strip():
    st.session_state.search_query = question.strip()
    st.session_state.show_sql = False
    st.session_state.show_trace = False
    with st.spinner("Analysing your question and querying the database…"):
        result = run_agent(question.strip(), verbose=False)
        chart_data = _try_chart(result.get("sql"))
    st.session_state.result = result
    st.session_state.chart_data = chart_data
    st.rerun()

# ── Results ───────────────────────────────────────────────────────────────────

result = st.session_state.result
if result:

    if result.get("error") and not result.get("answer"):
        st.markdown(
            f'<div class="err-box">{_html.escape(result["error"])}</div>',
            unsafe_allow_html=True,
        )

    else:
        # Answer card (pure HTML, no widgets inside)
        chart_html = _bar_chart_html(*st.session_state.chart_data) if st.session_state.chart_data else ""
        st.markdown(
            f'<div class="answer-card">'
            f'<div class="answer-top">'
            f'<div class="answer-eyebrow">Answer</div>'
            f'<div class="answer-body">{_html.escape(result["answer"])}</div>'
            f'</div>'
            f'{chart_html}'
            f'</div>',
            unsafe_allow_html=True,
        )

        # Action buttons — plain Streamlit widgets, no HTML wrapper tricks
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        btn_c1, btn_c2, _ = st.columns([1.1, 1.9, 4])
        with btn_c1:
            sql_label = "› Hide SQL" if st.session_state.show_sql else "› Show SQL"
            if st.button(sql_label, key="btn_sql"):
                st.session_state.show_sql = not st.session_state.show_sql
                st.rerun()
        with btn_c2:
            trace_label = "› Hide reasoning" if st.session_state.show_trace else "› Show how I got this"
            if st.button(trace_label, key="btn_trace"):
                st.session_state.show_trace = not st.session_state.show_trace
                st.rerun()

        # SQL panel
        if st.session_state.show_sql and result.get("sql"):
            st.code(result["sql"], language="sql")

        # Trace panel
        if st.session_state.show_trace:
            _render_trace(result.get("steps", []), result.get("sql"))

        # Meta
        model_label = "Haiku 4.5" if result["model"] == MODEL_PRIMARY else "Sonnet 4.6"
        st.markdown(
            f'<p class="meta">'
            f'{model_label}'
            f'<span class="meta-dot">·</span>'
            f'{result["iterations"]} iteration{"s" if result["iterations"] != 1 else ""}'
            f'<span class="meta-dot">·</span>'
            f'{result["routed_to"]}'
            f'</p>',
            unsafe_allow_html=True,
        )

st.markdown(
    '<p class="footer">Read-only access to the TPC-H sample database</p>',
    unsafe_allow_html=True,
)
