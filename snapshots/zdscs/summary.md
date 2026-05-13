# Internal Linking Audit Report — zdscs

_Generated 2026-05-13 07:27 for `zdscs.com`._

## Pipeline summary

| Stage | Result |
|---|---:|
| URLs read | 240 |
| Classified | 113 |
| Ignored (per `url_patterns_to_ignore`) | 127 |
| Internal links analyzed | 21,628 |
| Canonical conflict clusters | 13 |
| **Total violations** | **2,278** |

## Classification breakdown

| Page type | Count |
|---|---:|
| `blog_post` | 76 |
| `top_level_service` | 23 |
| `blog_archive` | 7 |
| `home` | 2 |
| `about_us` | 2 |
| `contact_us` | 2 |
| `services_hub` | 1 |

## Violations by severity

| Severity | Count |
|---|---:|
| critical | 1 |
| warning | 2,277 |

## Violations by auditor

| Auditor | Violations |
|---|---:|
| `duplicate_links` | 2,095 |
| `blog_link_budget` | 152 |
| `canonical_conflicts` | 24 |
| `click_depth` | 6 |
| `universal_nav` | 1 |
| `service_silo` | 0 |
| `neighborhood_silo` | 0 |
| `location_silo` | 0 |

## Violations by rule

| Rule | Severity | Count |
|---|---|---:|
| `duplicate_links.same_target_multiple_times` | warning | 2,095 |
| `blog_link_budget.too_many_service_links` | warning | 76 |
| `blog_link_budget.too_many_silo_blog_links` | warning | 75 |
| `canonical_conflicts.duplicate_top_level_service` | warning | 13 |
| `click_depth.exceeds_three_clicks` | warning | 6 |
| `canonical_conflicts.duplicate_blog_archive` | warning | 6 |
| `canonical_conflicts.duplicate_blog_post` | warning | 2 |
| `universal_nav.missing_privacy_policy_page_missing` | critical | 1 |
| `blog_link_budget.too_few_silo_blog_links` | warning | 1 |
| `canonical_conflicts.duplicate_home` | warning | 1 |
| `canonical_conflicts.duplicate_about_us` | warning | 1 |
| `canonical_conflicts.duplicate_contact_us` | warning | 1 |

## Top 15 most-violating pages

| Violations | Page |
|---:|---|
| 45 | `https://www.zdscs.com/blog/?category=trends-and-trade` |
| 31 | `https://www.zdscs.com/blog/how-to-audit-your-parcel-spend-step-by-step/` |
| 30 | `https://www.zdscs.com/blog/freight-audit-pay-avoiding-fees/` |
| 27 | `https://www.zdscs.com/blog/the-role-of-rpa-in-enhancing-supply-chain-efficiency-a-deep-dive/` |
| 26 | `https://www.zdscs.com/ups-contract-negotiation/` |
| 26 | `https://www.zdscs.com/blog/freight-optimization-its-bid-time/` |
| 26 | `https://www.zdscs.com/blog/manifest-2026-recap-key-takeaways/` |
| 26 | `https://www.zdscs.com/blog/the-critical-role-of-supply-chain-visibility-in-modern-business/` |
| 25 | `https://www.zdscs.com/filing-carrier-claims/` |
| 25 | `https://www.zdscs.com/parcel-audit-services/` |
| 25 | `https://www.zdscs.com/parcel-contract-negotiation/` |
| 25 | `https://www.zdscs.com/blog/5-things-3pls-and-freight-brokers-should-consider-when-choosing-freight-audit-and-invoicing-software/` |
| 25 | `https://www.zdscs.com/blog/data-driven-carrier-negotiations/` |
| 25 | `https://www.zdscs.com/blog/freight-accrual-what-it-is-how-it-works-and-why-accuracy-matters/` |
| 25 | `https://www.zdscs.com/blog/manufacturing-freight-audit-5-hidden-costs/` |

## Recommended priorities

Suggested order of attack, highest signal-to-effort first:

1. **Consolidate the 13 canonical-conflict clusters** (see `canonical_conflicts.duplicate_*` rows in `violations.csv`). Duplicate URLs that classify identically also inflate `service_silo`, `location_silo`, and `click_depth` counts — fixing them cascades.
2. **Review the 2,095 `duplicate_links` violations** — this typically indicates mega-footer template duplication. Consider reducing footer link density or extending the UI-anchor allowlist in the auditor.

---

_See `violations.csv` for the full per-violation list and `registry_summary.csv` for the classification index._