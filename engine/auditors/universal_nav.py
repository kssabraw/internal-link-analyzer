"""Auditor: every page must expose the required universal nav/footer links.

Per docs/sop.md section "Navigation (Applies to Every Page)":
> Every page on the site exposes the following links via the nav bar or footer:
> Home Page, About Us, Contact Us, Privacy Policy, Top Level Service Pages,
> Areas We Serve Page, Blog Archive.

Per docs/sop.md section "Hub Pages and Nav Dropdowns":
> >20 top-level service pages: the Services hub page is required.
> >20 top-level location pages: the Areas We Serve hub page is required.

This auditor sources each universal-nav target from the registry rather than
hard-coding SOP-default paths, so clients whose About Us / Contact Us /
Privacy Policy live at configured aliases (`path_aliases`) are checked
correctly. If a required page type is missing from the site entirely, the
auditor emits a single site-level violation rather than per-page noise.
"""

from __future__ import annotations

from collections import defaultdict

import pandas as pd

from engine.classifier import PageType
from engine.config import ClientConfig
from engine.registry import SiteRegistry
from engine.violations import Severity, Violation

NAME = "universal_nav"
SEVERITY = Severity.CRITICAL

# (PageType, rule slug for missing link, SOP-default path) - always required per SOP.
# The default path is only used in violation messages when no page of that type
# exists on the site, so the human reviewer sees what was expected.
_ALWAYS_REQUIRED: list[tuple[PageType, str, str]] = [
    (PageType.HOME, "missing_home", "/"),
    (PageType.ABOUT_US, "missing_about_us", "/about-us"),
    (PageType.CONTACT_US, "missing_contact_us", "/contact-us"),
    (PageType.PRIVACY_POLICY, "missing_privacy_policy", "/privacy-policy"),
    (PageType.BLOG_ARCHIVE, "missing_blog_archive", "/blog"),
]

# Per SOP hub rules: hub page is only required when the count exceeds this.
_HUB_THRESHOLD = 20


def run(
    registry: SiteRegistry,
    links_df: pd.DataFrame,
    config: ClientConfig,
) -> list[Violation]:
    """Emit Violations for missing universal nav targets.

    Per-page violations are emitted when the target page exists but isn't
    linked from a given page. Site-level violations are emitted once when a
    required target page type doesn't exist anywhere on the site at all.
    """
    required: list[tuple[PageType, str, str]] = list(_ALWAYS_REQUIRED)
    if len(config.services) > _HUB_THRESHOLD:
        required.append((PageType.SERVICES_HUB, "missing_services_hub", "/services"))
    if len(config.locations) > _HUB_THRESHOLD:
        required.append(
            (
                PageType.AREAS_WE_SERVE_HUB,
                "missing_areas_we_serve_hub",
                "/areas-we-serve",
            )
        )

    pages = registry.all_pages()
    if not pages:
        # Nothing classified; no audit to run.
        return []

    links_by_source: dict[str, set[str]] = defaultdict(set)
    for source, target in zip(
        links_df["source_url"], links_df["target_url"], strict=True
    ):
        links_by_source[source].add(target)

    violations: list[Violation] = []

    for page_type, rule_slug, default_path in required:
        canonical_paths = {p.raw_path for p in registry.get_by_type(page_type)}

        if not canonical_paths:
            # The site has no page of this type at all — emit a single
            # site-level violation rather than fire per-page noise.
            violations.append(
                Violation(
                    rule=f"{NAME}.{rule_slug}_page_missing",
                    severity=SEVERITY,
                    source_url=config.domain,
                    page_type=page_type,
                    expected=default_path,
                    actual=None,
                    message=(
                        f"Site has no {page_type.value} page — universal nav rule "
                        f"cannot be satisfied. Create one (default path: "
                        f"{default_path}) or configure path_aliases."
                    ),
                )
            )
            continue

        for page in pages:
            if page.raw_path in canonical_paths:
                continue  # a page is not required to link to itself
            outgoing = links_by_source.get(page.raw_path, set())
            if outgoing & canonical_paths:
                continue
            # When multiple canonical paths exist (canonical-conflict cluster),
            # report any of them as expected — the canonical_conflicts auditor
            # will surface the duplicate separately.
            expected = sorted(canonical_paths)[0]
            violations.append(
                Violation(
                    rule=f"{NAME}.{rule_slug}",
                    severity=SEVERITY,
                    source_url=page.url,
                    page_type=page.page_type,
                    expected=expected,
                    actual=None,
                    message=(
                        f"Page does not link to required nav target {expected}"
                    ),
                )
            )

    return violations
