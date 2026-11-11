# Frontend

React 19 + Vite + Tailwind CSS v4 + Recharts. Talks to the FastAPI backend in the parent folder
(`/ask/stream`, `/config`), proxied by Vite during development (see `vite.config.js`).

```bash
npm install
npm run dev      # http://localhost:5173 (start the backend on :8000 first)
npm run lint     # oxlint
npm run build    # production bundle in dist/
```

Layout: `src/App.jsx` (page + state), `src/components/` (answer card, reasoning trace),
`src/lib/` (API client with SSE streaming, number formatting, SQL highlighting).
