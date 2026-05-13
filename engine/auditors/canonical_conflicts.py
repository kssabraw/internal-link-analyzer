"""Auditor: detect URLs that resolve to identical PageClassifications.

Per docs/sop.md "Avoiding Duplicate Content":
> A well-organized site architecture minimizes the risk of duplicate content
> issues. By using canonical tags and properly structuring your URLs, you
> help Google identify the original and most authoritative version of each
> page, preventing the dilution of link equity and potential ranking issues.

Two pages with the same (page_type, location, service, subservice,
neighborhood, bio_name, blog_slug) tuple are flagged as canonical conflicts.
The first page in each cluster is treated as the canonical; subsequent pages
emit a Violation with `expected` pointing to the canonical URL.
"""

from __future__ import annotations

import pandas as pd

from engine.config import ClientConfig
from engine.registry import SiteRegistry
from engine.violations import Severity, Violation

NAME = "canonical_conflicts"
SEVERITY = Severity.WARNING


def run(
    registry: SiteRegistry,
    links_df: pd.DataFrame,
    config: ClientConfig,
) -> list[Violation]:
    """Emit a Violation per duplicate URL within each canonical-conflict cluster."""
    violations: list[Violation] = []
    for cluster in registry.get_canonical_conflicts():
        canonical = cluster[0]
        for duplicate in cluster[1:]:
            violations.append(
                Violation(
                    rule=f"{NAME}.duplicate_{duplicate.page_type.value}",
                    severity=SEVERITY,
                    source_url=duplicate.url,
                    page_type=duplicate.page_type,
                    expected=canonical.url,
                    actual=duplicate.url,
                    message=(
                        f"URL classifies identically to {canonical.url}; "
                        f"consider canonicalizing to it"
                    ),
                )
            )
    return violations
