"""Tests for engine.auditors.canonical_conflicts."""

from pathlib import Path

import pandas as pd
import pytest

from engine.auditors import canonical_conflicts
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


def _empty_links_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "source_url": pd.Series([], dtype="object"),
            "target_url": pd.Series([], dtype="object"),
            "anchor_text": pd.Series([], dtype="object"),
            "link_type": pd.Series([], dtype="object"),
        }
    )


def test_no_violations_when_no_duplicates(config: ClientConfig) -> None:
    pages = [
        _page(
            "/los-angeles/plumber",
            PageType.LOCAL_LANDING,
            location="los-angeles",
            service="plumber",
        ),
        _page(
            "/chicago/plumber",
            PageType.LOCAL_LANDING,
            location="chicago",
            service="plumber",
        ),
    ]
    registry = SiteRegistry(pages, config)
    assert canonical_conflicts.run(registry, _empty_links_df(), config) == []


def test_cluster_of_two_emits_one_violation(config: ClientConfig) -> None:
    a = _page(
        "/los-angeles/plumber",
        PageType.LOCAL_LANDING,
        location="los-angeles",
        service="plumber",
    )
    b = _page(
        "/la/plumber",
        PageType.LOCAL_LANDING,
        location="los-angeles",
        service="plumber",
    )
    registry = SiteRegistry([a, b], config)

    violations = canonical_conflicts.run(registry, _empty_links_df(), config)
    assert len(violations) == 1
    v = violations[0]
    assert v.rule == "canonical_conflicts.duplicate_local_landing"
    assert v.severity == Severity.WARNING
    assert v.source_url == b.url  # duplicate is b
    assert v.expected == a.url  # a is the canonical (first in list)
    assert v.actual == b.url


def test_cluster_of_three_emits_two_violations(config: ClientConfig) -> None:
    a = _page("/p1", PageType.TOP_LEVEL_SERVICE, service="plumber")
    b = _page("/p2", PageType.TOP_LEVEL_SERVICE, service="plumber")
    c = _page("/p3", PageType.TOP_LEVEL_SERVICE, service="plumber")
    registry = SiteRegistry([a, b, c], config)

    violations = canonical_conflicts.run(registry, _empty_links_df(), config)
    assert len(violations) == 2
    assert {v.source_url for v in violations} == {b.url, c.url}
    assert all(v.expected == a.url for v in violations)
    assert all(
        v.rule == "canonical_conflicts.duplicate_top_level_service"
        for v in violations
    )


def test_multiple_clusters_yield_independent_violations(
    config: ClientConfig,
) -> None:
    a1 = _page(
        "/la/plumber",
        PageType.LOCAL_LANDING,
        location="los-angeles",
        service="plumber",
    )
    a2 = _page(
        "/los-angeles/plumber",
        PageType.LOCAL_LANDING,
        location="los-angeles",
        service="plumber",
    )
    b1 = _page("/p1", PageType.TOP_LEVEL_SERVICE, service="plumber")
    b2 = _page("/p2", PageType.TOP_LEVEL_SERVICE, service="plumber")
    standalone = _page("/", PageType.HOME)
    registry = SiteRegistry([a1, a2, b1, b2, standalone], config)

    violations = canonical_conflicts.run(registry, _empty_links_df(), config)
    rules = {v.rule for v in violations}
    assert rules == {
        "canonical_conflicts.duplicate_local_landing",
        "canonical_conflicts.duplicate_top_level_service",
    }
    assert len(violations) == 2


def test_rule_slug_includes_page_type(config: ClientConfig) -> None:
    a = _page(
        "/blog/post-a",
        PageType.BLOG_POST,
        blog_slug="x",
    )
    b = _page(
        "/blog/2024/post-a",
        PageType.BLOG_POST,
        blog_slug="x",
    )
    registry = SiteRegistry([a, b], config)

    violations = canonical_conflicts.run(registry, _empty_links_df(), config)
    assert len(violations) == 1
    assert violations[0].rule == "canonical_conflicts.duplicate_blog_post"


def test_empty_registry(config: ClientConfig) -> None:
    registry = SiteRegistry([], config)
    assert canonical_conflicts.run(registry, _empty_links_df(), config) == []
