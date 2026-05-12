# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

This file orients Claude Code on the project. Read it at the start of every session before making changes.

## Project purpose

This repo is an internal linking audit engine for local SEO websites. It reads crawl data (URL list + internal links list) exported from Website Auditor, classifies every URL by page type, and reports violations against a defined Standard Operating Procedure (`docs/sop.md`).

The engine is multi-tenant: one codebase, many client configs. Adding a new client is adding a new folder under `clients/`, not changing engine code.

The audit is deterministic. No LLM calls in the audit logic. Same input → same output, every time. The only "judgment" in the system is the classifier matching URL slug tokens against the client's known services and locations — that's pure string matching, not inference.

## Mental model: engine vs config

Two things live in this repo, and they must stay separate:

1. The engine (`engine/`) — code that doesn't change per client. The classifier, the registry, the auditors, the report generator. Versioned, tested, shared across all clients.
2. Client configs (`clients/[slug]/`) — small files describing one client. Services list, locations list, neighborhoods, aliases, and the crawl input data. Not versioned (the configs are versioned; the input/output CSVs are gitignored).

Rules belong in the engine. Data belongs in client configs. If you find yourself hardcoding a client-specific value in engine code, stop — it belongs in the client config schema instead.

## Source of truth for audit rules

`docs/sop.md` is the authoritative specification for what the auditors check. When implementing or modifying an auditor:

1. Re-read the relevant section of `docs/sop.md` first.
2. Quote the rule in the auditor's docstring.
3. If `docs/sop.md` is ambiguous on a point, do not guess. Stop and surface the ambiguity to the human for clarification, then update `docs/sop.md` once the answer is decided.

Auditors are derived from the SOP, not the other way around. If a rule needs to change, the SOP changes first, then the auditor.

## Tech stack and conventions

* Python 3.11+ (use modern syntax: `str | None`, `list[X]`, `match` statements, `StrEnum`)
* pandas for CSV processing
* Pydantic v2 for config schema validation
* pytest for tests
* click for the CLI entry point
* pyyaml for loading client configs

Style:

* Type hints everywhere. No untyped function signatures.
* Dataclasses (`@dataclass(frozen=True)`) for engine-internal data structures (Violation, PageClassification, etc.). Pydantic models for external-facing config that needs validation.
* Functions over classes where possible. Auditors are functions, not classes.
* No bare `except:`. Catch specific exceptions or let them bubble.
* Fail loudly on bad data, not silently. If a CSV is malformed or a URL can't be parsed, raise a clear error. Don't swallow and produce a misleading clean run.

## Repository structure

```
seo-internal-linking-audit/
  .github/
    workflows/
      audit.yml              # GitHub Action: run audit for a client
  docs/
    sop.md                   # AUTHORITATIVE rule spec — read before changing auditors
    architecture.md          # Optional: notes on engine internals
  engine/
    __init__.py
    config.py                # Pydantic models for client config
    classifier.py            # URL → PageClassification
    registry.py              # SiteRegistry: indexed access to classified pages
    violations.py            # Violation dataclass, Severity enum
    auditors/
      __init__.py            # Registers all auditors
      universal_nav.py
      click_depth.py
      duplicate_links.py
      blog_link_budget.py
      service_silo.py
      location_silo.py
      neighborhood_silo.py
      canonical_conflicts.py
    report.py                # Writes violations.csv, canonical_conflicts.csv, summary.md
  clients/
    .gitkeep
    [client-slug]/
      config.yml             # Client config (versioned)
      input/                 # Website Auditor exports (gitignored)
        urls.csv
        links.csv
      output/                # Audit results (gitignored)
        violations.csv
        canonical_conflicts.csv
        summary.md
        unclassified_urls.csv
  tests/
    fixtures/
      sample_config.yml
      sample_urls.csv
      sample_links.csv
    test_classifier.py
    test_registry.py
    test_auditors/
      test_universal_nav.py
      test_click_depth.py
      ...
  audit.py                   # CLI entry point
  CLAUDE.md                  # This file
  README.md
  requirements.txt
  pyproject.toml
  .gitignore                 # Ignores clients/*/input/, clients/*/output/
```

## Key contracts

### PageClassification

The classifier returns one of these per URL.

```python
from dataclasses import dataclass
from enum import StrEnum

class PageType(StrEnum):
    HOME = "home"
    ABOUT_US = "about_us"
    BIO = "bio"
    CONTACT_US = "contact_us"
    PRIVACY_POLICY = "privacy_policy"
    SERVICES_HUB = "services_hub"
    AREAS_WE_SERVE_HUB = "areas_we_serve_hub"
    TOP_LEVEL_SERVICE = "top_level_service"
    TOP_LEVEL_LOCATION = "top_level_location"
    SUB_SERVICE = "sub_service"
    LOCAL_LANDING = "local_landing"
    NEIGHBORHOOD = "neighborhood"
    SUBSERVICE_LANDING = "subservice_landing"
    NEIGHBORHOOD_SERVICE = "neighborhood_service"
    BLOG_ARCHIVE = "blog_archive"
    BLOG_POST = "blog_post"
    UNKNOWN = "unknown"

@dataclass(frozen=True)
class PageClassification:
    url: str                       # normalized URL
    page_type: PageType
    location: str | None = None    # slug, e.g. "fort-lauderdale"
    service: str | None = None     # slug, e.g. "it-support"
    subservice: str | None = None  # slug, e.g. "24-hour"
    neighborhood: str | None = None
    bio_name: str | None = None    # for BIO pages
    blog_slug: str | None = None   # for BLOG_POST
    raw_path: str = ""             # original path for debugging
```

When the classifier cannot match a URL to a known page type, it returns `PageType.UNKNOWN`. Do not guess. Unclassified URLs are written to `unclassified_urls.csv` for human review.

### SiteRegistry

Built once from the list of classifications. Provides indexed lookups.

```python
class SiteRegistry:
    def get_by_url(self, url: str) -> PageClassification | None: ...
    def get_by_type(self, page_type: PageType) -> list[PageClassification]: ...
    def get_top_level_service(self, service: str) -> PageClassification | None: ...
    def get_top_level_location(self, location: str) -> PageClassification | None: ...
    def get_local_landing_pages_for_service(self, service: str) -> list[PageClassification]: ...
    def get_local_landing_pages_for_location(self, location: str) -> list[PageClassification]: ...
    def get_local_landing_page(self, location: str, service: str) -> PageClassification | None: ...
    def get_subservice(self, service: str, subservice: str) -> PageClassification | None: ...
    def get_subservice_landing_pages(self, location: str, service: str) -> list[PageClassification]: ...
    def get_neighborhood(self, location: str, neighborhood: str) -> PageClassification | None: ...
    def get_neighborhoods_for_location(self, location: str) -> list[PageClassification]: ...
    def get_neighborhood_service_pages(self, location: str, neighborhood: str) -> list[PageClassification]: ...
    def get_blog_posts(self) -> list[PageClassification]: ...
    def get_parent(self, page: PageClassification) -> PageClassification | None: ...
    def get_canonical_conflicts(self) -> list[list[PageClassification]]: ...
    def all_pages(self) -> list[PageClassification]: ...
```

Parent lookup does not parse URL strings. It uses the classification attributes — e.g., the parent of a Local Landing Page with `location="fort-lauderdale"` is whatever page in the registry has `page_type=TOP_LEVEL_LOCATION` and `location="fort-lauderdale"`. This is what makes the audit work on sites with any URL structure (flat, nested, mixed).

### Violation

```python
class Severity(StrEnum):
    CRITICAL = "critical"   # SOP rule violation that hurts SEO meaningfully
    WARNING = "warning"     # SOP rule violation, lower impact
    INFO = "info"           # noteworthy but not a violation per se

@dataclass(frozen=True)
class Violation:
    rule: str               # e.g. "universal_nav.missing_home_link"
    severity: Severity
    source_url: str
    page_type: PageType
    expected: str | None    # what should be there
    actual: str | None      # what is there (or None if missing)
    message: str            # human-readable summary
```

### Auditor function signature

Every auditor is a function with this signature:

```python
def run(
    registry: SiteRegistry,
    links_df: pd.DataFrame,
    config: ClientConfig,
) -> list[Violation]:
    """One-line description of what this auditor checks.
    
    Per docs/sop.md section "<section name>":
    > <quote of the rule>
    """
    ...
```

`links_df` columns are guaranteed to be: `source_url`, `target_url`, `anchor_text`, `link_type` (nav/footer/body/sidebar — best-effort, may be None).

Each auditor file (`engine/auditors/[name].py`) exports a single `run` function plus module-level constants for `NAME` (string) and `SEVERITY` (default severity for violations from this auditor). The `__init__.py` in `engine/auditors/` collects all auditors into a registry.

### ClientConfig

```python
from pydantic import BaseModel

class ServiceConfig(BaseModel):
    slug: str
    display: str
    aliases: list[str] = []

class NeighborhoodConfig(BaseModel):
    slug: str
    display: str | None = None
    aliases: list[str] = []

class LocationConfig(BaseModel):
    slug: str
    display: str
    aliases: list[str] = []
    neighborhoods: list[NeighborhoodConfig] = []

class SubserviceConfig(BaseModel):
    parent: str  # parent service slug
    slug: str
    display: str
    aliases: list[str] = []

class ClientConfig(BaseModel):
    client: str
    domain: str
    services: list[ServiceConfig]
    locations: list[LocationConfig]
    subservices: list[SubserviceConfig] = []
    url_patterns_to_ignore: list[str] = []  # regex patterns
```

## CLI usage

```bash
# Full audit
python audit.py --client wheelhouseit

# Run one auditor only (for debugging)
python audit.py --client wheelhouseit --auditor universal_nav

# Classify only (skip auditors, dump classification CSV)
python audit.py --client wheelhouseit --classify-only

# Verbose logging
python audit.py --client wheelhouseit --verbose
```

Outputs land in `clients/[client]/output/`:

* `violations.csv` — one row per violation, sorted by severity then page type
* `canonical_conflicts.csv` — URL clusters with identical classification (likely duplicates)
* `unclassified_urls.csv` — URLs that didn't classify, for config refinement
* `summary.md` — human-readable summary with counts and top issues

## How to add things

### Adding a new auditor

1. Re-read the relevant section of `docs/sop.md`.
2. Create `engine/auditors/[rule_name].py` with module constants `NAME`, `SEVERITY`, and the `run` function.
3. Register it in `engine/auditors/__init__.py`.
4. Write tests in `tests/test_auditors/test_[rule_name].py` using fixtures in `tests/fixtures/`.
5. Run the auditor in isolation against an existing client (`--auditor [rule_name]`) before merging.

### Adding a new client

1. Create `clients/[client-slug]/` with subfolders `input/` and `output/`.
2. Create `clients/[client-slug]/config.yml` per the `ClientConfig` schema.
3. Drop the Website Auditor exports as `input/urls.csv` and `input/links.csv`.
4. Run `python audit.py --client [slug] --classify-only` first.
5. Review `unclassified_urls.csv`. Add missing services/locations/aliases to the config, or add patterns to `url_patterns_to_ignore`.
6. Iterate until classification coverage is acceptable (target: >95% of commercial URLs classified).
7. Run the full audit.

### Adding a new rule that the SOP doesn't cover

Don't. Update `docs/sop.md` first with the new rule and rationale, get human sign-off, then implement the auditor. The engine must not enforce rules that aren't documented in the SOP.

## Things to AVOID

* Do not add LLM calls to the audit logic. Classification and rule checking are deterministic. If you're tempted to "use an LLM to figure out if these two URLs are about the same thing," the answer is to use the classification attributes instead.
* Do not parse URL strings for parent/child lookups inside auditors. Use the registry. URL string parsing happens once, in the classifier, and produces a `PageClassification`. Auditors work on classifications.
* Do not fetch pages from the internet. All input is the Website Auditor CSVs. The audit is offline.
* Do not guess when classifying. Unmatched URLs are `PageType.UNKNOWN`, written to `unclassified_urls.csv`, and surfaced to the human for config refinement.
* Do not bake client-specific values into engine code. They go in `config.yml`.
* Do not put everything in one file. Auditors are one per file. The cost of more files is far lower than the cost of a 2000-line `auditors.py`.
* Do not write defensive `try/except` blocks that swallow errors. Fail loudly. The audit running but producing wrong output is much worse than the audit crashing with a clear error.
* Do not add caching, async, or parallelism in v1. The audit runs on bounded data in seconds. Optimize when there's a measured problem.
* Do not change `docs/sop.md` casually. It's a human-owned specification. Propose changes; don't make them silently.

## Testing conventions

* Every auditor has at least three test cases: a passing case (no violations), a clear failure case (1+ violations), and an edge case (empty input, missing optional fields, etc.).
* Fixtures live in `tests/fixtures/`. The sample data is small and hand-crafted, not real client data.
* Tests are fast. The full test suite runs in under 10 seconds.
* Run with `pytest` from the repo root.

## Session start checklist

When starting a Claude Code session in this repo:

1. Read this file (`CLAUDE.md`).
2. If working on an auditor, also read the relevant section of `docs/sop.md`.
3. If working on the classifier, read `clients/wheelhouseit/config.yml` (or whichever client config is in scope) to understand the data shapes.
4. Run `pytest` to confirm the test suite is green before making changes.
5. Make changes incrementally — one auditor, one feature, one fix at a time.
6. Run tests after each change.

## Open questions / known gaps

This list is maintained as the engine evolves. Items here are known unknowns that should be resolved before they bite.

* None yet — populate as discovered.
