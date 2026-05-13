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

# Silo violations produce straightforward per-page "add this link" rows.
_SILO_RULE_PREFIXES = (
    "service_silo.missing",
    "location_silo.missing",
    "neighborhood_silo.missing",
)

# Sentinel values used in CSV columns for non-"add link" actions, so a reader
# can sort/filter the file and still understand what to do.
_REDIRECT_ANCHOR = "(server-side 301 redirect)"
_CREATE_PAGE_PLACEHOLDER = "(create new page)"
_REMOVE_LINKS_PLACEHOLDER = "(reduce links — see why)"
_ADD_FROM_HIGHER_PLACEHOLDER = "(add a link to this page from a higher-level page)"


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
    """One-line plain-English explanation of the action."""
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
    if rule.startswith("canonical_conflicts.duplicate_"):
        return (
            "URL duplicates a canonical page — 301-redirect to the canonical "
            "to consolidate ranking signals and stop splitting link equity"
        )
    if rule.endswith("_page_missing"):
        return (
            "Site has no canonical page for this universal-nav target — create "
            "one at the SOP default path, or add the actual path to "
            "path_aliases in config.yml"
        )
    if rule == "click_depth.exceeds_three_clicks":
        return (
            "Page is more than 3 clicks from home; add an internal link to it "
            "from a higher-level page (services hub, top-level service, or a "
            "well-linked blog post) to flatten depth"
        )
    if rule == "click_depth.unreachable":
        return (
            "Page has no incoming internal links; add one from a logical "
            "parent or 301-redirect/delete if obsolete"
        )
    if rule == "blog_link_budget.too_many_service_links":
        return (
            "Blog post links to more than one service page — SOP allows "
            "exactly one. Remove all but the most relevant service link"
        )
    if rule == "blog_link_budget.too_many_silo_blog_links":
        return (
            "Blog post links to too many other blog posts — reduce to the "
            "SOP cap of related-post links"
        )
    if rule == "blog_link_budget.too_few_silo_blog_links":
        return (
            "Blog post has too few related-post links — add internal links "
            "to relevant sibling blog posts up to the SOP minimum"
        )
    if rule == "blog_link_budget.missing_service_link":
        return (
            "Blog post does not link to any service page — add exactly one "
            "service link relevant to the post topic"
        )
    return rule


def _format_canonical_action(v: Violation) -> dict[str, str] | None:
    """A canonical-conflict violation becomes a redirect action.

    `source_url` is the duplicate URL; `expected` is the canonical to redirect to.
    """
    if v.expected is None:
        return None
    return {
        "source_url": v.source_url,
        "target_url": v.expected,
        "anchor": _REDIRECT_ANCHOR,
        "rule": v.rule,
        "explanation": _rule_explanation(v.rule),
    }


def _format_missing_page_action(v: Violation) -> dict[str, str]:
    """A universal_nav `_page_missing` violation becomes a 'create this page' action."""
    return {
        "source_url": _CREATE_PAGE_PLACEHOLDER,
        "target_url": v.expected or "",
        "anchor": "",
        "rule": v.rule,
        "explanation": _rule_explanation(v.rule),
    }


def _format_click_depth_action(v: Violation) -> dict[str, str]:
    """A click_depth violation becomes an 'add a link from a higher-level page' action."""
    return {
        "source_url": _ADD_FROM_HIGHER_PLACEHOLDER,
        "target_url": v.source_url,
        "anchor": "",
        "rule": v.rule,
        "explanation": _rule_explanation(v.rule),
    }


def _format_blog_budget_action(v: Violation) -> dict[str, str]:
    """A blog_link_budget violation becomes a 'review the link mix on this post' action."""
    if v.rule.startswith("blog_link_budget.too_many"):
        target = _REMOVE_LINKS_PLACEHOLDER
        anchor = ""
    elif v.rule == "blog_link_budget.missing_service_link":
        target = "(add one relevant service link)"
        anchor = ""
    else:
        target = "(add related-post links up to SOP minimum)"
        anchor = ""
    return {
        "source_url": v.source_url,
        "target_url": target,
        "anchor": anchor,
        "rule": v.rule,
        "explanation": _rule_explanation(v.rule),
    }


def write_action_list(
    md_path: Path,
    csv_path: Path,
    *,
    violations: list[Violation],
    registry: SiteRegistry,
    config: ClientConfig,
) -> None:
    """Write action_list.md and action_list.csv from auditor violations.

    Action categories:
    - Silo (`service_silo.*`, `location_silo.*`, `neighborhood_silo.*`) →
      "edit page X, add link to Y."
    - Canonical conflicts (`canonical_conflicts.duplicate_*`) →
      "301-redirect this URL to the canonical."
    - Universal-nav missing pages (`universal_nav.*_page_missing`) →
      "create this canonical page."
    - Click depth (`click_depth.exceeds_three_clicks`, `.unreachable`) →
      "add an incoming link to this page from a higher-level page."
    - Blog link budget (`blog_link_budget.*`) →
      "reduce / add blog-post links to meet the SOP budget."
    """
    silo_items: list[dict[str, str]] = []
    redirect_items: list[dict[str, str]] = []
    create_page_items: list[dict[str, str]] = []
    click_depth_items: list[dict[str, str]] = []
    blog_budget_items: list[dict[str, str]] = []

    for v in violations:
        if any(v.rule.startswith(p) for p in _SILO_RULE_PREFIXES):
            target = (
                registry.get_by_url(v.expected)
                if v.expected is not None
                else None
            )
            silo_items.append(
                {
                    "source_url": v.source_url,
                    "target_url": v.expected or "",
                    "anchor": _suggested_anchor(target, config),
                    "rule": v.rule,
                    "explanation": _rule_explanation(v.rule),
                }
            )
        elif v.rule.startswith("canonical_conflicts.duplicate_"):
            row = _format_canonical_action(v)
            if row is not None:
                redirect_items.append(row)
        elif v.rule.endswith("_page_missing") and v.rule.startswith(
            "universal_nav."
        ):
            create_page_items.append(_format_missing_page_action(v))
        elif v.rule in (
            "click_depth.exceeds_three_clicks",
            "click_depth.unreachable",
        ):
            click_depth_items.append(_format_click_depth_action(v))
        elif v.rule.startswith("blog_link_budget."):
            blog_budget_items.append(_format_blog_budget_action(v))

    # `items` is the unified action stream that drives the CSV (in
    # priority order) and the per-page Markdown sections.
    items: list[dict[str, str]] = (
        create_page_items
        + redirect_items
        + silo_items
        + click_depth_items
        + blog_budget_items
    )

    # Unreachable pages also surface in a separate Markdown section so the
    # human reviewer sees them as a list, not just buried in click_depth rows.
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
        "_Punch list of internal-linking work. Each row in `action_list.csv` "
        "is one action: edit a page, redirect a URL, create a missing page, "
        "or rebalance a blog post's outbound links._"
    )
    out("")
    out("## How to use")
    out("")
    out(
        "1. Open `action_list.csv` in Excel - it has the same data, sortable."
    )
    out(
        "2. Work top-down: create missing canonical pages first, then "
        "redirects, then add missing internal links, then prune blog posts."
    )
    out("3. Use the suggested anchor text exactly when possible.")
    out("4. Check off each item as you go.")
    out("")
    out(
        f"**Total actions:** {len(items)}  "
        f"**Pages / sources affected:** {len(by_source)}"
    )
    out("")

    # Category breakdown so reviewers can see the shape at a glance.
    category_counts: list[tuple[str, int]] = [
        ("Create missing canonical pages", len(create_page_items)),
        ("Redirect canonical-conflict duplicates", len(redirect_items)),
        ("Add missing silo links", len(silo_items)),
        ("Fix click-depth (add incoming links)", len(click_depth_items)),
        ("Rebalance blog-post outbound links", len(blog_budget_items)),
    ]
    if any(n for _, n in category_counts):
        out("## Action categories")
        out("")
        out("| Category | Count |")
        out("|---|---:|")
        for name, n in category_counts:
            if n:
                out(f"| {name} | {n:,} |")
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
