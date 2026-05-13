"""Tests for engine.auditors.location_silo."""

from pathlib import Path

import pandas as pd
import pytest

from engine.auditors import location_silo
from engine.classifier import PageClassification, PageType
from engine.config import ClientConfig, load as load_config
from engine.registry import SiteRegistry
from engine.violations import Severity

FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample_config.yml"


@pytest.fixture
def config() -> ClientConfig:
    """Synthetic config: services=[plumber, electrician], locations=[la, chicago],
    subservices=[plumber/24-hour]."""
    return load_config(FIXTURE)


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


# --------------------------------------------------------------------------- #
# TOP_LEVEL_LOCATION -> LOCAL_LANDING
# --------------------------------------------------------------------------- #


def test_passing_when_top_level_links_to_all_landings(
    config: ClientConfig,
) -> None:
    tll = _page(
        "/los-angeles", PageType.TOP_LEVEL_LOCATION, location="los-angeles"
    )
    ll_p = _page(
        "/los-angeles/plumber",
        PageType.LOCAL_LANDING,
        location="los-angeles",
        service="plumber",
    )
    ll_e = _page(
        "/los-angeles/electrician",
        PageType.LOCAL_LANDING,
        location="los-angeles",
        service="electrician",
    )
    registry = SiteRegistry([tll, ll_p, ll_e], config)
    links = _links_df(
        [
            (tll.raw_path, ll_p.raw_path),
            (tll.raw_path, ll_e.raw_path),
        ]
    )

    assert location_silo.run(registry, links, config) == []


def test_one_missing_landing_fires_one_violation(
    config: ClientConfig,
) -> None:
    tll = _page(
        "/los-angeles", PageType.TOP_LEVEL_LOCATION, location="los-angeles"
    )
    ll_p = _page(
        "/los-angeles/plumber",
        PageType.LOCAL_LANDING,
        location="los-angeles",
        service="plumber",
    )
    ll_e = _page(
        "/los-angeles/electrician",
        PageType.LOCAL_LANDING,
        location="los-angeles",
        service="electrician",
    )
    registry = SiteRegistry([tll, ll_p, ll_e], config)
    # Only links to plumber, missing electrician
    links = _links_df([(tll.raw_path, ll_p.raw_path)])

    violations = location_silo.run(registry, links, config)
    assert len(violations) == 1
    v = violations[0]
    assert v.rule == "location_silo.missing_local_landing_link"
    assert v.severity == Severity.CRITICAL
    assert v.source_url == tll.url
    assert v.expected == ll_e.url


def test_all_landings_missing_fires_all_violations(
    config: ClientConfig,
) -> None:
    tll = _page(
        "/los-angeles", PageType.TOP_LEVEL_LOCATION, location="los-angeles"
    )
    ll_p = _page(
        "/los-angeles/plumber",
        PageType.LOCAL_LANDING,
        location="los-angeles",
        service="plumber",
    )
    ll_e = _page(
        "/los-angeles/electrician",
        PageType.LOCAL_LANDING,
        location="los-angeles",
        service="electrician",
    )
    registry = SiteRegistry([tll, ll_p, ll_e], config)

    violations = location_silo.run(registry, _empty_links_df(), config)
    assert len(violations) == 2
    expected = {v.expected for v in violations}
    assert expected == {ll_p.url, ll_e.url}


def test_only_canonical_local_landing_required(
    config: ClientConfig,
) -> None:
    """Duplicate local landings for (loc, svc): only the first (canonical) is required."""
    tll = _page(
        "/los-angeles", PageType.TOP_LEVEL_LOCATION, location="los-angeles"
    )
    canonical = _page(
        "/los-angeles/plumber",
        PageType.LOCAL_LANDING,
        location="los-angeles",
        service="plumber",
    )
    duplicate = _page(
        "/la/plumber",
        PageType.LOCAL_LANDING,
        location="los-angeles",
        service="plumber",
    )
    registry = SiteRegistry([tll, canonical, duplicate], config)
    links = _links_df([(tll.raw_path, canonical.raw_path)])

    assert location_silo.run(registry, links, config) == []


def test_top_level_location_with_no_landings(config: ClientConfig) -> None:
    tll = _page("/chicago", PageType.TOP_LEVEL_LOCATION, location="chicago")
    registry = SiteRegistry([tll], config)
    assert location_silo.run(registry, _empty_links_df(), config) == []


# --------------------------------------------------------------------------- #
# LOCAL_LANDING -> SUBSERVICE_LANDING
# --------------------------------------------------------------------------- #


def test_local_landing_links_to_all_subservice_landings(
    config: ClientConfig,
) -> None:
    ll = _page(
        "/los-angeles/plumber",
        PageType.LOCAL_LANDING,
        location="los-angeles",
        service="plumber",
    )
    sub_land = _page(
        "/los-angeles/plumber/24-hour",
        PageType.SUBSERVICE_LANDING,
        location="los-angeles",
        service="plumber",
        subservice="24-hour",
    )
    registry = SiteRegistry([ll, sub_land], config)
    links = _links_df([(ll.raw_path, sub_land.raw_path)])

    assert location_silo.run(registry, links, config) == []


def test_local_landing_missing_subservice_landing_link(
    config: ClientConfig,
) -> None:
    ll = _page(
        "/los-angeles/plumber",
        PageType.LOCAL_LANDING,
        location="los-angeles",
        service="plumber",
    )
    sub_land = _page(
        "/los-angeles/plumber/24-hour",
        PageType.SUBSERVICE_LANDING,
        location="los-angeles",
        service="plumber",
        subservice="24-hour",
    )
    registry = SiteRegistry([ll, sub_land], config)

    violations = location_silo.run(registry, _empty_links_df(), config)
    assert len(violations) == 1
    v = violations[0]
    assert v.rule == "location_silo.missing_subservice_landing_link"
    assert v.severity == Severity.CRITICAL
    assert v.source_url == ll.url
    assert v.expected == sub_land.url


def test_subservice_landing_for_other_location_does_not_fire(
    config: ClientConfig,
) -> None:
    """A LL for los-angeles doesn't need to link to subservice landings under chicago."""
    ll_la = _page(
        "/los-angeles/plumber",
        PageType.LOCAL_LANDING,
        location="los-angeles",
        service="plumber",
    )
    sub_chi = _page(
        "/chicago/plumber/24-hour",
        PageType.SUBSERVICE_LANDING,
        location="chicago",
        service="plumber",
        subservice="24-hour",
    )
    registry = SiteRegistry([ll_la, sub_chi], config)

    assert location_silo.run(registry, _empty_links_df(), config) == []


def test_subservice_landing_for_other_service_does_not_fire(
    config: ClientConfig,
) -> None:
    """An electrician LL doesn't need to link to plumber subservice landings."""
    ll_e = _page(
        "/los-angeles/electrician",
        PageType.LOCAL_LANDING,
        location="los-angeles",
        service="electrician",
    )
    sub_plumber = _page(
        "/los-angeles/plumber/24-hour",
        PageType.SUBSERVICE_LANDING,
        location="los-angeles",
        service="plumber",
        subservice="24-hour",
    )
    registry = SiteRegistry([ll_e, sub_plumber], config)

    assert location_silo.run(registry, _empty_links_df(), config) == []


# --------------------------------------------------------------------------- #
# Edge cases
# --------------------------------------------------------------------------- #


def test_empty_registry_yields_no_violations(config: ClientConfig) -> None:
    registry = SiteRegistry([], config)
    assert location_silo.run(registry, _empty_links_df(), config) == []


def test_partial_link_coverage_across_two_locations(
    config: ClientConfig,
) -> None:
    """Two locations: missing links are independent."""
    tll_la = _page(
        "/los-angeles", PageType.TOP_LEVEL_LOCATION, location="los-angeles"
    )
    tll_chi = _page(
        "/chicago", PageType.TOP_LEVEL_LOCATION, location="chicago"
    )
    ll_la_p = _page(
        "/los-angeles/plumber",
        PageType.LOCAL_LANDING,
        location="los-angeles",
        service="plumber",
    )
    ll_chi_p = _page(
        "/chicago/plumber",
        PageType.LOCAL_LANDING,
        location="chicago",
        service="plumber",
    )
    registry = SiteRegistry([tll_la, tll_chi, ll_la_p, ll_chi_p], config)
    # LA links to its LL; Chicago does not
    links = _links_df([(tll_la.raw_path, ll_la_p.raw_path)])

    violations = location_silo.run(registry, links, config)
    assert len(violations) == 1
    assert violations[0].source_url == tll_chi.url
    assert violations[0].expected == ll_chi_p.url
