# Internal Linking Audit Report — wheelhouseit

_Generated 2026-05-13 06:32 for `wheelhouseit.com`._

## Pipeline summary

| Stage | Result |
|---|---:|
| URLs read | 2,148 |
| Classified | 1,060 |
| Ignored (per `url_patterns_to_ignore`) | 1,088 |
| Internal links analyzed | 359,729 |
| Canonical conflict clusters | 29 |
| **Total violations** | **74,449** |

## Classification breakdown

| Page type | Count |
|---|---:|
| `blog_post` | 806 |
| `top_level_service` | 108 |
| `local_landing` | 102 |
| `neighborhood_service` | 26 |
| `top_level_location` | 8 |
| `sub_service` | 8 |
| `blog_archive` | 1 |
| `home` | 1 |

## Violations by severity

| Severity | Count |
|---|---:|
| critical | 4,701 |
| warning | 69,748 |

## Violations by auditor

| Auditor | Violations |
|---|---:|
| `duplicate_links` | 68,027 |
| `universal_nav` | 4,396 |
| `blog_link_budget` | 1,612 |
| `service_silo` | 140 |
| `click_depth` | 132 |
| `canonical_conflicts` | 96 |
| `location_silo` | 46 |
| `neighborhood_silo` | 0 |

## Violations by rule

| Rule | Severity | Count |
|---|---|---:|
| `duplicate_links.same_target_multiple_times` | warning | 68,027 |
| `universal_nav.missing_about_us` | critical | 1,060 |
| `universal_nav.missing_contact_us` | critical | 1,060 |
| `universal_nav.missing_privacy_policy` | critical | 1,060 |
| `universal_nav.missing_services_hub` | critical | 1,060 |
| `blog_link_budget.too_many_service_links` | warning | 760 |
| `blog_link_budget.too_many_silo_blog_links` | warning | 737 |
| `service_silo.missing_local_landing_link` | critical | 140 |
| `click_depth.unreachable` | critical | 119 |
| `universal_nav.missing_home` | critical | 78 |
| `universal_nav.missing_blog_archive` | critical | 78 |
| `blog_link_budget.too_few_silo_blog_links` | warning | 69 |
| `blog_link_budget.missing_service_link` | warning | 46 |
| `location_silo.missing_local_landing_link` | critical | 46 |
| `canonical_conflicts.duplicate_blog_post` | warning | 40 |
| `canonical_conflicts.duplicate_top_level_service` | warning | 33 |
| `canonical_conflicts.duplicate_local_landing` | warning | 23 |
| `click_depth.exceeds_three_clicks` | warning | 13 |

## Sitewide structural findings

Rules that fire on essentially every classified page indicate a structural / template-level issue rather than per-page problems to fix one-by-one. Address these first.

| Rule | Pages affected |
|---|---:|
| `universal_nav.missing_about_us` | 1,060 |
| `universal_nav.missing_contact_us` | 1,060 |
| `universal_nav.missing_privacy_policy` | 1,060 |
| `universal_nav.missing_services_hub` | 1,060 |

## Top 15 most-violating pages

| Violations | Page |
|---:|---|
| 212 | `wheelhouseit.com/blog` |
| 88 | `wheelhouseit.com/cloud-management` |
| 87 | `wheelhouseit.com/healthcare-it-outsourcing` |
| 87 | `wheelhouseit.com/it-solutions-healthcare-2` |
| 86 | `wheelhouseit.com/healthcare-it-managed-services` |
| 82 | `wheelhouseit.com/managed-it-services-for-law-firms` |
| 82 | `wheelhouseit.com/new-york-city` |
| 82 | `wheelhouseit.com/fort-lauderdale` |
| 81 | `wheelhouseit.com/blog/whats-new-in-microsoft-teams-march-2020` |
| 81 | `wheelhouseit.com/blog/legacy-phone-solutions-why-they-fell-short-during-the-pandemic` |
| 81 | `wheelhouseit.com/blog/8-tips-for-having-the-best-online-meeting-experience-with-microsoft-teams` |
| 81 | `wheelhouseit.com/healthcare-it-managed-services/new-york-city` |
| 81 | `wheelhouseit.com/healthcare-it-managed-services/manhattan` |
| 81 | `wheelhouseit.com/healthcare-it-managed-services/long-island` |
| 81 | `wheelhouseit.com/international-it-support` |

## Recommended priorities

Suggested order of attack, highest signal-to-effort first:

1. **Fix the sitewide structural issues** listed above first — each one resolved drops violations by the page count in one move.
2. **Consolidate the 29 canonical-conflict clusters** (see `canonical_conflicts.duplicate_*` rows in `violations.csv`). Duplicate URLs that classify identically also inflate `service_silo`, `location_silo`, and `click_depth` counts — fixing them cascades.
3. **Restore internal links to the 119 unreachable pages** (see `click_depth.unreachable` in `violations.csv`). These can't be crawled at all via site navigation.
4. **Fix the 186 silo-linking gaps** (`service_silo.*`, `location_silo.*`, `neighborhood_silo.*`). These are the core SOP rules for parent→child link coverage.
5. **Review the 68,027 `duplicate_links` violations** — this typically indicates mega-footer template duplication. Consider reducing footer link density or extending the UI-anchor allowlist in the auditor.

---

_See `violations.csv` for the full per-violation list and `registry_summary.csv` for the classification index._