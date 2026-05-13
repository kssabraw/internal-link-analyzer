"""Auditor: no page should link to the same target URL more than once.

Per docs/sop.md "Global Rules":
> Never link to the same page twice on the same page. Google generally counts
> only the first link's anchor text, so a duplicate link with different anchor
> is wasted.

The Website Auditor export does not distinguish nav / footer / body link
regions, so a universal-nav target that legitimately appears in both nav and
footer would otherwise produce 1000+ false positives. To suppress that noise,
when all anchor texts for a (source, target) pair match a small allowlist of
UI-functional anchors ("Home", "Contact Us", etc.), the duplicate is treated
as expected nav/footer duplication and skipped. If any anchor in the group
falls outside the allowlist, the duplicate fires - those are the body-content
duplicates the SOP rule is actually targeting.
"""

from __future__ import annotations

from collections import defaultdict

import pandas as pd

from engine.config import ClientConfig
from engine.registry import SiteRegistry
from engine.violations import Severity, Violation

NAME = "duplicate_links"
SEVERITY = Severity.WARNING

# Anchors that are typically nav / footer UI elements. If every duplicate
# uses one of these, the duplication is expected (nav + footer cohabit).
_UI_ANCHORS: frozenset[str] = frozenset(
    {
        "home",
        "homepage",
        "about",
        "about us",
        "contact",
        "contact us",
        "contact wheelhouse it",
        "privacy",
        "privacy policy",
        "blog",
        "services",
        "all services",
        "service areas",
        "areas we serve",
        "menu",
        "sitemap",
        "search",
        "login",
        "client login",
        "support",
        "request a quote",
        "get a quote",
        "free consultation",
        "schedule a consultation",
    }
)


def _normalize_anchor(anchor: str | float | None) -> str:
    """Lowercase, collapse internal whitespace. Empty / null becomes ''."""
    if anchor is None or (isinstance(anchor, float) and pd.isna(anchor)):
        return ""
    return " ".join(str(anchor).strip().lower().split())


def _all_ui_anchors(anchors: list[str]) -> bool:
    """True iff every anchor (after normalization) is empty or in the UI allowlist."""
    return all(a == "" or a in _UI_ANCHORS for a in anchors)


def run(
    registry: SiteRegistry,
    links_df: pd.DataFrame,
    config: ClientConfig,
) -> list[Violation]:
    """Emit one Violation per (source, target) pair that appears 2+ times.

    Sources that don't match a classified page are skipped (we only audit
    pages we actually classified). Pairs where all duplicate anchors are
    universal-nav UI strings are skipped (nav + footer duplication is
    expected and architecturally intentional).
    """
    classified = {p.raw_path: p for p in registry.all_pages()}

    pair_anchors: dict[tuple[str, str], list[str]] = defaultdict(list)
    for source, target, anchor in zip(
        links_df["source_url"],
        links_df["target_url"],
        links_df["anchor_text"],
        strict=True,
    ):
        if source not in classified:
            continue
        pair_anchors[(source, target)].append(_normalize_anchor(anchor))

    violations: list[Violation] = []
    for (source, target), anchors in pair_anchors.items():
        if len(anchors) < 2:
            continue
        if _all_ui_anchors(anchors):
            continue
        page = classified[source]
        violations.append(
            Violation(
                rule=f"{NAME}.same_target_multiple_times",
                severity=SEVERITY,
                source_url=page.url,
                page_type=page.page_type,
                expected=f"1 link to {target}",
                actual=f"{len(anchors)} links to {target}",
                message=(
                    f"Page links to {target} {len(anchors)} times; "
                    f"Google counts only the first anchor"
                ),
            )
        )
    return violations
