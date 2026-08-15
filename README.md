# Kestrel Provisions Control Tower

A supply chain "control tower" over Kestrel Provisions' 18-month operational
SQLite dataset, a partner freight-billing API, and a competitor price scrape
target. FastAPI backend + Next.js frontend, reading from a derived
`data/analytics.db` built by a one-command pipeline. Five pillars: Service,
Cold Chain, Money, Price Position, and Ask-anything (natural-language
questions over the data).

See `DECISIONS.md` for what was built, what was deliberately left out, and
the judgment calls made where the brief was ambiguous. See `CLAUDE.md` for
repo layout and coding conventions.

## What you'll see

A sticky nav (Overview / Service / Cold Chain / Money / Price Position / Ask)
and a shared filter bar (region/warehouse/route/outlet/date range) on every
page:

- **Overview** — the latest complete fiscal quarter, and a "worst of worst"
  summary across all four KPI pillars.
- **Service** — worst-performing outlets by fill rate, fill-rate trend, and
  fill rate by region.
- **Cold Chain** — worst cold-chain routes by excursion rate, excursion trend
  by month, and near-expiry stock value by warehouse.
- **Money** — routes with the highest freight cost per delivered case, cost
  trend by month, and cost by warehouse.
- **Price Position** — Kestrel's MRP vs. the competitor's own MRP vs. the
  competitor's observed street price, as three clearly separated columns
  (scoped to the 4 cities BazaarPulse covers).
- **Ask** — a chat-style box for natural-language questions over the data;
  shows the generated SQL and result table alongside the answer, or a clear
  "no LLM configured" state if neither provider below is set up.

## Prerequisites

- **Python 3.12+**
- **Node.js 20.9+** (Next.js 16's minimum)
- `data/kestrel_ops.db` — the raw source database. Supplied separately by
  the grader (not committed to this repo — see `.gitignore`). Place it at
  exactly `data/kestrel_ops.db` before running anything.
- `partner_api/` and `bazaarpulse_site/` — the two mock services from the
  assignment pack. Also not committed (gitignored fixtures). Place them at
  the repo root, i.e. `partner_api/server.py` and `bazaarpulse_site/index.html`
  should exist.

## 1. Clone and install dependencies

```bash
git clone <this-repo-url>
cd kestrel-control-tower

# Python
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Node
npm install --prefix frontend
```

## 2. Place the supplied files

Copy in the three assets listed under Prerequisites:

```
data/kestrel_ops.db
partner_api/server.py
bazaarpulse_site/  (index.html, robots.txt, product/, city/, ...)
```

## 3. Start the two mock services

These stand in for Kestrel's real partner freight-billing API and the
public competitor price tracker. They're only needed while building the
analytics database (step 4) — the app itself never calls them at request
time, only the build pipeline does. Each needs its own terminal (a fresh
shell, so the venv from step 1 isn't active there — the commands below
call it directly rather than assuming it's been re-activated):

```bash
# partner carrier billing API — :8088
.venv/bin/python3 partner_api/server.py

# competitor price scrape target — :8080 (stdlib only, any python3 works)
cd bazaarpulse_site && python3 -m http.server 8080
```

Leave both running through step 4. You can stop them afterward — `make serve`
(step 6) doesn't need them.

## 4. Build the analytics database

With the venv active and both mock services running:

```bash
make build
```

This runs `build/pipeline.py`, which chains every dimension, fact,
external-ingestion, and mart build script in dependency order and writes
`data/analytics.db`. It's safe to re-run (idempotent — every step drops and
rebuilds its own tables) and takes a few minutes the first time, mostly
spent on the freight invoice ingest and the BazaarPulse crawl. It fails
loudly and stops before touching `analytics.db` if the source data doesn't
match the assumptions the pipeline was built against.

## 5. Configure environment variables (optional)

Ask-anything (`/ask`) works without any of this — it just reports that no
LLM is configured. To enable it, pick one:

- **Anthropic** (preferred if you have a key): export it in the shell
  before starting the backend — `config/settings.py` reads it as a real
  process environment variable, not from a file:
  ```bash
  export ANTHROPIC_API_KEY=sk-...
  ```
- **Ollama** (local, no key needed): if an Ollama server is already
  running on `localhost:11434`, the backend uses it automatically whenever
  `ANTHROPIC_API_KEY` isn't set. The default model name is `llama3.1`
  (`config/settings.py`) — if that isn't what you have pulled, set
  `OLLAMA_MODEL` to match one you do (`ollama list` to check):
  ```bash
  OLLAMA_MODEL=qwen3:4b make serve
  ```
  Responses from a local model can take 30–90s — that's expected, not a hang.

Resolution order: `ANTHROPIC_API_KEY` first, then a live Ollama probe, then
"not configured" — never a startup failure either way.

The frontend defaults to `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000`
even with no `.env.local` file at all, so nothing to do here if you're
using the default ports from this guide. Only needed if the backend runs
somewhere else:

```bash
cp frontend/.env.local.example frontend/.env.local
# then edit NEXT_PUBLIC_API_BASE_URL in that file
```

## 6. Run the app

```bash
make serve
```

This runs `scripts/serve.sh`, which starts `uvicorn` (backend, `:8000`) and
`next dev` (frontend, `:3000`) together as a single foreground command.
Open **http://localhost:3000**. A single **Ctrl+C** stops both processes
cleanly — nothing is left running in the background.

## Troubleshooting

- **Port already in use**: something else is bound to 8000, 8080, 8088, or
  3000. Find and stop it (`lsof -i :8000`, etc.) before retrying.
- **`make build` fails immediately with a "T1 profiling assertion regressed"
  error**: the source `data/kestrel_ops.db` doesn't match what the pipeline
  expects (wrong file, or a different snapshot). Confirm you placed the
  exact supplied file at `data/kestrel_ops.db`.
- **`make build` fails partway through an external-ingestion step**: confirm
  both mock services from step 3 are still running and reachable at
  `:8088`/`:8080`.
- **Frontend loads but shows no data / fetch errors**: confirm the backend
  is running on `:8000`. If you created a custom `frontend/.env.local`
  (step 5), confirm `NEXT_PUBLIC_API_BASE_URL` in it actually matches where
  the backend is running.
- **`/ask` returns a 500 / connection error with Ollama running**: the
  default `OLLAMA_MODEL` (`llama3.1`) probably isn't pulled. Run
  `ollama list` and set `OLLAMA_MODEL` to a model you actually have (see
  step 5).
