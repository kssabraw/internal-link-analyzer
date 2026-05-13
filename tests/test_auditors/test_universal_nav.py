"""Tests for engine.auditors.universal_nav."""

from pathlib import Path

import pandas as pd
import pytest

from engine.auditors import universal_nav
from engine.classifier import PageClassification, PageType
from engine.config import (
    ClientConfig,
    LocationConfig,
    ServiceConfig,
    load as load_config,
)
from engine.registry import SiteRegistry
from engine.violations import Severity

FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample_config.yml"

_ALWAYS_REQUIRED_PATHS = {
    "/",
    "/about-us",
    "/contact-us",
    "/privacy-policy",
    "/blog",
}


@pytest.fixture
def config() -> ClientConfig:
    """Sample synthetic config (2 services, 2 locations) - no hubs required."""
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


def _empty_links_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "source_url": pd.Series([], dtype="object"),
            "target_url": pd.Series([], dtype="object"),
            "anchor_text": pd.Series([], dtype="object"),
            "link_type": pd.Series([], dtype="object"),
        }
    )


def _links_df(rows: list[tuple[str, str]]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "source_url": [src for src, _ in rows],
            "target_url": [tgt for _, tgt in rows],
            "anchor_text": [""] * len(rows),
            "link_type": [None] * len(rows),
        }
    )


# --------------------------------------------------------------------------- #
# Passing cases
# --------------------------------------------------------------------------- #


def test_no_violations_when_page_links_to_all_targets(
    config: ClientConfig,
) -> None:
    page = _page(
        "/los-angeles/plumber",
        PageType.LOCAL_LANDING,
        location="los-angeles",
        service="plumber",
    )
    registry = SiteRegistry([page], config)
    links = _links_df([(page.raw_path, tgt) for tgt in _ALWAYS_REQUIRED_PATHS])

    violations = universal_nav.run(registry, links, config)
    assert violations == []


# --------------------------------------------------------------------------- #
# Failing cases
# --------------------------------------------------------------------------- #


def test_fires_one_violation_per_missing_target(config: ClientConfig) -> None:
    page = _page(
        "/los-angeles/plumber",
        PageType.LOCAL_LANDING,
        location="los-angeles",
        service="plumber",
    )
    registry = SiteRegistry([page], config)

    violations = universal_nav.run(registry, _empty_links_df(), config)

    # All 5 always-required targets are missing.
    assert len(violations) == 5
    rules = {v.rule for v in violations}
    assert rules == {
        "universal_nav.missing_home",
        "universal_nav.missing_about_us",
        "universal_nav.missing_contact_us",
        "universal_nav.missing_privacy_policy",
        "universal_nav.missing_blog_archive",
    }
    assert all(v.severity == Severity.CRITICAL for v in violations)
    assert all(v.source_url == page.url for v in violations)
    assert all(v.page_type == PageType.LOCAL_LANDING for v in violations)


def test_violation_fields_are_populated_correctly(config: ClientConfig) -> None:
    page = _page("/some-page", PageType.LOCAL_LANDING)
    registry = SiteRegistry([page], config)

    violations = universal_nav.run(registry, _empty_links_df(), config)
    home_v = next(v for v in violations if v.rule == "universal_nav.missing_home")
    assert home_v.expected == "/"
    assert home_v.actual is None
    assert "Page does not link to required nav target /" in home_v.message


def test_partial_link_coverage_emits_only_missing_ones(
    config: ClientConfig,
) -> None:
    page = _page("/some-page", PageType.LOCAL_LANDING)
    registry = SiteRegistry([page], config)
    # Links to home and blog but not about-us / contact-us / privacy
    links = _links_df([(page.raw_path, "/"), (page.raw_path, "/blog")])

    violations = universal_nav.run(registry, links, config)
    assert {v.rule for v in violations} == {
        "universal_nav.missing_about_us",
        "universal_nav.missing_contact_us",
        "universal_nav.missing_privacy_policy",
    }


# --------------------------------------------------------------------------- #
# Self-link exemption
# --------------------------------------------------------------------------- #


def test_home_does_not_require_self_link(config: ClientConfig) -> None:
    home = _page("/", PageType.HOME)
    registry = SiteRegistry([home], config)

    violations = universal_nav.run(registry, _empty_links_df(), config)
    assert not any(v.rule == "universal_nav.missing_home" for v in violations)
    # But the other 4 are still required
    assert len(violations) == 4


def test_about_us_does_not_require_self_link(config: ClientConfig) -> None:
    about = _page("/about-us", PageType.ABOUT_US)
    registry = SiteRegistry([about], config)

    violations = universal_nav.run(registry, _empty_links_df(), config)
    assert not any(
        v.rule == "universal_nav.missing_about_us" for v in violations
    )


# --------------------------------------------------------------------------- #
# Hub page rules
# --------------------------------------------------------------------------- #


def test_services_hub_not_required_when_count_at_or_under_threshold(
    config: ClientConfig,
) -> None:
    """Sample config has 2 services - no hub required, no rule fires."""
    page = _page("/some-page", PageType.LOCAL_LANDING)
    registry = SiteRegistry([page], config)

    violations = universal_nav.run(registry, _empty_links_df(), config)
    assert not any(
        v.rule == "universal_nav.missing_services_hub" for v in violations
    )


def test_services_hub_required_when_count_exceeds_threshold() -> None:
    services = [
        ServiceConfig(slug=f"svc-{i}", display=f"Svc {i}", aliases=[])
        for i in range(25)
    ]
    cfg = ClientConfig(
        client="big",
        domain="example.com",
        services=services,
        locations=[],
        subservices=[],
        url_patterns_to_ignore=[],
    )
    page = _page("/some-page", PageType.LOCAL_LANDING)
    registry = SiteRegistry([page], cfg)

    violations = universal_nav.run(registry, _empty_links_df(), cfg)
    assert any(
        v.rule == "universal_nav.missing_services_hub" for v in violations
    )


def test_areas_we_serve_hub_required_when_count_exceeds_threshold() -> None:
    locations = [
        LocationConfig(slug=f"city-{i}", display=f"City {i}", aliases=[])
        for i in range(25)
    ]
    cfg = ClientConfig(
        client="big",
        domain="example.com",
        services=[],
        locations=locations,
        subservices=[],
        url_patterns_to_ignore=[],
    )
    page = _page("/some-page", PageType.LOCAL_LANDING)
    registry = SiteRegistry([page], cfg)

    violations = universal_nav.run(registry, _empty_links_df(), cfg)
    assert any(
        v.rule == "universal_nav.missing_areas_we_serve_hub" for v in violations
    )


def test_areas_we_serve_hub_not_required_when_under_threshold(
    config: ClientConfig,
) -> None:
    page = _page("/some-page", PageType.LOCAL_LANDING)
    registry = SiteRegistry([page], config)

    violations = universal_nav.run(registry, _empty_links_df(), config)
    assert not any(
        v.rule == "universal_nav.missing_areas_we_serve_hub" for v in violations
    )


# --------------------------------------------------------------------------- #
# Edge cases
# --------------------------------------------------------------------------- #


def test_empty_registry_yields_no_violations(config: ClientConfig) -> None:
    registry = SiteRegistry([], config)
    assert universal_nav.run(registry, _empty_links_df(), config) == []


def test_multiple_pages_each_get_their_own_violations(
    config: ClientConfig,
) -> None:
    a = _page("/page-a", PageType.LOCAL_LANDING)
    b = _page("/page-b", PageType.LOCAL_LANDING)
    registry = SiteRegistry([a, b], config)

    violations = universal_nav.run(registry, _empty_links_df(), config)
    # 5 missing targets x 2 pages
    assert len(violations) == 10
    sources = {v.source_url for v in violations}
    assert sources == {a.url, b.url}
