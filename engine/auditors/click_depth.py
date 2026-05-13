"""Auditor: every commercial page must be reachable from home in <=3 clicks.

Per docs/sop.md section "Click-Depth Target":
> All commercial pages - service pages, location pages, local landing pages,
> neighborhood pages, and their third-level descendants - must be reachable
> from the homepage in 3 clicks or fewer.
>
> Blog posts are exempt.

BFS over the internal-links graph from the homepage. Pages that exceed depth
3 emit a WARNING; pages unreachable from home emit a CRITICAL (a page no
crawler can find via internal links is materially worse than a deep page).
"""

from __future__ import annotations

from collections import defaultdict, deque

import pandas as pd

from engine.classifier import PageType
from engine.config import ClientConfig
from engine.registry import SiteRegistry
from engine.violations import Severity, Violation

NAME = "click_depth"
SEVERITY = Severity.WARNING  # default; .unreachable overrides to CRITICAL

MAX_DEPTH = 3

# Commercial pages subject to the click-depth rule, per SOP.
_COMMERCIAL_PAGE_TYPES: frozenset[PageType] = frozenset(
    {
        PageType.TOP_LEVEL_SERVICE,
        PageType.SUB_SERVICE,
        PageType.TOP_LEVEL_LOCATION,
        PageType.LOCAL_LANDING,
        PageType.NEIGHBORHOOD,
        PageType.SUBSERVICE_LANDING,
        PageType.NEIGHBORHOOD_SERVICE,
    }
)


def _bfs_depths(home_path: str, links_df: pd.DataFrame) -> dict[str, int]:
    """Return {path: shortest depth from home_path} for every reachable path."""
    outgoing: dict[str, list[str]] = defaultdict(list)
    for source, target in zip(
        links_df["source_url"], links_df["target_url"], strict=True
    ):
        outgoing[source].append(target)

    depths: dict[str, int] = {home_path: 0}
    queue: deque[str] = deque([home_path])
    while queue:
        current = queue.popleft()
        next_depth = depths[current] + 1
        for target in outgoing.get(current, ()):
            if target in depths:
                continue
            depths[target] = next_depth
            queue.append(target)
    return depths


def run(
    registry: SiteRegistry,
    links_df: pd.DataFrame,
    config: ClientConfig,
) -> list[Violation]:
    """Emit a Violation for every commercial page that exceeds 3 clicks or is unreachable."""
    homes = registry.get_by_type(PageType.HOME)
    if not homes:
        return []  # no home -> can't compute depth; universal_nav flags missing home
    home_path = homes[0].raw_path

    depths = _bfs_depths(home_path, links_df)

    violations: list[Violation] = []
    for page in registry.all_pages():
        if page.page_type not in _COMMERCIAL_PAGE_TYPES:
            continue
        if page.raw_path == home_path:
            continue

        if page.raw_path not in depths:
            violations.append(
                Violation(
                    rule=f"{NAME}.unreachable",
                    severity=Severity.CRITICAL,
                    source_url=page.url,
                    page_type=page.page_type,
                    expected=f"reachable from home within {MAX_DEPTH} clicks",
                    actual="unreachable from home via internal links",
                    message=(
                        "Page is unreachable from the homepage; no internal "
                        "link path exists"
                    ),
                )
            )
            continue

        depth = depths[page.raw_path]
        if depth > MAX_DEPTH:
            violations.append(
                Violation(
                    rule=f"{NAME}.exceeds_three_clicks",
                    severity=Severity.WARNING,
                    source_url=page.url,
                    page_type=page.page_type,
                    expected=f"<= {MAX_DEPTH} clicks from home",
                    actual=f"{depth} clicks from home",
                    message=(
                        f"Page is {depth} clicks from the homepage "
                        f"(SOP max is {MAX_DEPTH})"
                    ),
                )
            )

    return violations
