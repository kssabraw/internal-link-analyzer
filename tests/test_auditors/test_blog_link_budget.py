"""Tests for engine.auditors.blog_link_budget."""

from pathlib import Path

import pandas as pd
import pytest

from engine.auditors import blog_link_budget
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


def _post(slug: str) -> PageClassification:
    return _page(f"/blog/{slug}", PageType.BLOG_POST, blog_slug=slug)


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
# Passing case
# --------------------------------------------------------------------------- #


def test_passing_when_exact_budget_met(config: ClientConfig) -> None:
    post = _post("post-a")
    svc = _page("/plumber", PageType.TOP_LEVEL_SERVICE, service="plumber")
    sib_b = _post("post-b")
    sib_c = _post("post-c")
    registry = SiteRegistry([post, svc, sib_b, sib_c], config)
    links = _links_df(
        [
            (post.raw_path, svc.raw_path),
            (post.raw_path, sib_b.raw_path),
            (post.raw_path, sib_c.raw_path),
        ]
    )
    violations = blog_link_budget.run(registry, links, config)
    # post-a meets budget; sibling posts in fixture have their own (broken)
    # budgets which we don't assert about here
    post_a_violations = [v for v in violations if v.source_url == post.url]
    assert post_a_violations == []


# --------------------------------------------------------------------------- #
# Service link budget violations
# --------------------------------------------------------------------------- #


def test_missing_service_link_fires(config: ClientConfig) -> None:
    post = _post("post-a")
    sib_b = _post("post-b")
    sib_c = _post("post-c")
    registry = SiteRegistry([post, sib_b, sib_c], config)
    links = _links_df(
        [
            (post.raw_path, sib_b.raw_path),
            (post.raw_path, sib_c.raw_path),
        ]
    )

    violations = blog_link_budget.run(registry, links, config)
    rules = [v.rule for v in violations]
    assert "blog_link_budget.missing_service_link" in rules
    v = next(v for v in violations if v.rule.endswith("missing_service_link"))
    assert v.source_url == post.url
    assert v.severity == Severity.WARNING


def test_too_many_service_links_fires(config: ClientConfig) -> None:
    post = _post("post-a")
    svc_a = _page("/plumber", PageType.TOP_LEVEL_SERVICE, service="plumber")
    svc_b = _page(
        "/electrician", PageType.TOP_LEVEL_SERVICE, service="electrician"
    )
    sib_b = _post("post-b")
    sib_c = _post("post-c")
    registry = SiteRegistry([post, svc_a, svc_b, sib_b, sib_c], config)
    links = _links_df(
        [
            (post.raw_path, svc_a.raw_path),
            (post.raw_path, svc_b.raw_path),
            (post.raw_path, sib_b.raw_path),
            (post.raw_path, sib_c.raw_path),
        ]
    )

    violations = blog_link_budget.run(registry, links, config)
    rules = [v.rule for v in violations]
    assert "blog_link_budget.too_many_service_links" in rules
    v = next(v for v in violations if v.rule.endswith("too_many_service_links"))
    assert "2 service links" in v.actual


def test_sub_service_counts_toward_service_budget(
    config: ClientConfig,
) -> None:
    post = _post("post-a")
    sub = _page(
        "/plumber/24-hour",
        PageType.SUB_SERVICE,
        service="plumber",
        subservice="24-hour",
    )
    sib_b = _post("post-b")
    sib_c = _post("post-c")
    registry = SiteRegistry([post, sub, sib_b, sib_c], config)
    links = _links_df(
        [
            (post.raw_path, sub.raw_path),
            (post.raw_path, sib_b.raw_path),
            (post.raw_path, sib_c.raw_path),
        ]
    )
    violations = blog_link_budget.run(registry, links, config)
    post_a_violations = [v for v in violations if v.source_url == post.url]
    assert post_a_violations == []


def test_local_landing_does_not_count_toward_service_budget(
    config: ClientConfig,
) -> None:
    """Only TOP_LEVEL_SERVICE and SUB_SERVICE count - landings don't."""
    post = _post("post-a")
    ll = _page(
        "/los-angeles/plumber",
        PageType.LOCAL_LANDING,
        location="los-angeles",
        service="plumber",
    )
    sib_b = _post("post-b")
    sib_c = _post("post-c")
    registry = SiteRegistry([post, ll, sib_b, sib_c], config)
    # Links to a LOCAL_LANDING (not a service page) + 2 silo posts
    links = _links_df(
        [
            (post.raw_path, ll.raw_path),
            (post.raw_path, sib_b.raw_path),
            (post.raw_path, sib_c.raw_path),
        ]
    )
    violations = blog_link_budget.run(registry, links, config)
    rules = [v.rule for v in violations]
    assert "blog_link_budget.missing_service_link" in rules


# --------------------------------------------------------------------------- #
# Silo blog link budget violations
# --------------------------------------------------------------------------- #


def test_too_few_silo_blog_links_zero_fires(config: ClientConfig) -> None:
    post = _post("post-a")
    svc = _page("/plumber", PageType.TOP_LEVEL_SERVICE, service="plumber")
    registry = SiteRegistry([post, svc], config)
    links = _links_df([(post.raw_path, svc.raw_path)])

    violations = blog_link_budget.run(registry, links, config)
    rules = [v.rule for v in violations]
    assert "blog_link_budget.too_few_silo_blog_links" in rules
    v = next(v for v in violations if v.rule.endswith("too_few_silo_blog_links"))
    assert "0 silo" in v.actual


def test_too_few_silo_blog_links_one_fires(config: ClientConfig) -> None:
    post = _post("post-a")
    svc = _page("/plumber", PageType.TOP_LEVEL_SERVICE, service="plumber")
    sib_b = _post("post-b")
    registry = SiteRegistry([post, svc, sib_b], config)
    links = _links_df(
        [
            (post.raw_path, svc.raw_path),
            (post.raw_path, sib_b.raw_path),
        ]
    )

    violations = blog_link_budget.run(registry, links, config)
    v = next(v for v in violations if v.rule.endswith("too_few_silo_blog_links"))
    assert "1 silo" in v.actual


def test_too_many_silo_blog_links_fires(config: ClientConfig) -> None:
    post = _post("post-a")
    svc = _page("/plumber", PageType.TOP_LEVEL_SERVICE, service="plumber")
    siblings = [_post(f"post-{c}") for c in "bcde"]
    registry = SiteRegistry([post, svc, *siblings], config)
    links = _links_df(
        [(post.raw_path, svc.raw_path)]
        + [(post.raw_path, s.raw_path) for s in siblings]
    )

    violations = blog_link_budget.run(registry, links, config)
    v = next(
        v for v in violations if v.rule.endswith("too_many_silo_blog_links")
    )
    assert "4 silo" in v.actual


# --------------------------------------------------------------------------- #
# Both rules in one post
# --------------------------------------------------------------------------- #


def test_both_rules_fire_independently(config: ClientConfig) -> None:
    """A blog post with 0 service links AND 0 silo links emits 2 violations."""
    post = _post("post-a")
    registry = SiteRegistry([post], config)

    violations = blog_link_budget.run(registry, _empty_links_df(), config)
    rules = {v.rule for v in violations}
    assert rules == {
        "blog_link_budget.missing_service_link",
        "blog_link_budget.too_few_silo_blog_links",
    }


# --------------------------------------------------------------------------- #
# Deduplication: duplicate links count once toward the budget
# --------------------------------------------------------------------------- #


def test_duplicate_link_counts_once(config: ClientConfig) -> None:
    """Two links to the same service target count as 1 toward the budget."""
    post = _post("post-a")
    svc = _page("/plumber", PageType.TOP_LEVEL_SERVICE, service="plumber")
    sib_b = _post("post-b")
    sib_c = _post("post-c")
    registry = SiteRegistry([post, svc, sib_b, sib_c], config)
    links = _links_df(
        [
            (post.raw_path, svc.raw_path),
            (post.raw_path, svc.raw_path),  # duplicate
            (post.raw_path, sib_b.raw_path),
            (post.raw_path, sib_c.raw_path),
        ]
    )

    violations = blog_link_budget.run(registry, links, config)
    post_a_violations = [v for v in violations if v.source_url == post.url]
    # post-a passes - duplicate doesn't push service count to 2
    assert post_a_violations == []


# --------------------------------------------------------------------------- #
# Edge cases
# --------------------------------------------------------------------------- #


def test_self_link_does_not_count(config: ClientConfig) -> None:
    """Blog post linking to itself doesn't count as a silo blog link."""
    post = _post("post-a")
    svc = _page("/plumber", PageType.TOP_LEVEL_SERVICE, service="plumber")
    sib_b = _post("post-b")
    registry = SiteRegistry([post, svc, sib_b], config)
    links = _links_df(
        [
            (post.raw_path, svc.raw_path),
            (post.raw_path, post.raw_path),  # self-link
            (post.raw_path, sib_b.raw_path),
        ]
    )

    violations = blog_link_budget.run(registry, links, config)
    # silo count is 1 (just sib_b, self-link excluded) -> too_few fires
    rules = [v.rule for v in violations]
    assert "blog_link_budget.too_few_silo_blog_links" in rules


def test_unclassified_link_targets_dont_count(config: ClientConfig) -> None:
    """Links to URLs not in the registry don't count toward either budget."""
    post = _post("post-a")
    sib_b = _post("post-b")
    sib_c = _post("post-c")
    svc = _page("/plumber", PageType.TOP_LEVEL_SERVICE, service="plumber")
    registry = SiteRegistry([post, sib_b, sib_c, svc], config)
    links = _links_df(
        [
            (post.raw_path, "/some-random-page"),  # not classified
            (post.raw_path, svc.raw_path),
            (post.raw_path, sib_b.raw_path),
            (post.raw_path, sib_c.raw_path),
        ]
    )
    violations = blog_link_budget.run(registry, links, config)
    post_a_violations = [v for v in violations if v.source_url == post.url]
    assert post_a_violations == []


def test_empty_registry(config: ClientConfig) -> None:
    registry = SiteRegistry([], config)
    assert blog_link_budget.run(registry, _empty_links_df(), config) == []


def test_no_blog_posts_no_violations(config: ClientConfig) -> None:
    home = _page("/", PageType.HOME)
    registry = SiteRegistry([home], config)
    assert blog_link_budget.run(registry, _empty_links_df(), config) == []
