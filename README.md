# internal-link-analyzer

An internal linking audit engine for local SEO websites. Reads crawl data exported from Website Auditor, classifies every URL by page type, and reports violations against the SOP in `docs/sop.md`.

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
# Full audit
python audit.py --client <client-slug>

# Run a single auditor (for debugging)
python audit.py --client <client-slug> --auditor universal_nav

# Classify URLs only — skips auditors, dumps unclassified_urls.csv
python audit.py --client <client-slug> --classify-only

# Verbose logging
python audit.py --client <client-slug> --verbose
```

Input files go in `clients/<client-slug>/input/` (gitignored). Output lands in `clients/<client-slug>/output/` (gitignored).

## Adding a client

See the "Adding a new client" section in `CLAUDE.md`.

## Tests

```bash
pytest
```
