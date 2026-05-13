"""CLI entry point for the internal link audit engine."""

import csv
from pathlib import Path

import click

from engine.action_list import write_action_list
from engine.auditors import ALL_AUDITORS
from engine.classifier import (
    PageClassification,
    PageType,
    classify_all,
    read_urls,
)
from engine.config import ClientConfig, load as load_config
from engine.links import read_links
from engine.registry import SiteRegistry
from engine.violations import Severity, Violation

LOW_CONFIDENCE_THRESHOLD = 0.7

_SEVERITY_ORDER = {Severity.CRITICAL: 0, Severity.WARNING: 1, Severity.INFO: 2}


@click.command()
@click.option(
    "--client",
    required=True,
    help="Client slug matching a folder under clients/",
)
@click.option(
    "--auditor", default=None, help="Run only this auditor (e.g. universal_nav)"
)
@click.option(
    "--classify-only", is_flag=True, help="Classify URLs only; skip auditors"
)
@click.option("--verbose", is_flag=True, help="Enable verbose logging")
def main(
    client: str, auditor: str | None, classify_only: bool, verbose: bool
) -> None:
    """Run the internal linking audit for a client."""
    client_dir = Path("clients") / client
    config = load_config(client_dir / "config.yml")

    if classify_only:
        _run_classify_only(client_dir, config, verbose)
        return

    _run_audit(client_dir, config, auditor, verbose)


def _run_audit(
    client_dir: Path,
    config: ClientConfig,
    auditor_name: str | None,
    verbose: bool,
) -> None:
    urls = read_urls(client_dir / "input")
    classifications, ignored = classify_all(urls, config)
    registry = SiteRegistry(classifications, config)
    links_df = read_links(client_dir / "input")

    if auditor_name is not None:
        selected = [a for a in ALL_AUDITORS if a.NAME == auditor_name]
        if not selected:
            known = ", ".join(a.NAME for a in ALL_AUDITORS)
            raise click.ClickException(
                f"Unknown auditor '{auditor_name}'. Known: {known}"
            )
    else:
        selected = list(ALL_AUDITORS)

    all_violations: list[Violation] = []
    skipped: list[str] = []
    for auditor in selected:
        try:
            violations = auditor.run(registry, links_df, config)
        except NotImplementedError:
            skipped.append(auditor.NAME)
            if verbose:
                print(f"{auditor.NAME}: not implemented yet (skipped)")
            continue
        print(f"{auditor.NAME}: {len(violations)} violations")
        all_violations.extend(violations)

    output_dir = client_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_violations(output_dir / "violations.csv", all_violations)
    write_action_list(
        output_dir / "action_list.md",
        output_dir / "action_list.csv",
        violations=all_violations,
        registry=registry,
        config=config,
    )
    _write_summary(
        output_dir / "summary.md",
        config=config,
        urls=urls,
        classifications=classifications,
        ignored=ignored,
        links_df=links_df,
        registry=registry,
        violations=all_violations,
        skipped=skipped,
        auditor_filter=auditor_name,
    )

    print(
        f"\nClassified: {len(classifications)}  "
        f"Ignored: {len(ignored)}  "
        f"Links: {len(links_df)}  "
        f"Total violations: {len(all_violations)}"
    )
    if skipped:
        print(f"Skipped (not yet implemented): {', '.join(skipped)}")


def _run_classify_only(
    client_dir: Path, config: ClientConfig, verbose: bool
) -> None:
    urls = read_urls(client_dir / "input")
    classifications, ignored = classify_all(urls, config)

    output_dir = client_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    _write_classifications(output_dir / "classifications.csv", classifications)
    review = [
        c
        for c in classifications
        if c.page_type == PageType.UNKNOWN or c.confidence < LOW_CONFIDENCE_THRESHOLD
    ]
    _write_review(output_dir / "unclassified_urls.csv", review)

    registry = SiteRegistry(classifications, config)
    _write_registry_summary(output_dir / "registry_summary.csv", registry)

    conflict_clusters = len(registry.get_canonical_conflicts())
    print(f"URLs read:       {len(urls)}")
    print(f"Classified:      {len(classifications)}")
    print(f"Ignored:         {len(ignored)}")
    print(f"For review:      {len(review)}")
    print(f"Conflict clusters: {conflict_clusters}")
    if verbose:
        unknowns = sum(1 for c in classifications if c.page_type == PageType.UNKNOWN)
        low_conf = len(review) - unknowns
        print(f"  - UNKNOWN:     {unknowns}")
        print(f"  - low confidence (< {LOW_CONFIDENCE_THRESHOLD}): {low_conf}")


def _write_classifications(
    path: Path, classifications: list[PageClassification]
) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "url",
                "page_type",
                "location",
                "service",
                "subservice",
                "neighborhood",
                "confidence",
            ]
        )
        for c in classifications:
            writer.writerow(
                [
                    c.url,
                    c.page_type.value,
                    c.location or "",
                    c.service or "",
                    c.subservice or "",
                    c.neighborhood or "",
                    f"{c.confidence:.2f}",
                ]
            )


def _write_review(path: Path, review: list[PageClassification]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["url", "page_type", "raw_path", "confidence", "reason"])
        for c in review:
            reason = (
                "unknown" if c.page_type == PageType.UNKNOWN else "low_confidence"
            )
            writer.writerow(
                [c.url, c.page_type.value, c.raw_path, f"{c.confidence:.2f}", reason]
            )


def _write_violations(path: Path, violations: list[Violation]) -> None:
    """Write violations.csv sorted by severity, then page_type, then rule, then url."""
    ordered = sorted(
        violations,
        key=lambda v: (
            _SEVERITY_ORDER[v.severity],
            v.page_type.value,
            v.rule,
            v.source_url,
        ),
    )
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "rule",
                "severity",
                "source_url",
                "page_type",
                "expected",
                "actual",
                "message",
            ]
        )
        for v in ordered:
            writer.writerow(
                [
                    v.rule,
                    v.severity.value,
                    v.source_url,
                    v.page_type.value,
                    v.expected or "",
                    v.actual or "",
                    v.message,
                ]
            )


def _write_summary(
    path: Path,
    *,
    config: ClientConfig,
    urls: list[str],
    classifications: list[PageClassification],
    ignored: list[str],
    links_df,  # pandas DataFrame; avoid pd import in signature
    registry: SiteRegistry,
    violations: list[Violation],
    skipped: list[str],
    auditor_filter: str | None,
) -> None:
    """Write a human-readable summary.md report.

    Layout: pipeline stats, classification mix, severity / auditor / rule
    breakdowns, top-N most-violating pages, top-N most-common rules,
    sitewide findings (rules that fire on essentially every page), and
    recommended priorities.
    """
    from collections import Counter
    from datetime import datetime

    n_pages = len(classifications)
    by_type: Counter[PageType] = Counter(c.page_type for c in classifications)
    by_severity = Counter(v.severity for v in violations)
    by_auditor: Counter[str] = Counter(v.rule.split(".", 1)[0] for v in violations)
    by_rule = Counter(v.rule for v in violations)
    by_source = Counter(v.source_url for v in violations)
    conflict_clusters = len(registry.get_canonical_conflicts())

    # Sitewide rules: fire on every classified page (>= n_pages, accounting for
    # self-exemption which can drop by 1).
    sitewide_rules = [
        (rule, count)
        for rule, count in by_rule.most_common()
        if n_pages and count >= n_pages - 1 and not rule.startswith("duplicate_links")
    ]

    lines: list[str] = []
    a = lines.append

    a(f"# Internal Linking Audit Report — {config.client}")
    a("")
    a(
        f"_Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} "
        f"for `{config.domain}`._"
    )
    if auditor_filter:
        a("")
        a(f"> Filtered to auditor `{auditor_filter}` only.")
    a("")
    a("## Pipeline summary")
    a("")
    a("| Stage | Result |")
    a("|---|---:|")
    a(f"| URLs read | {len(urls):,} |")
    a(f"| Classified | {n_pages:,} |")
    a(f"| Ignored (per `url_patterns_to_ignore`) | {len(ignored):,} |")
    a(f"| Internal links analyzed | {len(links_df):,} |")
    a(f"| Canonical conflict clusters | {conflict_clusters} |")
    a(f"| **Total violations** | **{len(violations):,}** |")
    if skipped:
        a(f"| Auditors skipped (not implemented) | {', '.join(skipped)} |")
    a("")

    a("## Classification breakdown")
    a("")
    a("| Page type | Count |")
    a("|---|---:|")
    for pt, n in sorted(by_type.items(), key=lambda kv: -kv[1]):
        a(f"| `{pt.value}` | {n:,} |")
    a("")

    a("## Violations by severity")
    a("")
    a("| Severity | Count |")
    a("|---|---:|")
    for sev in (Severity.CRITICAL, Severity.WARNING, Severity.INFO):
        n = by_severity.get(sev, 0)
        if n:
            a(f"| {sev.value} | {n:,} |")
    a("")

    a("## Violations by auditor")
    a("")
    a("| Auditor | Violations |")
    a("|---|---:|")
    for auditor in sorted(
        {a_.NAME for a_ in ALL_AUDITORS}, key=lambda n: -by_auditor.get(n, 0)
    ):
        n = by_auditor.get(auditor, 0)
        a(f"| `{auditor}` | {n:,} |")
    a("")

    a("## Violations by rule")
    a("")
    a("| Rule | Severity | Count |")
    a("|---|---|---:|")
    rule_severity = {v.rule: v.severity for v in violations}
    for rule, n in by_rule.most_common():
        a(f"| `{rule}` | {rule_severity[rule].value} | {n:,} |")
    a("")

    if sitewide_rules:
        a("## Sitewide structural findings")
        a("")
        a(
            "Rules that fire on essentially every classified page indicate a "
            "structural / template-level issue rather than per-page problems "
            "to fix one-by-one. Address these first."
        )
        a("")
        a("| Rule | Pages affected |")
        a("|---|---:|")
        for rule, count in sitewide_rules:
            a(f"| `{rule}` | {count:,} |")
        a("")

    top_n = 15
    if by_source:
        a(f"## Top {top_n} most-violating pages")
        a("")
        a("| Violations | Page |")
        a("|---:|---|")
        for src, n in by_source.most_common(top_n):
            a(f"| {n:,} | `{src}` |")
        a("")

    a("## Recommended priorities")
    a("")
    a("Suggested order of attack, highest signal-to-effort first:")
    a("")
    priorities: list[str] = []

    if sitewide_rules:
        priorities.append(
            "**Fix the sitewide structural issues** listed above first — "
            "each one resolved drops violations by the page count in one move."
        )
    if conflict_clusters:
        priorities.append(
            f"**Consolidate the {conflict_clusters} canonical-conflict clusters** "
            "(see `canonical_conflicts.duplicate_*` rows in `violations.csv`). "
            "Duplicate URLs that classify identically also inflate `service_silo`, "
            "`location_silo`, and `click_depth` counts — fixing them cascades."
        )
    unreachable = by_rule.get("click_depth.unreachable", 0)
    if unreachable:
        priorities.append(
            f"**Restore internal links to the {unreachable} unreachable pages** "
            "(see `click_depth.unreachable` in `violations.csv`). These can't "
            "be crawled at all via site navigation."
        )
    silo_total = sum(
        n for r, n in by_rule.items() if "silo.missing" in r
    )
    if silo_total:
        priorities.append(
            f"**Fix the {silo_total:,} silo-linking gaps** "
            "(`service_silo.*`, `location_silo.*`, `neighborhood_silo.*`). "
            "These are the core SOP rules for parent→child link coverage."
        )
    duplicate_count = by_rule.get(
        "duplicate_links.same_target_multiple_times", 0
    )
    if duplicate_count > 1000:
        priorities.append(
            f"**Review the {duplicate_count:,} `duplicate_links` violations** — "
            "this typically indicates mega-footer template duplication. "
            "Consider reducing footer link density or extending the UI-anchor "
            "allowlist in the auditor."
        )

    if not priorities:
        priorities.append(
            "No major structural issues found. Audit per-page violations in "
            "`violations.csv` for fine-tuning."
        )

    for i, p in enumerate(priorities, 1):
        a(f"{i}. {p}")
    a("")
    a("---")
    a("")
    a(
        "_See `violations.csv` for the full per-violation list and "
        "`registry_summary.csv` for the classification index._"
    )

    path.write_text("\n".join(lines), encoding="utf-8")


def _write_registry_summary(path: Path, registry: SiteRegistry) -> None:
    type_counts: dict[PageType, int] = {
        pt: len(registry.get_by_type(pt)) for pt in PageType
    }
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["page_type", "count"])
        for pt in PageType:
            count = type_counts[pt]
            if count > 0:
                writer.writerow([pt.value, count])
        writer.writerow(
            ["canonical_conflict_clusters", len(registry.get_canonical_conflicts())]
        )


if __name__ == "__main__":
    main()
