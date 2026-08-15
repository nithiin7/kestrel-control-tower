# Kestrel Provisions Control Tower

A supply chain "control tower" over Kestrel Provisions' 18-month operational
SQLite dataset, a competitor price scrape target, and a flaky partner
billing API. FastAPI backend + Next.js frontend, reading from a derived
`data/analytics.db` built by a one-command pipeline.

See `CLAUDE.md` for repo layout and coding guidelines, `docs/` for the
assignment brief and data dictionary, and `DECISIONS.md` (once written) for
what was built, what was skipped, and why.

**Status:** in progress. This README documents what's runnable today; it
will grow into full cold-start instructions (`make build`, `make serve`) as
the build pipeline, API, and frontend land.

## Prerequisites

- Python 3.12+
- `data/kestrel_ops.db` — the raw source DB, supplied by the grader, not
  committed to this repo. Place it at that exact path before running anything.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## What's runnable now

**Source-data profiling + regression guards** — confirms the ground-truth
facts the rest of the pipeline depends on (outlet counts, city name
variants, per-source timestamp formats, etc.) and writes
`data/ref/city_name_map.csv`:

```bash
python scripts/profile_source_db.py
```

**`dim_outlets` build** — dedupes/joins outlets on `outlet_code`, excludes
the 3 test outlets into a side `dim_outlets_excluded` table for audit, and
normalizes city spelling via `city_name_map.csv`. Writes to
`data/analytics.db`:

```bash
python build/dims/build_dim_outlets.py
```

## Mock services (for later ingestion tasks)

Supplied fixtures, gitignored, copied in from the assignment pack:

```bash
# competitor price scrape target — :8080
cd bazaarpulse_site && python3 -m http.server 8080

# partner carrier billing API — :8088
python3 partner_api/server.py
```
