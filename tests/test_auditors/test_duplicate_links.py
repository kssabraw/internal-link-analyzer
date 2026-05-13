"""Tests for engine.auditors.duplicate_links."""

from pathlib import Path

import pandas as pd
import pytest

from engine.auditors import duplicate_links
from engine.classifier import PageClassification, PageType
from engine.config import ClientConfig, load as load_config
from engine.registry import SiteRegistry
from engine.violations import Severity

FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample_config.yml"


@pytest.fixture
def config() -> ClientConfig:
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


def _links_df(rows: list[tuple[str, str, str]]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "source_url": [r[0] for r in rows],
            "target_url": [r[1] for r in rows],
            "anchor_text": [r[2] for r in rows],
            "link_type": [None] * len(rows),
        }
    )


def _empty_links_df() -> pd.DataFrame:
    return _links_df([])


# --------------------------------------------------------------------------- #
# Core: detect duplicates
# --------------------------------------------------------------------------- #


def test_no_duplicates_yields_no_violations(config: ClientConfig) -> None:
    page = _page("/foo", PageType.LOCAL_LANDING)
    registry = SiteRegistry([page], config)
    links = _links_df(
        [
            ("/foo", "/bar", "our bar service"),
            ("/foo", "/baz", "more on baz"),
        ]
    )
    assert duplicate_links.run(registry, links, config) == []


def test_two_links_to_same_target_with_body_anchors_fires(
    config: ClientConfig,
) -> None:
    page = _page("/foo", PageType.LOCAL_LANDING)
    registry = SiteRegistry([page], config)
    links = _links_df(
        [
            ("/foo", "/plumber", "professional plumber"),
            ("/foo", "/plumber", "our plumbing team"),
        ]
    )

    violations = duplicate_links.run(registry, links, config)
    assert len(violations) == 1
    v = violations[0]
    assert v.rule == "duplicate_links.same_target_multiple_times"
    assert v.severity == Severity.WARNING
    assert v.source_url == page.url
    assert "2 links to /plumber" in v.actual
    assert "1 link to /plumber" in v.expected


def test_three_links_reports_count_three(config: ClientConfig) -> None:
    page = _page("/foo", PageType.LOCAL_LANDING)
    registry = SiteRegistry([page], config)
    links = _links_df(
        [
            ("/foo", "/x", "first"),
            ("/foo", "/x", "second"),
            ("/foo", "/x", "third"),
        ]
    )

    violations = duplicate_links.run(registry, links, config)
    assert len(violations) == 1
    assert "3 links" in violations[0].actual


# --------------------------------------------------------------------------- #
# UI anchor allowlist (suppression)
# --------------------------------------------------------------------------- #


def test_ui_anchors_in_nav_and_footer_are_suppressed(
    config: ClientConfig,
) -> None:
    page = _page("/foo", PageType.LOCAL_LANDING)
    registry = SiteRegistry([page], config)
    # Same target linked twice with UI-style anchors -> suppressed
    links = _links_df(
        [
            ("/foo", "/", "Home"),
            ("/foo", "/", "Home"),
        ]
    )
    assert duplicate_links.run(registry, links, config) == []


def test_mixed_anchors_fires_when_any_is_body_style(
    config: ClientConfig,
) -> None:
    """If one anchor is UI and another is content, the body-content link is the
    SEO-meaningful one the SOP rule is protecting - fire."""
    page = _page("/foo", PageType.LOCAL_LANDING)
    registry = SiteRegistry([page], config)
    links = _links_df(
        [
            ("/foo", "/plumber", "Services"),  # UI-like
            ("/foo", "/plumber", "our skilled plumbers in Los Angeles"),  # body
        ]
    )
    violations = duplicate_links.run(registry, links, config)
    assert len(violations) == 1


def test_ui_anchor_match_is_case_and_whitespace_insensitive(
    config: ClientConfig,
) -> None:
    page = _page("/foo", PageType.LOCAL_LANDING)
    registry = SiteRegistry([page], config)
    links = _links_df(
        [
            ("/foo", "/about-us", "  ABOUT US  "),
            ("/foo", "/about-us", "About Us"),
        ]
    )
    assert duplicate_links.run(registry, links, config) == []


def test_empty_anchor_counts_as_ui(config: ClientConfig) -> None:
    """Image / icon links often have no visible anchor text; treat as UI."""
    page = _page("/foo", PageType.LOCAL_LANDING)
    registry = SiteRegistry([page], config)
    links = _links_df(
        [
            ("/foo", "/", ""),
            ("/foo", "/", ""),
        ]
    )
    assert duplicate_links.run(registry, links, config) == []


# --------------------------------------------------------------------------- #
# Source filtering: ignore unclassified sources
# --------------------------------------------------------------------------- #


def test_unclassified_source_is_ignored(config: ClientConfig) -> None:
    page = _page("/foo", PageType.LOCAL_LANDING)
    registry = SiteRegistry([page], config)
    # source is not in the registry -> skipped
    links = _links_df(
        [
            ("/press/some-article", "/plumber", "body anchor"),
            ("/press/some-article", "/plumber", "another body anchor"),
        ]
    )
    assert duplicate_links.run(registry, links, config) == []


# --------------------------------------------------------------------------- #
# Edge cases
# --------------------------------------------------------------------------- #


def test_empty_links_df(config: ClientConfig) -> None:
    page = _page("/foo", PageType.LOCAL_LANDING)
    registry = SiteRegistry([page], config)
    assert duplicate_links.run(registry, _empty_links_df(), config) == []


def test_multiple_pairs_yield_separate_violations(config: ClientConfig) -> None:
    a = _page("/a", PageType.LOCAL_LANDING)
    b = _page("/b", PageType.LOCAL_LANDING)
    registry = SiteRegistry([a, b], config)
    links = _links_df(
        [
            ("/a", "/x", "body text"),
            ("/a", "/x", "more body"),
            ("/b", "/x", "different anchor"),
            ("/b", "/x", "yet another"),
        ]
    )
    violations = duplicate_links.run(registry, links, config)
    assert len(violations) == 2
    assert {v.source_url for v in violations} == {a.url, b.url}
