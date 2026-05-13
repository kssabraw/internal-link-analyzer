"""CLI entry point for the internal link audit engine."""

import csv
from pathlib import Path

import click

from engine.classifier import (
    PageClassification,
    PageType,
    classify_all,
    read_urls,
)
from engine.config import load as load_config

LOW_CONFIDENCE_THRESHOLD = 0.7


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

    print("not implemented")


def _run_classify_only(client_dir: Path, config, verbose: bool) -> None:
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

    print(f"URLs read:       {len(urls)}")
    print(f"Classified:      {len(classifications)}")
    print(f"Ignored:         {len(ignored)}")
    print(f"For review:      {len(review)}")
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


if __name__ == "__main__":
    main()
