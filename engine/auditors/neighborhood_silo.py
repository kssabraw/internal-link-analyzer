"""Auditor: neighborhood silo linking - neighborhood pages link sideways and down.

Per docs/sop.md section "Neighborhood Relationships":
> Neighborhood Page -> Related neighborhoods: Link to every other Neighborhood
> Page that shares the same parent location. No cap.
>
> Neighborhood Page -> Neighborhood Service Pages within this neighborhood:
> Link to every Neighborhood Service Page that exists for this neighborhood -
> i.e., every /[parent-location]/[this-neighborhood]/[service]/ page. Do not
> link from a neighborhood page to top-level service pages; the geographic
> relevance lives in the Neighborhood Service Pages.

Canonical-conflict handling: when multiple URLs classify to the same
identity tuple, only the first (canonical) is required.
"""

from __future__ import annotations

from collections import defaultdict

import pandas as pd

from engine.classifier import PageType
from engine.config import ClientConfig
from engine.registry import SiteRegistry
from engine.violations import Severity, Violation

NAME = "neighborhood_silo"
SEVERITY = Severity.WARNING


def run(
    registry: SiteRegistry,
    links_df: pd.DataFrame,
    config: ClientConfig,
) -> list[Violation]:
    """Check every neighborhood links to its siblings and its neighborhood services."""
    links_by_source: dict[str, set[str]] = defaultdict(set)
    for source, target in zip(
        links_df["source_url"], links_df["target_url"], strict=True
    ):
        links_by_source[source].add(target)

    violations: list[Violation] = []

    for nb_page in registry.get_by_type(PageType.NEIGHBORHOOD):
        if nb_page.location is None or nb_page.neighborhood is None:
            continue
        outgoing = links_by_source.get(nb_page.raw_path, set())

        # Rule 1: sibling neighborhoods (same parent location)
        sibling_pages = registry.get_neighborhoods_for_location(
            nb_page.location
        )
        seen_neighborhoods: set[str] = set()
        for sibling in sibling_pages:
            if sibling.neighborhood is None:
                continue
            if sibling.neighborhood == nb_page.neighborhood:
                continue
            if sibling.neighborhood in seen_neighborhoods:
                continue
            seen_neighborhoods.add(sibling.neighborhood)
            canonical = registry.get_neighborhood(
                nb_page.location, sibling.neighborhood
            )
            if canonical is None:
                continue
            if canonical.raw_path == nb_page.raw_path:
                continue
            if canonical.raw_path in outgoing:
                continue
            violations.append(
                Violation(
                    rule=f"{NAME}.missing_sibling_neighborhood_link",
                    severity=SEVERITY,
                    source_url=nb_page.url,
                    page_type=nb_page.page_type,
                    expected=canonical.url,
                    actual=None,
                    message=(
                        f"Neighborhood page does not link to its sibling "
                        f"neighborhood {canonical.url}"
                    ),
                )
            )

        # Rule 2: neighborhood service pages within this neighborhood
        nb_services = registry.get_neighborhood_service_pages(
            nb_page.location, nb_page.neighborhood
        )
        seen_services: set[str] = set()
        for nb_svc in nb_services:
            if nb_svc.service is None:
                continue
            if nb_svc.service in seen_services:
                continue
            seen_services.add(nb_svc.service)
            if nb_svc.raw_path == nb_page.raw_path:
                continue
            if nb_svc.raw_path in outgoing:
                continue
            violations.append(
                Violation(
                    rule=f"{NAME}.missing_neighborhood_service_link",
                    severity=SEVERITY,
                    source_url=nb_page.url,
                    page_type=nb_page.page_type,
                    expected=nb_svc.url,
                    actual=None,
                    message=(
                        f"Neighborhood page does not link to its neighborhood "
                        f"service page {nb_svc.url}"
                    ),
                )
            )

    return violations
