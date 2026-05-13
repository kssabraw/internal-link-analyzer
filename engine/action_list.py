"""Generate a staff-ready punch list of internal links to add.

Reads silo-auditor violations and turns them into 'edit this page, add this
link, use this anchor text' action items grouped by source page. Designed
to be handed to a junior SEO or web dev for execution.

Anchor-text suggestions follow docs/sop.md "Anchor Text Conventions":
- Sibling and child links: exact-match keyword for the target page's
  primary topic (service + location for landings, neighborhood name
  for neighborhoods, etc.).
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from engine.classifier import PageType
from engine.config import ClientConfig
from engine.registry import SiteRegistry
from engine.violations import Violation

# Only silo violations produce per-page "add this link" action items.
# click_depth.unreachable requires judgment about where to link from
# (separate section in the report).
_ACTION_RULE_PREFIXES = (
    "service_silo.missing",
    "location_silo.missing",
    "neighborhood_silo.missing",
)


def _service_display(slug: str | None, config: ClientConfig) -> str:
    if slug is None:
        return ""
    for svc in config.services:
        if svc.slug == slug:
            return svc.display
    for sub in config.subservices:
        if sub.slug == slug:
            return sub.display
    return slug


def _location_display(slug: str | None, config: ClientConfig) -> str:
    if slug is None:
        return ""
    for loc in config.locations:
        if loc.slug == slug:
            return loc.display
    return slug


def _neighborhood_display(
    location_slug: str | None,
    neighborhood_slug: str | None,
    config: ClientConfig,
) -> str:
    if location_slug is None or neighborhood_slug is None:
        return ""
    for loc in config.locations:
        if loc.slug == location_slug:
            for nb in loc.neighborhoods:
                if nb.slug == neighborhood_slug:
                    return nb.display or nb.slug
    return neighborhood_slug


def _suggested_anchor(target, config: ClientConfig) -> str:
    """Per SOP anchor conventions: exact-match keyword anchor for child links."""
    if target is None:
        return ""
    pt = target.page_type
    if pt == PageType.LOCAL_LANDING:
        svc = _service_display(target.service, config)
        loc = _location_display(target.location, config)
        return f"{svc} {loc}".strip()
    if pt == PageType.SUBSERVICE_LANDING:
        svc = _service_display(target.service, config)
        loc = _location_display(target.location, config)
        sub = _service_display(target.subservice, config)
        return f"{sub} {svc} {loc}".strip()
    if pt == PageType.NEIGHBORHOOD:
        return _neighborhood_display(
            target.location, target.neighborhood, config
        )
    if pt == PageType.NEIGHBORHOOD_SERVICE:
        svc = _service_display(target.service, config)
        nb = _neighborhood_display(
            target.location, target.neighborhood, config
        )
        return f"{svc} {nb}".strip()
    if pt == PageType.TOP_LEVEL_SERVICE:
        return _service_display(target.service, config)
    if pt == PageType.TOP_LEVEL_LOCATION:
        return _location_display(target.location, config)
    if pt == PageType.SUB_SERVICE:
        svc = _service_display(target.service, config)
        sub = _service_display(target.subservice, config)
        return f"{sub} {svc}".strip()
    return ""


def _rule_explanation(rule: str) -> str:
    """One-line plain-English explanation of why this link is needed."""
    if rule == "service_silo.missing_local_landing_link":
        return "Service page should link down to each city/location landing for this service"
    if rule == "service_silo.missing_subservice_landing_link":
        return "Sub-service page should link down to each location's subservice landing"
    if rule == "location_silo.missing_local_landing_link":
        return "Location page should link down to each service offered in this location"
    if rule == "location_silo.missing_subservice_landing_link":
        return "Local landing should link down to its subservice landings"
    if rule == "neighborhood_silo.missing_sibling_neighborhood_link":
        return "Neighborhood pages should link to their sibling neighborhoods (same parent city)"
    if rule == "neighborhood_silo.missing_neighborhood_service_link":
        return "Neighborhood page should link to each service offered in this neighborhood"
    return rule


def write_action_list(
    md_path: Path,
    csv_path: Path,
    *,
    violations: list[Violation],
    registry: SiteRegistry,
    config: ClientConfig,
) -> None:
    """Write action_list.md and action_list.csv from the silo violations."""
    items: list[dict[str, str]] = []
    for v in violations:
        if not any(v.rule.startswith(p) for p in _ACTION_RULE_PREFIXES):
            continue
        target = (
            registry.get_by_url(v.expected) if v.expected is not None else None
        )
        items.append(
            {
                "source_url": v.source_url,
                "target_url": v.expected or "",
                "anchor": _suggested_anchor(target, config),
                "rule": v.rule,
                "explanation": _rule_explanation(v.rule),
            }
        )

    # Unreachable pages (need links FROM somewhere TO them - no specific source)
    unreachable: list[str] = [
        v.source_url
        for v in violations
        if v.rule == "click_depth.unreachable"
    ]

    by_source: dict[str, list[dict[str, str]]] = defaultdict(list)
    for item in items:
        by_source[item["source_url"]].append(item)
    sorted_sources = sorted(
        by_source.keys(), key=lambda s: (-len(by_source[s]), s)
    )

    # ----- CSV -----
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "page_to_edit",
                "add_link_to",
                "suggested_anchor_text",
                "why",
                "rule_id",
            ]
        )
        for source in sorted_sources:
            for item in by_source[source]:
                writer.writerow(
                    [
                        item["source_url"],
                        item["target_url"],
                        item["anchor"],
                        item["explanation"],
                        item["rule"],
                    ]
                )

    # ----- Markdown -----
    lines: list[str] = []
    out = lines.append
    out(f"# Internal Linking Action List - {config.client}")
    out("")
    out(
        "_Punch list of internal links to add. Each item is "
        "'edit this page, add this link, use this anchor.'_"
    )
    out("")
    out("## How to use")
    out("")
    out(
        "1. Open `action_list.csv` in Excel - it has the same data, sortable."
    )
    out(
        "2. For each page below, log into the CMS, edit the page, add the "
        "missing link in the body content (or in a 'Service Areas' / "
        "'Related Services' component if you use one)."
    )
    out("3. Use the suggested anchor text exactly when possible.")
    out("4. Check off each item as you go.")
    out("")
    out(
        f"**Total pages needing work:** {len(by_source)}  "
        f"**Total links to add:** {len(items)}"
    )
    out("")
    out("---")
    out("")

    for source in sorted_sources:
        page_items = by_source[source]
        out(f"## {source}")
        out("")
        out(f"_{len(page_items)} link(s) to add to this page_")
        out("")
        out("| # | Add link to | Suggested anchor text |")
        out("|---|---|---|")
        for i, item in enumerate(page_items, 1):
            out(
                f"| {i} | `{item['target_url']}` | "
                f"{item['anchor']} |"
            )
        out("")

    if unreachable:
        out("---")
        out("")
        out("## Orphan pages (need to be linked from somewhere)")
        out("")
        out(
            f"These {len(unreachable)} pages exist but have no incoming links "
            f"from anywhere on the site. They can't be discovered by search "
            f"engines crawling your navigation."
        )
        out("")
        out(
            "**Action:** Decide if each page should still exist. If yes, add "
            "a link to it from a logical parent page (e.g. its top-level "
            "service or top-level location page). If no, delete the page or "
            "301-redirect it to the canonical URL."
        )
        out("")
        for i, url in enumerate(sorted(unreachable), 1):
            out(f"- [ ] {i}. `{url}`")
        out("")

    md_path.write_text("\n".join(lines), encoding="utf-8")
