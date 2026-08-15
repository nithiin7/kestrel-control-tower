# FDE Take-Home Assignment Pack

**Kestrel Provisions: Supply Chain Control Tower**

## Contents

| File | Read order |
|---|---|
| `01_Assignment_Brief.docx` | 1. Start here |
| `01_Assignment_Brief.md` | Same brief, markdown |
| `02_Data_Dictionary.md` | 2. Partial documentation of the database |
| `03_External_Sources.md` | 3. How to reach the scrape target and the APIs |
| `data/kestrel_ops.db` | SQLite, 13 tables, ~820,000 rows |
| `data/csv/` | Same tables as CSV |
| `bazaarpulse_site/` | Static competitor price site. Serve locally |
| `partner_api/server.py` | Mock carrier billing API. Runs on port 8088 |

## Quick start

```bash
# database
sqlite3 data/kestrel_ops.db ".tables"

# competitor price site
cd bazaarpulse_site && python3 -m http.server 8080

# partner API
pip install fastapi uvicorn && python3 partner_api/server.py
```

All data is synthetic and generated for assessment purposes. Kestrel Provisions,
BazaarPulse and all named individuals are fictional.
