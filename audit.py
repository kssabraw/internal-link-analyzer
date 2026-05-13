"""CLI entry point for the internal link audit engine."""

import csv
from pathlib import Path

import click

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
