"""Tests for engine.auditors.service_silo."""

from pathlib import Path

import pandas as pd
import pytest

from engine.auditors import service_silo
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
# TOP_LEVEL_SERVICE -> LOCAL_LANDING
# --------------------------------------------------------------------------- #


def test_passing_when_top_level_links_to_all_landings(
    config: ClientConfig,
) -> None:
    tls = _page("/plumber", PageType.TOP_LEVEL_SERVICE, service="plumber")
    ll_la = _page(
        "/los-angeles/plumber",
        PageType.LOCAL_LANDING,
        location="los-angeles",
        service="plumber",
    )
    ll_chi = _page(
        "/chicago/plumber",
        PageType.LOCAL_LANDING,
        location="chicago",
        service="plumber",
    )
    registry = SiteRegistry([tls, ll_la, ll_chi], config)
    links = _links_df(
        [
            (tls.raw_path, ll_la.raw_path),
            (tls.raw_path, ll_chi.raw_path),
        ]
    )

    assert service_silo.run(registry, links, config) == []


def test_one_missing_landing_fires_one_violation(
    config: ClientConfig,
) -> None:
    tls = _page("/plumber", PageType.TOP_LEVEL_SERVICE, service="plumber")
    ll_la = _page(
        "/los-angeles/plumber",
        PageType.LOCAL_LANDING,
        location="los-angeles",
        service="plumber",
    )
    ll_chi = _page(
        "/chicago/plumber",
        PageType.LOCAL_LANDING,
        location="chicago",
        service="plumber",
    )
    registry = SiteRegistry([tls, ll_la, ll_chi], config)
    # Only links to LA, missing link to Chicago
    links = _links_df([(tls.raw_path, ll_la.raw_path)])

    violations = service_silo.run(registry, links, config)
    assert len(violations) == 1
    v = violations[0]
    assert v.rule == "service_silo.missing_local_landing_link"
    assert v.severity == Severity.CRITICAL
    assert v.source_url == tls.url
    assert v.expected == ll_chi.url


def test_all_landings_missing_fires_all_violations(
    config: ClientConfig,
) -> None:
    tls = _page("/plumber", PageType.TOP_LEVEL_SERVICE, service="plumber")
    ll_la = _page(
        "/los-angeles/plumber",
        PageType.LOCAL_LANDING,
        location="los-angeles",
        service="plumber",
    )
    ll_chi = _page(
        "/chicago/plumber",
        PageType.LOCAL_LANDING,
        location="chicago",
        service="plumber",
    )
    registry = SiteRegistry([tls, ll_la, ll_chi], config)

    violations = service_silo.run(registry, _empty_links_df(), config)
    assert len(violations) == 2
    expected = {v.expected for v in violations}
    assert expected == {ll_la.url, ll_chi.url}


def test_no_violations_when_no_local_landings_exist(
    config: ClientConfig,
) -> None:
    """Service with no related local landings has nothing to link to."""
    tls = _page("/plumber", PageType.TOP_LEVEL_SERVICE, service="plumber")
    registry = SiteRegistry([tls], config)
    assert service_silo.run(registry, _empty_links_df(), config) == []


def test_only_canonical_local_landing_required(
    config: ClientConfig,
) -> None:
    """When duplicate local landings exist for (loc, svc), only the first is required."""
    tls = _page("/plumber", PageType.TOP_LEVEL_SERVICE, service="plumber")
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
    registry = SiteRegistry([tls, canonical, duplicate], config)
    # Link only to canonical, not to duplicate
    links = _links_df([(tls.raw_path, canonical.raw_path)])

    # No violations: canonical is linked, duplicate is irrelevant to this auditor
    violations = service_silo.run(registry, links, config)
    assert violations == []


# --------------------------------------------------------------------------- #
# SUB_SERVICE -> SUBSERVICE_LANDING
# --------------------------------------------------------------------------- #


def test_sub_service_links_to_all_subservice_landings(
    config: ClientConfig,
) -> None:
    sub = _page(
        "/plumber/24-hour",
        PageType.SUB_SERVICE,
        service="plumber",
        subservice="24-hour",
    )
    sub_land_la = _page(
        "/los-angeles/plumber/24-hour",
        PageType.SUBSERVICE_LANDING,
        location="los-angeles",
        service="plumber",
        subservice="24-hour",
    )
    registry = SiteRegistry([sub, sub_land_la], config)
    links = _links_df([(sub.raw_path, sub_land_la.raw_path)])

    assert service_silo.run(registry, links, config) == []


def test_sub_service_missing_subservice_landing_link(
    config: ClientConfig,
) -> None:
    sub = _page(
        "/plumber/24-hour",
        PageType.SUB_SERVICE,
        service="plumber",
        subservice="24-hour",
    )
    sub_land_la = _page(
        "/los-angeles/plumber/24-hour",
        PageType.SUBSERVICE_LANDING,
        location="los-angeles",
        service="plumber",
        subservice="24-hour",
    )
    registry = SiteRegistry([sub, sub_land_la], config)

    violations = service_silo.run(registry, _empty_links_df(), config)
    assert len(violations) == 1
    v = violations[0]
    assert v.rule == "service_silo.missing_subservice_landing_link"
    assert v.severity == Severity.CRITICAL
    assert v.source_url == sub.url
    assert v.expected == sub_land_la.url


def test_sub_service_only_matches_correct_subservice() -> None:
    """A sub-service for 24-hour does not require links to weekend subservice landings."""
    from engine.config import ServiceConfig, LocationConfig, SubserviceConfig

    cfg = ClientConfig(
        client="x",
        domain="example.com",
        services=[ServiceConfig(slug="plumber", display="Plumber", aliases=[])],
        locations=[
            LocationConfig(
                slug="los-angeles", display="LA", aliases=[], neighborhoods=[]
            )
        ],
        subservices=[
            SubserviceConfig(
                parent="plumber", slug="24-hour", display="24h", aliases=[]
            ),
            SubserviceConfig(
                parent="plumber",
                slug="weekend",
                display="Weekend",
                aliases=[],
            ),
        ],
        url_patterns_to_ignore=[],
    )
    sub_24 = _page(
        "/plumber/24-hour",
        PageType.SUB_SERVICE,
        service="plumber",
        subservice="24-hour",
    )
    landing_weekend = _page(
        "/los-angeles/plumber/weekend",
        PageType.SUBSERVICE_LANDING,
        location="los-angeles",
        service="plumber",
        subservice="weekend",
    )
    registry = SiteRegistry([sub_24, landing_weekend], cfg)

    # 24-hour sub-service should NOT be expected to link to the weekend landing
    assert service_silo.run(registry, _empty_links_df(), cfg) == []


# --------------------------------------------------------------------------- #
# Edge cases
# --------------------------------------------------------------------------- #


def test_empty_registry_yields_no_violations(config: ClientConfig) -> None:
    registry = SiteRegistry([], config)
    assert service_silo.run(registry, _empty_links_df(), config) == []


def test_partial_link_coverage_emits_only_missing_links(
    config: ClientConfig,
) -> None:
    """Multiple top-level services: missing links are independent."""
    tls_p = _page("/plumber", PageType.TOP_LEVEL_SERVICE, service="plumber")
    tls_e = _page(
        "/electrician", PageType.TOP_LEVEL_SERVICE, service="electrician"
    )
    ll_p_la = _page(
        "/los-angeles/plumber",
        PageType.LOCAL_LANDING,
        location="los-angeles",
        service="plumber",
    )
    ll_e_la = _page(
        "/los-angeles/electrician",
        PageType.LOCAL_LANDING,
        location="los-angeles",
        service="electrician",
    )
    registry = SiteRegistry([tls_p, tls_e, ll_p_la, ll_e_la], config)
    # plumber links to its LL, electrician doesn't
    links = _links_df([(tls_p.raw_path, ll_p_la.raw_path)])

    violations = service_silo.run(registry, links, config)
    assert len(violations) == 1
    assert violations[0].source_url == tls_e.url
    assert violations[0].expected == ll_e_la.url


def test_self_link_exemption() -> None:
    """If a TOP_LEVEL_SERVICE somehow shares a raw_path with a LOCAL_LANDING
    candidate (degenerate config), we don't fire a self-link violation."""
    from engine.config import ServiceConfig, LocationConfig

    cfg = ClientConfig(
        client="x",
        domain="example.com",
        services=[ServiceConfig(slug="plumber", display="P", aliases=[])],
        locations=[
            LocationConfig(slug="x", display="X", aliases=[], neighborhoods=[])
        ],
        subservices=[],
        url_patterns_to_ignore=[],
    )
    same = _page(
        "/plumber",
        PageType.LOCAL_LANDING,
        location="x",
        service="plumber",
    )
    tls = _page("/plumber", PageType.TOP_LEVEL_SERVICE, service="plumber")
    registry = SiteRegistry([tls, same], cfg)

    assert service_silo.run(registry, _empty_links_df(), cfg) == []
