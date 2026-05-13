"""Tests for engine.auditors.neighborhood_silo."""

from pathlib import Path

import pandas as pd
import pytest

from engine.auditors import neighborhood_silo
from engine.classifier import PageClassification, PageType
from engine.config import (
    ClientConfig,
    LocationConfig,
    NeighborhoodConfig,
    ServiceConfig,
    load as load_config,
)
from engine.registry import SiteRegistry
from engine.violations import Severity

FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample_config.yml"


@pytest.fixture
def config() -> ClientConfig:
    """Sample config: los-angeles has neighborhoods=[los-feliz]."""
    return load_config(FIXTURE)


@pytest.fixture
def multi_neighborhood_config() -> ClientConfig:
    """Config with multiple neighborhoods so sibling tests have something to compare."""
    return ClientConfig(
        client="multi",
        domain="example.com",
        services=[
            ServiceConfig(slug="plumber", display="Plumber", aliases=[]),
            ServiceConfig(slug="electrician", display="Electrician", aliases=[]),
        ],
        locations=[
            LocationConfig(
                slug="los-angeles",
                display="LA",
                aliases=[],
                neighborhoods=[
                    NeighborhoodConfig(
                        slug="los-feliz", display="Los Feliz", aliases=[]
                    ),
                    NeighborhoodConfig(
                        slug="venice", display="Venice", aliases=[]
                    ),
                    NeighborhoodConfig(
                        slug="silver-lake", display="Silver Lake", aliases=[]
                    ),
                ],
            ),
            LocationConfig(
                slug="chicago",
                display="Chicago",
                aliases=[],
                neighborhoods=[
                    NeighborhoodConfig(
                        slug="wicker-park", display="Wicker Park", aliases=[]
                    )
                ],
            ),
        ],
        subservices=[],
        url_patterns_to_ignore=[],
    )


def _page(
    path: str, page_type: PageType, **kwargs: object
) -> PageClassification:
    return PageClassification(
        url=f"https://example.com{path}",
        page_type=page_type,
        raw_path=path,
        **kwargs,  # type: ignore[arg-type]
    )


def _links_df(rows: list[tuple[str, str]]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "source_url": [r[0] for r in rows],
            "target_url": [r[1] for r in rows],
            "anchor_text": [""] * len(rows),
            "link_type": [None] * len(rows),
        }
    )


def _empty_links_df() -> pd.DataFrame:
    return _links_df([])


def _neighborhood(slug: str, location: str = "los-angeles") -> PageClassification:
    return _page(
        f"/{location}/{slug}",
        PageType.NEIGHBORHOOD,
        location=location,
        neighborhood=slug,
    )


def _nb_service(
    nb: str, svc: str, location: str = "los-angeles"
) -> PageClassification:
    return _page(
        f"/{location}/{nb}/{svc}",
        PageType.NEIGHBORHOOD_SERVICE,
        location=location,
        neighborhood=nb,
        service=svc,
    )


# --------------------------------------------------------------------------- #
# Sibling neighborhood links
# --------------------------------------------------------------------------- #


def test_passing_when_neighborhood_links_to_all_siblings(
    multi_neighborhood_config: ClientConfig,
) -> None:
    a = _neighborhood("los-feliz")
    b = _neighborhood("venice")
    c = _neighborhood("silver-lake")
    registry = SiteRegistry([a, b, c], multi_neighborhood_config)
    links = _links_df(
        [
            (a.raw_path, b.raw_path),
            (a.raw_path, c.raw_path),
            (b.raw_path, a.raw_path),
            (b.raw_path, c.raw_path),
            (c.raw_path, a.raw_path),
            (c.raw_path, b.raw_path),
        ]
    )
    assert neighborhood_silo.run(registry, links, multi_neighborhood_config) == []


def test_missing_one_sibling_fires_one_violation(
    multi_neighborhood_config: ClientConfig,
) -> None:
    a = _neighborhood("los-feliz")
    b = _neighborhood("venice")
    c = _neighborhood("silver-lake")
    registry = SiteRegistry([a, b, c], multi_neighborhood_config)
    # `a` links only to b, missing link to c
    links = _links_df([(a.raw_path, b.raw_path)])

    violations = neighborhood_silo.run(
        registry, links, multi_neighborhood_config
    )
    sibling_violations = [
        v
        for v in violations
        if v.rule == "neighborhood_silo.missing_sibling_neighborhood_link"
        and v.source_url == a.url
    ]
    assert len(sibling_violations) == 1
    assert sibling_violations[0].expected == c.url
    assert sibling_violations[0].severity == Severity.WARNING


def test_neighborhood_does_not_link_to_itself_as_sibling(
    multi_neighborhood_config: ClientConfig,
) -> None:
    """A neighborhood is not its own sibling."""
    a = _neighborhood("los-feliz")
    registry = SiteRegistry([a], multi_neighborhood_config)
    # No siblings to link to (it's the only neighborhood)
    assert (
        neighborhood_silo.run(
            registry, _empty_links_df(), multi_neighborhood_config
        )
        == []
    )


def test_siblings_must_share_parent_location(
    multi_neighborhood_config: ClientConfig,
) -> None:
    """A neighborhood in LA is not a sibling of a neighborhood in Chicago."""
    la_a = _neighborhood("los-feliz", "los-angeles")
    chi_a = _neighborhood("wicker-park", "chicago")
    registry = SiteRegistry([la_a, chi_a], multi_neighborhood_config)
    # No siblings of la_a in LA (only one LA neighborhood),
    # so no violation.
    violations = neighborhood_silo.run(
        registry, _empty_links_df(), multi_neighborhood_config
    )
    assert not any(
        v.rule == "neighborhood_silo.missing_sibling_neighborhood_link"
        and v.source_url == la_a.url
        and v.expected == chi_a.url
        for v in violations
    )


# --------------------------------------------------------------------------- #
# Neighborhood service links
# --------------------------------------------------------------------------- #


def test_passing_when_neighborhood_links_to_all_its_services(
    config: ClientConfig,
) -> None:
    nb = _neighborhood("los-feliz")
    svc_a = _nb_service("los-feliz", "plumber")
    svc_b = _nb_service("los-feliz", "electrician")
    registry = SiteRegistry([nb, svc_a, svc_b], config)
    links = _links_df(
        [(nb.raw_path, svc_a.raw_path), (nb.raw_path, svc_b.raw_path)]
    )
    assert neighborhood_silo.run(registry, links, config) == []


def test_missing_neighborhood_service_fires_violation(
    config: ClientConfig,
) -> None:
    nb = _neighborhood("los-feliz")
    svc = _nb_service("los-feliz", "plumber")
    registry = SiteRegistry([nb, svc], config)

    violations = neighborhood_silo.run(registry, _empty_links_df(), config)
    assert len(violations) == 1
    v = violations[0]
    assert v.rule == "neighborhood_silo.missing_neighborhood_service_link"
    assert v.severity == Severity.WARNING
    assert v.source_url == nb.url
    assert v.expected == svc.url


def test_neighborhood_services_filtered_by_neighborhood(
    multi_neighborhood_config: ClientConfig,
) -> None:
    """A neighborhood is not required to link to services in OTHER neighborhoods."""
    a = _neighborhood("los-feliz")
    svc_for_venice = _nb_service("venice", "plumber")
    registry = SiteRegistry([a, svc_for_venice], multi_neighborhood_config)

    violations = neighborhood_silo.run(
        registry, _empty_links_df(), multi_neighborhood_config
    )
    assert not any(
        v.rule == "neighborhood_silo.missing_neighborhood_service_link"
        and v.source_url == a.url
        for v in violations
    )


# --------------------------------------------------------------------------- #
# Combined / edge cases
# --------------------------------------------------------------------------- #


def test_both_rules_fire_together(
    multi_neighborhood_config: ClientConfig,
) -> None:
    a = _neighborhood("los-feliz")
    b = _neighborhood("venice")
    svc = _nb_service("los-feliz", "plumber")
    registry = SiteRegistry([a, b, svc], multi_neighborhood_config)

    violations = neighborhood_silo.run(
        registry, _empty_links_df(), multi_neighborhood_config
    )
    a_violations = [v for v in violations if v.source_url == a.url]
    rules_for_a = {v.rule for v in a_violations}
    assert "neighborhood_silo.missing_sibling_neighborhood_link" in rules_for_a
    assert (
        "neighborhood_silo.missing_neighborhood_service_link" in rules_for_a
    )


def test_empty_registry(config: ClientConfig) -> None:
    registry = SiteRegistry([], config)
    assert neighborhood_silo.run(registry, _empty_links_df(), config) == []


def test_no_neighborhoods_no_violations(config: ClientConfig) -> None:
    """A registry without NEIGHBORHOOD pages produces no violations."""
    page = _page("/los-angeles", PageType.TOP_LEVEL_LOCATION, location="los-angeles")
    registry = SiteRegistry([page], config)
    assert neighborhood_silo.run(registry, _empty_links_df(), config) == []


def test_canonical_dedup_for_duplicate_neighborhoods(
    multi_neighborhood_config: ClientConfig,
) -> None:
    """Duplicate NEIGHBORHOOD pages for same (loc, nb) - only canonical required."""
    a = _neighborhood("los-feliz")
    b = _neighborhood("venice")
    duplicate_b = _page(
        "/la/venice",
        PageType.NEIGHBORHOOD,
        location="los-angeles",
        neighborhood="venice",
    )
    registry = SiteRegistry([a, b, duplicate_b], multi_neighborhood_config)
    # `a` only links to canonical b; duplicate_b is not required
    links = _links_df([(a.raw_path, b.raw_path)])

    violations = neighborhood_silo.run(
        registry, links, multi_neighborhood_config
    )
    sibling_violations = [
        v
        for v in violations
        if v.rule == "neighborhood_silo.missing_sibling_neighborhood_link"
        and v.source_url == a.url
    ]
    # los-feliz needs venice (which it has); silver-lake doesn't exist; no other siblings.
    assert sibling_violations == []
