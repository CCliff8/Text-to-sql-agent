# Frontend — React + Vite

React frontend for the Text-to-SQL Analyst Agent.

## Stack

- **React 19** — UI
- **Vite** — dev server and build tool
- **Tailwind CSS v4** — styling
- **Recharts** — interactive bar charts

## Setup

```bash
npm install
npm run dev
```

Runs on **http://localhost:5173**. Requires the FastAPI backend running on port 8000 (see root README).

## Structure

```
src/
├── App.jsx                  # Main page, search bar, state management
├── index.css                # Tailwind import + base styles
└── components/
    ├── AnswerCard.jsx        # Answer text + Recharts horizontal bar chart
    └── TracePanel.jsx        # Collapsible agent trace (schema, SQL, tables)
```

## API

The frontend proxies all `/ask` and `/health` requests to `http://localhost:8000` via Vite's dev proxy — no CORS configuration needed during development.
