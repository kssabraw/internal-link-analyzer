"""Tests for engine.auditors.click_depth."""

from pathlib import Path

import pandas as pd
import pytest

from engine.auditors import click_depth
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
# Reachable within budget
# --------------------------------------------------------------------------- #


def test_page_at_depth_one_passes(config: ClientConfig) -> None:
    home = _page("/", PageType.HOME)
    svc = _page("/plumber", PageType.TOP_LEVEL_SERVICE, service="plumber")
    registry = SiteRegistry([home, svc], config)
    links = _links_df([("/", "/plumber")])

    assert click_depth.run(registry, links, config) == []


def test_page_at_depth_three_passes(config: ClientConfig) -> None:
    home = _page("/", PageType.HOME)
    a = _page("/plumber", PageType.TOP_LEVEL_SERVICE, service="plumber")
    b = _page(
        "/los-angeles",
        PageType.TOP_LEVEL_LOCATION,
        location="los-angeles",
    )
    c = _page(
        "/los-angeles/plumber",
        PageType.LOCAL_LANDING,
        location="los-angeles",
        service="plumber",
    )
    registry = SiteRegistry([home, a, b, c], config)
    # / -> /plumber -> /los-angeles -> /los-angeles/plumber (depth 3)
    links = _links_df(
        [
            ("/", "/plumber"),
            ("/plumber", "/los-angeles"),
            ("/los-angeles", "/los-angeles/plumber"),
        ]
    )

    assert click_depth.run(registry, links, config) == []


# --------------------------------------------------------------------------- #
# Exceeds budget
# --------------------------------------------------------------------------- #


def test_page_at_depth_four_fires_violation(config: ClientConfig) -> None:
    home = _page("/", PageType.HOME)
    a = _page("/plumber", PageType.TOP_LEVEL_SERVICE, service="plumber")
    b = _page(
        "/los-angeles",
        PageType.TOP_LEVEL_LOCATION,
        location="los-angeles",
    )
    c = _page(
        "/los-angeles/plumber",
        PageType.LOCAL_LANDING,
        location="los-angeles",
        service="plumber",
    )
    d = _page(
        "/los-angeles/plumber/24-hour",
        PageType.SUBSERVICE_LANDING,
        location="los-angeles",
        service="plumber",
        subservice="24-hour",
    )
    registry = SiteRegistry([home, a, b, c, d], config)
    # Chain: / -> a -> b -> c -> d (depth 4)
    links = _links_df(
        [
            ("/", "/plumber"),
            ("/plumber", "/los-angeles"),
            ("/los-angeles", "/los-angeles/plumber"),
            ("/los-angeles/plumber", "/los-angeles/plumber/24-hour"),
        ]
    )

    violations = click_depth.run(registry, links, config)
    assert len(violations) == 1
    v = violations[0]
    assert v.rule == "click_depth.exceeds_three_clicks"
    assert v.severity == Severity.WARNING
    assert v.source_url == d.url
    assert "4 clicks from home" in v.actual


# --------------------------------------------------------------------------- #
# Unreachable
# --------------------------------------------------------------------------- #


def test_unreachable_page_fires_critical(config: ClientConfig) -> None:
    home = _page("/", PageType.HOME)
    orphan = _page("/plumber", PageType.TOP_LEVEL_SERVICE, service="plumber")
    registry = SiteRegistry([home, orphan], config)
    # No links at all - orphan is unreachable
    violations = click_depth.run(registry, _empty_links_df(), config)
    assert len(violations) == 1
    v = violations[0]
    assert v.rule == "click_depth.unreachable"
    assert v.severity == Severity.CRITICAL
    assert v.source_url == orphan.url


# --------------------------------------------------------------------------- #
# Page type filtering
# --------------------------------------------------------------------------- #


def test_blog_post_is_exempt(config: ClientConfig) -> None:
    """Blog posts can be arbitrarily deep without firing."""
    home = _page("/", PageType.HOME)
    post = _page(
        "/blog/post-a", PageType.BLOG_POST, blog_slug="post-a"
    )
    registry = SiteRegistry([home, post], config)

    # Post is unreachable, but should be exempt from click_depth audit
    assert click_depth.run(registry, _empty_links_df(), config) == []


def test_home_itself_does_not_fire(config: ClientConfig) -> None:
    home = _page("/", PageType.HOME)
    registry = SiteRegistry([home], config)
    assert click_depth.run(registry, _empty_links_df(), config) == []


def test_about_us_not_audited(config: ClientConfig) -> None:
    """ABOUT_US is not a commercial page; click-depth doesn't apply."""
    home = _page("/", PageType.HOME)
    about = _page("/about-us", PageType.ABOUT_US)
    registry = SiteRegistry([home, about], config)
    # about-us is unreachable - but not commercial, so no violation
    assert click_depth.run(registry, _empty_links_df(), config) == []


# --------------------------------------------------------------------------- #
# Edge cases
# --------------------------------------------------------------------------- #


def test_no_home_yields_no_violations(config: ClientConfig) -> None:
    """Without a HOME page, click-depth cannot be computed; auditor no-ops."""
    svc = _page("/plumber", PageType.TOP_LEVEL_SERVICE, service="plumber")
    registry = SiteRegistry([svc], config)
    assert click_depth.run(registry, _empty_links_df(), config) == []


def test_empty_registry(config: ClientConfig) -> None:
    registry = SiteRegistry([], config)
    assert click_depth.run(registry, _empty_links_df(), config) == []


def test_bfs_uses_shortest_path(config: ClientConfig) -> None:
    """A page reachable via a depth-2 path AND a depth-5 path uses depth 2."""
    home = _page("/", PageType.HOME)
    a = _page(
        "/los-angeles",
        PageType.TOP_LEVEL_LOCATION,
        location="los-angeles",
    )
    b = _page("/plumber", PageType.TOP_LEVEL_SERVICE, service="plumber")
    target = _page(
        "/los-angeles/plumber",
        PageType.LOCAL_LANDING,
        location="los-angeles",
        service="plumber",
    )
    registry = SiteRegistry([home, a, b, target], config)
    # Two paths:
    #   /  -> /los-angeles -> /los-angeles/plumber (depth 2)
    #   /  -> /plumber -> [cycle through a few hops] (longer)
    # BFS uses the shorter path.
    links = _links_df(
        [
            ("/", "/los-angeles"),
            ("/", "/plumber"),
            ("/los-angeles", "/los-angeles/plumber"),
            ("/plumber", "/los-angeles"),  # redundant longer route
        ]
    )
    # target ends up at depth 2; well within budget
    assert click_depth.run(registry, links, config) == []


def test_multiple_violations_independently(config: ClientConfig) -> None:
    home = _page("/", PageType.HOME)
    orphan_svc = _page("/plumber", PageType.TOP_LEVEL_SERVICE, service="plumber")
    deep = _page(
        "/los-angeles/plumber/24-hour",
        PageType.SUBSERVICE_LANDING,
        location="los-angeles",
        service="plumber",
        subservice="24-hour",
    )
    intermediate = _page(
        "/los-angeles",
        PageType.TOP_LEVEL_LOCATION,
        location="los-angeles",
    )
    intermediate2 = _page(
        "/los-angeles/plumber",
        PageType.LOCAL_LANDING,
        location="los-angeles",
        service="plumber",
    )
    intermediate3 = _page(
        "/los-angeles/plumber/extra",
        PageType.LOCAL_LANDING,  # made-up depth padding
        location="los-angeles",
        service="plumber",
    )
    registry = SiteRegistry(
        [home, orphan_svc, deep, intermediate, intermediate2, intermediate3],
        config,
    )
    # Path to deep: / -> /la -> /la/plumber -> /la/plumber/extra -> /la/plumber/24-hour (depth 4)
    links = _links_df(
        [
            ("/", "/los-angeles"),
            ("/los-angeles", "/los-angeles/plumber"),
            ("/los-angeles/plumber", "/los-angeles/plumber/extra"),
            ("/los-angeles/plumber/extra", "/los-angeles/plumber/24-hour"),
        ]
    )
    violations = click_depth.run(registry, links, config)
    rules = {(v.rule, v.source_url) for v in violations}
    assert ("click_depth.unreachable", orphan_svc.url) in rules
    assert ("click_depth.exceeds_three_clicks", deep.url) in rules
