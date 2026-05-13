"""Auditor: every page must expose the required universal nav/footer links.

Per docs/sop.md section "Navigation (Applies to Every Page)":
> Every page on the site exposes the following links via the nav bar or footer:
> Home Page, About Us, Contact Us, Privacy Policy, Top Level Service Pages,
> Areas We Serve Page, Blog Archive.

Per docs/sop.md section "Hub Pages and Nav Dropdowns":
> >20 top-level service pages: the Services hub page is required.
> >20 top-level location pages: the Areas We Serve hub page is required.

This auditor checks for the presence of each required nav/footer target on
every classified page. It emits one Violation per missing target. Anchor-text
conventions are not checked here (deferred to v2).
"""

from __future__ import annotations

from collections import defaultdict

import pandas as pd

from engine.config import ClientConfig
from engine.registry import SiteRegistry
from engine.violations import Severity, Violation

NAME = "universal_nav"
SEVERITY = Severity.CRITICAL

# (canonical target path, rule slug) - always required per SOP
_ALWAYS_REQUIRED: list[tuple[str, str]] = [
    ("/", "missing_home"),
    ("/about-us", "missing_about_us"),
    ("/contact-us", "missing_contact_us"),
    ("/privacy-policy", "missing_privacy_policy"),
    ("/blog", "missing_blog_archive"),
]

# Per SOP hub rules: hub page is only required when the count exceeds this.
_HUB_THRESHOLD = 20


def run(
    registry: SiteRegistry,
    links_df: pd.DataFrame,
    config: ClientConfig,
) -> list[Violation]:
    """Emit one Violation per missing universal nav target on each classified page."""
    required = list(_ALWAYS_REQUIRED)
    if len(config.services) > _HUB_THRESHOLD:
        required.append(("/services", "missing_services_hub"))
    if len(config.locations) > _HUB_THRESHOLD:
        required.append(("/areas-we-serve", "missing_areas_we_serve_hub"))

    links_by_source: dict[str, set[str]] = defaultdict(set)
    for source, target in zip(
        links_df["source_url"], links_df["target_url"], strict=True
    ):
        links_by_source[source].add(target)

    violations: list[Violation] = []
    for page in registry.all_pages():
        outgoing = links_by_source.get(page.raw_path, set())
        for target_path, rule_slug in required:
            if page.raw_path == target_path:
                continue  # a page is not required to link to itself
            if target_path in outgoing:
                continue
            violations.append(
                Violation(
                    rule=f"{NAME}.{rule_slug}",
                    severity=SEVERITY,
                    source_url=page.url,
                    page_type=page.page_type,
                    expected=target_path,
                    actual=None,
                    message=(
                        f"Page does not link to required nav target {target_path}"
                    ),
                )
            )

    return violations
