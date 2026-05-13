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


def _canonical_nav_pages() -> list["PageClassification"]:
    """The five SOP-default universal-nav pages, all classified.

    The auditor sources nav targets from the registry rather than hard-coded
    paths, so per-page link-coverage tests must include these.
    """
    return [
        _page("/", PageType.HOME),
        _page("/about-us", PageType.ABOUT_US),
        _page("/contact-us", PageType.CONTACT_US),
        _page("/privacy-policy", PageType.PRIVACY_POLICY),
        _page("/blog", PageType.BLOG_ARCHIVE),
    ]


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
    registry = SiteRegistry([page, *_canonical_nav_pages()], config)
    # Page links to every required target; canonical pages link to each other.
    links = _links_df(
        [(page.raw_path, tgt) for tgt in _ALWAYS_REQUIRED_PATHS]
        + [
            (src, tgt)
            for src in _ALWAYS_REQUIRED_PATHS
            for tgt in _ALWAYS_REQUIRED_PATHS
            if src != tgt
        ]
    )

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
    canonical = _canonical_nav_pages()
    registry = SiteRegistry([page, *canonical], config)

    violations = universal_nav.run(registry, _empty_links_df(), config)

    # All 5 targets missing from `page` -> 5 violations sourced at `page`.
    page_violations = [v for v in violations if v.source_url == page.url]
    assert len(page_violations) == 5
    rules = {v.rule for v in page_violations}
    assert rules == {
        "universal_nav.missing_home",
        "universal_nav.missing_about_us",
        "universal_nav.missing_contact_us",
        "universal_nav.missing_privacy_policy",
        "universal_nav.missing_blog_archive",
    }
    assert all(v.severity == Severity.CRITICAL for v in page_violations)
    assert all(v.page_type == PageType.LOCAL_LANDING for v in page_violations)


def test_violation_fields_are_populated_correctly(config: ClientConfig) -> None:
    page = _page("/some-page", PageType.LOCAL_LANDING)
    registry = SiteRegistry([page, *_canonical_nav_pages()], config)

    violations = universal_nav.run(registry, _empty_links_df(), config)
    home_v = next(
        v
        for v in violations
        if v.rule == "universal_nav.missing_home"
        and v.source_url == page.url
    )
    assert home_v.expected == "/"
    assert home_v.actual is None
    assert "Page does not link to required nav target /" in home_v.message


def test_partial_link_coverage_emits_only_missing_ones(
    config: ClientConfig,
) -> None:
    page = _page("/some-page", PageType.LOCAL_LANDING)
    registry = SiteRegistry([page, *_canonical_nav_pages()], config)
    # Links to home and blog but not about-us / contact-us / privacy
    links = _links_df([(page.raw_path, "/"), (page.raw_path, "/blog")])

    violations = universal_nav.run(registry, links, config)
    rules = {v.rule for v in violations if v.source_url == page.url}
    assert rules == {
        "universal_nav.missing_about_us",
        "universal_nav.missing_contact_us",
        "universal_nav.missing_privacy_policy",
    }


def test_site_level_violation_when_canonical_page_missing(
    config: ClientConfig,
) -> None:
    """If no page of the required type exists, emit one site-level violation."""
    page = _page("/some-page", PageType.LOCAL_LANDING)
    # Register only Home + Blog Archive; About / Contact / Privacy don't exist.
    registry = SiteRegistry(
        [
            page,
            _page("/", PageType.HOME),
            _page("/blog", PageType.BLOG_ARCHIVE),
        ],
        config,
    )

    violations = universal_nav.run(registry, _empty_links_df(), config)

    site_level = [v for v in violations if "_page_missing" in v.rule]
    assert {v.rule for v in site_level} == {
        "universal_nav.missing_about_us_page_missing",
        "universal_nav.missing_contact_us_page_missing",
        "universal_nav.missing_privacy_policy_page_missing",
    }
    # And no per-page violations fire for the missing-page types — those are
    # suppressed in favor of the single site-level violation.
    page_rules = {
        v.rule
        for v in violations
        if v.source_url == page.url and "_page_missing" not in v.rule
    }
    assert "universal_nav.missing_about_us" not in page_rules
    assert "universal_nav.missing_contact_us" not in page_rules
    assert "universal_nav.missing_privacy_policy" not in page_rules
    # Per-page violations for the page-types that DO exist still fire.
    assert page_rules == {
        "universal_nav.missing_home",
        "universal_nav.missing_blog_archive",
    }


def test_configured_path_aliases_satisfy_universal_nav(
    config: ClientConfig,
) -> None:
    """A page linking to a configured About Us alias path passes."""
    page = _page("/some-page", PageType.LOCAL_LANDING)
    # ABOUT_US lives at a non-default path (the classifier put it there via
    # path_aliases at classification time; here we simulate that result).
    registry = SiteRegistry(
        [
            page,
            _page("/", PageType.HOME),
            _page("/company/about-us", PageType.ABOUT_US),
            _page("/contact", PageType.CONTACT_US),
            _page("/privacy-policy", PageType.PRIVACY_POLICY),
            _page("/blog", PageType.BLOG_ARCHIVE),
        ],
        config,
    )
    links = _links_df(
        [
            (page.raw_path, "/"),
            (page.raw_path, "/company/about-us"),
            (page.raw_path, "/contact"),
            (page.raw_path, "/privacy-policy"),
            (page.raw_path, "/blog"),
        ]
    )

    violations = universal_nav.run(registry, links, config)
    page_violations = [v for v in violations if v.source_url == page.url]
    assert page_violations == []


# --------------------------------------------------------------------------- #
# Self-link exemption
# --------------------------------------------------------------------------- #


def test_home_does_not_require_self_link(config: ClientConfig) -> None:
    home = _page("/", PageType.HOME)
    registry = SiteRegistry([home, *_canonical_nav_pages()[1:]], config)

    violations = universal_nav.run(registry, _empty_links_df(), config)
    # Home isn't required to link to itself.
    home_violations = [
        v
        for v in violations
        if v.source_url == home.url and v.rule == "universal_nav.missing_home"
    ]
    assert home_violations == []


def test_about_us_does_not_require_self_link(config: ClientConfig) -> None:
    about = _page("/about-us", PageType.ABOUT_US)
    registry = SiteRegistry([about], config)

    violations = universal_nav.run(registry, _empty_links_df(), config)
    assert not any(
        v.rule == "universal_nav.missing_about_us"
        and v.source_url == about.url
        for v in violations
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
    hub = _page("/services", PageType.SERVICES_HUB)
    registry = SiteRegistry([page, hub, *_canonical_nav_pages()], cfg)

    violations = universal_nav.run(registry, _empty_links_df(), cfg)
    assert any(
        v.rule == "universal_nav.missing_services_hub"
        and v.source_url == page.url
        for v in violations
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
    hub = _page("/areas-we-serve", PageType.AREAS_WE_SERVE_HUB)
    registry = SiteRegistry([page, hub, *_canonical_nav_pages()], cfg)

    violations = universal_nav.run(registry, _empty_links_df(), cfg)
    assert any(
        v.rule == "universal_nav.missing_areas_we_serve_hub"
        and v.source_url == page.url
        for v in violations
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
    registry = SiteRegistry([a, b, *_canonical_nav_pages()], config)

    violations = universal_nav.run(registry, _empty_links_df(), config)
    # 5 missing targets x 2 non-canonical pages = 10 per-page violations.
    per_page = [v for v in violations if v.source_url in {a.url, b.url}]
    assert len(per_page) == 10
    assert {v.source_url for v in per_page} == {a.url, b.url}
