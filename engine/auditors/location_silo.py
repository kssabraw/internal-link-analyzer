"""Auditor: location silo linking - location pages must link down to their landings.

Per docs/sop.md section "Location Silo (Downward Links From Location Pages)":
> Top-Level Location Page -> Related Local Landing Pages: Link to every Local
> Landing Page under this location - i.e., every /[this-location]/[service]/
> page. No cap.
>
> Local Landing Page -> Subservice Landing Pages within this location/service:
> Link to every Subservice Landing Page for this location + service. No cap.

Canonical-conflict handling: when multiple URLs classify to the same
identity tuple, only the first (canonical) is required. The
canonical_conflicts auditor reports the duplicates separately.
"""

from __future__ import annotations

from collections import defaultdict

import pandas as pd

from engine.classifier import PageType
from engine.config import ClientConfig
from engine.registry import SiteRegistry
from engine.violations import Severity, Violation

NAME = "location_silo"
SEVERITY = Severity.CRITICAL


def run(
    registry: SiteRegistry,
    links_df: pd.DataFrame,
    config: ClientConfig,
) -> list[Violation]:
    """Check every location page links to all its expected child landings."""
    links_by_source: dict[str, set[str]] = defaultdict(set)
    for source, target in zip(
        links_df["source_url"], links_df["target_url"], strict=True
    ):
        links_by_source[source].add(target)

    violations: list[Violation] = []

    # 1. TOP_LEVEL_LOCATION -> LOCAL_LANDING for each service with one
    for tll_page in registry.get_by_type(PageType.TOP_LEVEL_LOCATION):
        if tll_page.location is None:
            continue
        outgoing = links_by_source.get(tll_page.raw_path, set())
        for svc_cfg in config.services:
            canonical = registry.get_local_landing_page(
                tll_page.location, svc_cfg.slug
            )
            if canonical is None:
                continue
            if canonical.raw_path == tll_page.raw_path:
                continue
            if canonical.raw_path in outgoing:
                continue
            violations.append(
                Violation(
                    rule=f"{NAME}.missing_local_landing_link",
                    severity=SEVERITY,
                    source_url=tll_page.url,
                    page_type=tll_page.page_type,
                    expected=canonical.url,
                    actual=None,
                    message=(
                        f"Top-level location page does not link to its local "
                        f"landing {canonical.url}"
                    ),
                )
            )

    # 2. LOCAL_LANDING -> SUBSERVICE_LANDING for each (loc, svc, subsvc)
    for ll_page in registry.get_by_type(PageType.LOCAL_LANDING):
        if ll_page.location is None or ll_page.service is None:
            continue
        outgoing = links_by_source.get(ll_page.raw_path, set())
        landings = registry.get_subservice_landing_pages(
            ll_page.location, ll_page.service
        )
        seen_subservices: set[str] = set()
        for landing in landings:
            if landing.subservice is None:
                continue
            if landing.subservice in seen_subservices:
                continue  # first-wins for canonical dedup
            seen_subservices.add(landing.subservice)
            if landing.raw_path == ll_page.raw_path:
                continue
            if landing.raw_path in outgoing:
                continue
            violations.append(
                Violation(
                    rule=f"{NAME}.missing_subservice_landing_link",
                    severity=SEVERITY,
                    source_url=ll_page.url,
                    page_type=ll_page.page_type,
                    expected=landing.url,
                    actual=None,
                    message=(
                        f"Local landing page does not link to its subservice "
                        f"landing {landing.url}"
                    ),
                )
            )

    return violations
