# CLAUDE.md

## Project

Kestrel Provisions Control Tower — an FDE take-home. Build a supply chain
"control tower" over an 18-month operational SQLite dataset, a scrape
target, and a flaky partner billing API. Two deliverables: a working
system that starts cold with one command, and `DECISIONS.md` (one page).

Full task breakdown lives in `docs/01_Assignment_Brief.md` and
`docs/02_Data_Dictionary.md`. Read those, and `DECISIONS.md` once it
exists, before making architectural calls.

**Stack:** FastAPI backend + Next.js (App Router) frontend, two processes
launched together by `scripts/serve.sh` (`make serve`). Build pipeline
(`make build`) cleans the raw DB and ingests external sources into a
derived `data/analytics.db`; the app only ever reads from that.

## Repo layout

```
config/settings.py       paths, ports, LLM provider resolution order
data/
  kestrel_ops.db          raw source DB (not committed, grader-supplied)
  analytics.db            build output (not committed, gitignored)
  ref/city_name_map.csv   canonical city spellings
  raw_cache/               cached raw pages from external sources (resumable)
build/
  dims/ facts/ external/ marts/   one script per table, see docs/analytics-schema
  pipeline.py             orchestrates the full build in dependency order
  assertions.py           data-quality guardrails asserted at build time
app/                      FastAPI: routers, LLM provider interface, schemas
frontend/                 Next.js App Router, TypeScript, light-only design
  app/                    one page per pillar (service/coldchain/money/price-position/ask) + landing
  components/ui.tsx       shared primitives (Card, Th/Td, PageHeader, ErrorBanner, EmptyRow) — reuse these, don't restyle inline
  components/charts/      hand-rolled SVG Bar/LineChart, see dataviz skill conventions
scripts/
  profile_source_db.py    ground-truth profiling + regression guards
  serve.sh                launches uvicorn + next dev together
  qa_checklist.md         the brief's 8 illustrative questions run against the live system
partner_api/               supplied mock carrier billing API (gitignored fixture)
bazaarpulse_site/          supplied mock scrape target (gitignored fixture)
docs/                       assignment brief, data dictionary, external sources
tests/
```

## Known data gotchas (don't re-derive, don't re-break)

- Dedupe/join outlets on `outlet_code` only — `outlet_name` has 70+ duplicate
  groups. 3 test outlets (`TST00001-3`) are `status=ACTIVE`, excluded by
  code/name pattern, never by status.
- `orders.created_at` format is a clean split by `source_system`;
  `deliveries.actual_arrival` a clean split by `telematics_vendor`. Parse
  per-source, don't guess a single format.
- `returns_credit_notes.return_qty` sign bug is uncorrelated noise — `ABS()`
  it, it isn't a meaningful reversal flag.
- `Bangalore`/`Bengaluru` and `Delhi`/`New Delhi` collapse via
  `data/ref/city_name_map.csv`; `Gurugram`/`Guwahati` are real distinct
  cities, never merge them.
- Freight `amount` is in paise; freight timestamps are UTC vs. the
  operational DB's IST.
- `/internal/` on the scrape target is robots-disallowed and must never be
  fetched.
- The frontend is deliberately light-only (`color-scheme: light` pinned in
  `globals.css`) — every surface color is a fixed light value, so letting
  the OS dark-mode media query flip text color previously put light text on
  light surfaces. Don't reintroduce a dark-mode media query without also
  redefining the surface colors.

## How to work in this repo

**Think before coding.** State assumptions explicitly rather than guessing.
If more than one reasonable interpretation exists, say so and ask instead
of silently picking one.

**Simplicity first.** Write the minimum code that solves the stated
problem — no speculative flexibility, no abstraction for single-use code,
no error handling for scenarios that can't happen here. If it could be
half the size, rewrite it that size.

**Surgical changes.** Touch only what the task requires. Don't refactor
adjacent code or "improve" unrelated formatting. Match existing style.
Remove only the dead code your own change creates.

**Goal-driven execution.** Turn tasks into a verifiable check before
starting — a row count, a spot-checked value, a curl response, a test —
and run it yourself before calling the task done, per each task's
acceptance criterion in the plan.

Keep code DRY, but don't extract an abstraction until a third real
duplicate shows up — two similar blocks are still fine.

## Commits

- Conventional commits (`feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`).
- One line, lowercase, no trailing period.
- No AI/Claude co-author trailer.
