"""Auditor: service silo linking - service pages must link down to all their landings.

Per docs/sop.md section "Service Silo (Downward Links From Service Pages)":
> Top-Level Service Page -> Related Local Landing Pages: Link to every Local
> Landing Page that uses this service - i.e., every /[location]/[this-service]/
> page on the site. No cap. Do not link to Subservice Landing Pages (deeper
> than one level down).
>
> Sub-Service Page -> Related Subservice Landing Pages: Link to every
> Subservice Landing Page that uses this subservice - i.e., every
> /[location]/[parent-service]/[this-subservice]/ page on the site. No cap.

Canonical-conflict handling: when multiple URLs classify to the same
(location, service) tuple, only the first (canonical) is required. The
canonical_conflicts auditor reports the duplicates separately.
"""

from __future__ import annotations

from collections import defaultdict

import pandas as pd

from engine.classifier import PageType
from engine.config import ClientConfig
from engine.registry import SiteRegistry
from engine.violations import Severity, Violation

NAME = "service_silo"
SEVERITY = Severity.CRITICAL


def run(
    registry: SiteRegistry,
    links_df: pd.DataFrame,
    config: ClientConfig,
) -> list[Violation]:
    """Check every service page links to all its expected child landings."""
    links_by_source: dict[str, set[str]] = defaultdict(set)
    for source, target in zip(
        links_df["source_url"], links_df["target_url"], strict=True
    ):
        links_by_source[source].add(target)

    violations: list[Violation] = []

    # 1. TOP_LEVEL_SERVICE -> LOCAL_LANDING for each location with one
    for svc_page in registry.get_by_type(PageType.TOP_LEVEL_SERVICE):
        if svc_page.service is None:
            continue
        outgoing = links_by_source.get(svc_page.raw_path, set())
        for loc_cfg in config.locations:
            canonical = registry.get_local_landing_page(
                loc_cfg.slug, svc_page.service
            )
            if canonical is None:
                continue
            if canonical.raw_path == svc_page.raw_path:
                continue
            if canonical.raw_path in outgoing:
                continue
            violations.append(
                Violation(
                    rule=f"{NAME}.missing_local_landing_link",
                    severity=SEVERITY,
                    source_url=svc_page.url,
                    page_type=svc_page.page_type,
                    expected=canonical.url,
                    actual=None,
                    message=(
                        f"Top-level service page does not link to its local "
                        f"landing {canonical.url}"
                    ),
                )
            )

    # 2. SUB_SERVICE -> SUBSERVICE_LANDING for each location with one
    for sub_page in registry.get_by_type(PageType.SUB_SERVICE):
        if sub_page.service is None or sub_page.subservice is None:
            continue
        outgoing = links_by_source.get(sub_page.raw_path, set())
        for loc_cfg in config.locations:
            landings = registry.get_subservice_landing_pages(
                loc_cfg.slug, sub_page.service
            )
            canonical = next(
                (p for p in landings if p.subservice == sub_page.subservice),
                None,
            )
            if canonical is None:
                continue
            if canonical.raw_path == sub_page.raw_path:
                continue
            if canonical.raw_path in outgoing:
                continue
            violations.append(
                Violation(
                    rule=f"{NAME}.missing_subservice_landing_link",
                    severity=SEVERITY,
                    source_url=sub_page.url,
                    page_type=sub_page.page_type,
                    expected=canonical.url,
                    actual=None,
                    message=(
                        f"Sub-service page does not link to its subservice "
                        f"landing {canonical.url}"
                    ),
                )
            )

    return violations
