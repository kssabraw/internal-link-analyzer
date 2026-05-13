"""Tests for engine.registry (SiteRegistry)."""

from pathlib import Path

import pytest

from engine.classifier import PageClassification, PageType
from engine.config import ClientConfig, load as load_config
from engine.registry import SiteRegistry

FIXTURE = Path(__file__).parent / "fixtures" / "sample_config.yml"


def _page(
    url: str,
    page_type: PageType,
    *,
    location: str | None = None,
    service: str | None = None,
    subservice: str | None = None,
    neighborhood: str | None = None,
    bio_name: str | None = None,
    blog_slug: str | None = None,
    raw_path: str | None = None,
) -> PageClassification:
    """Construct a PageClassification with sane defaults for tests."""
    return PageClassification(
        url=url,
        page_type=page_type,
        location=location,
        service=service,
        subservice=subservice,
        neighborhood=neighborhood,
        bio_name=bio_name,
        blog_slug=blog_slug,
        raw_path=raw_path or url.split("example.com", 1)[-1] or "/",
    )


@pytest.fixture
def config() -> ClientConfig:
    return load_config(FIXTURE)


@pytest.fixture
def pages() -> list[PageClassification]:
    """A small synthetic site exercising every page type and parent relationship."""
    return [
        _page("https://example.com/", PageType.HOME, raw_path="/"),
        _page("https://example.com/about-us", PageType.ABOUT_US),
        _page(
            "https://example.com/about-us/jane-doe",
            PageType.BIO,
            bio_name="jane-doe",
        ),
        _page(
            "https://example.com/about-us/john-smith",
            PageType.BIO,
            bio_name="john-smith",
        ),
        _page("https://example.com/contact-us", PageType.CONTACT_US),
        _page("https://example.com/privacy-policy", PageType.PRIVACY_POLICY),
        _page(
            "https://example.com/plumber",
            PageType.TOP_LEVEL_SERVICE,
            service="plumber",
        ),
        _page(
            "https://example.com/electrician",
            PageType.TOP_LEVEL_SERVICE,
            service="electrician",
        ),
        _page(
            "https://example.com/los-angeles",
            PageType.TOP_LEVEL_LOCATION,
            location="los-angeles",
        ),
        _page(
            "https://example.com/chicago",
            PageType.TOP_LEVEL_LOCATION,
            location="chicago",
        ),
        _page(
            "https://example.com/los-angeles/plumber",
            PageType.LOCAL_LANDING,
            location="los-angeles",
            service="plumber",
        ),
        _page(
            "https://example.com/chicago/plumber",
            PageType.LOCAL_LANDING,
            location="chicago",
            service="plumber",
        ),
        _page(
            "https://example.com/plumber/24-hour",
            PageType.SUB_SERVICE,
            service="plumber",
            subservice="24-hour",
        ),
        _page(
            "https://example.com/los-angeles/plumber/24-hour",
            PageType.SUBSERVICE_LANDING,
            location="los-angeles",
            service="plumber",
            subservice="24-hour",
        ),
        _page(
            "https://example.com/los-angeles/los-feliz",
            PageType.NEIGHBORHOOD,
            location="los-angeles",
            neighborhood="los-feliz",
        ),
        _page(
            "https://example.com/los-angeles/los-feliz/plumber",
            PageType.NEIGHBORHOOD_SERVICE,
            location="los-angeles",
            neighborhood="los-feliz",
            service="plumber",
        ),
        _page("https://example.com/blog", PageType.BLOG_ARCHIVE),
        _page(
            "https://example.com/blog/post-a",
            PageType.BLOG_POST,
            blog_slug="post-a",
        ),
        _page(
            "https://example.com/blog/post-b",
            PageType.BLOG_POST,
            blog_slug="post-b",
        ),
    ]


@pytest.fixture
def registry(
    pages: list[PageClassification], config: ClientConfig
) -> SiteRegistry:
    return SiteRegistry(pages, config)


# --------------------------------------------------------------------------- #
# Construction
# --------------------------------------------------------------------------- #


def test_empty_registry_does_not_crash(config: ClientConfig) -> None:
    reg = SiteRegistry([], config)
    assert reg.all_pages() == []
    assert reg.get_by_url("https://example.com/anything") is None
    assert reg.get_by_type(PageType.HOME) == []
    assert reg.get_top_level_service("plumber") is None
    assert reg.get_top_level_location("los-angeles") is None
    assert reg.get_local_landing_page("los-angeles", "plumber") is None
    assert reg.get_subservice("plumber", "24-hour") is None
    assert reg.get_neighborhood("los-angeles", "los-feliz") is None
    assert reg.get_blog_posts() == []
    assert reg.get_canonical_conflicts() == []


def test_all_pages_returns_full_list(
    registry: SiteRegistry, pages: list[PageClassification]
) -> None:
    assert len(registry.all_pages()) == len(pages)


# --------------------------------------------------------------------------- #
# Simple lookups
# --------------------------------------------------------------------------- #


def test_get_by_url_hit(registry: SiteRegistry) -> None:
    p = registry.get_by_url("https://example.com/plumber/")
    assert p is not None and p.page_type == PageType.TOP_LEVEL_SERVICE


def test_get_by_url_normalizes_input(registry: SiteRegistry) -> None:
    """Trailing slash, scheme, and case all normalize before lookup."""
    p1 = registry.get_by_url("https://example.com/Plumber/")
    p2 = registry.get_by_url("example.com/plumber")
    p3 = registry.get_by_url("/plumber")
    assert p1 is not None and p2 is not None and p3 is not None
    assert p1.service == p2.service == p3.service == "plumber"


def test_get_by_url_miss(registry: SiteRegistry) -> None:
    assert registry.get_by_url("https://example.com/nonexistent") is None


def test_get_by_type(registry: SiteRegistry) -> None:
    assert len(registry.get_by_type(PageType.TOP_LEVEL_SERVICE)) == 2
    assert len(registry.get_by_type(PageType.BIO)) == 2
    assert registry.get_by_type(PageType.AREAS_WE_SERVE_HUB) == []


def test_get_blog_posts(registry: SiteRegistry) -> None:
    assert len(registry.get_blog_posts()) == 2


# --------------------------------------------------------------------------- #
# Single-key getters: hit + miss
# --------------------------------------------------------------------------- #


def test_get_top_level_service(registry: SiteRegistry) -> None:
    assert registry.get_top_level_service("plumber") is not None
    assert registry.get_top_level_service("hvac") is None


def test_get_top_level_location(registry: SiteRegistry) -> None:
    assert registry.get_top_level_location("los-angeles") is not None
    assert registry.get_top_level_location("seattle") is None


def test_get_subservice(registry: SiteRegistry) -> None:
    p = registry.get_subservice("plumber", "24-hour")
    assert p is not None and p.subservice == "24-hour"
    assert registry.get_subservice("plumber", "weekend") is None
    assert registry.get_subservice("electrician", "24-hour") is None


def test_get_neighborhood(registry: SiteRegistry) -> None:
    p = registry.get_neighborhood("los-angeles", "los-feliz")
    assert p is not None and p.neighborhood == "los-feliz"
    assert registry.get_neighborhood("los-angeles", "venice") is None
    assert registry.get_neighborhood("chicago", "los-feliz") is None


def test_get_local_landing_page(registry: SiteRegistry) -> None:
    p = registry.get_local_landing_page("los-angeles", "plumber")
    assert p is not None and p.location == "los-angeles" and p.service == "plumber"
    assert registry.get_local_landing_page("los-angeles", "electrician") is None


def test_get_local_landing_page_first_wins(config: ClientConfig) -> None:
    """When two URLs classify to the same (loc, svc), return the first encountered."""
    first = _page(
        "https://example.com/la/plumber",
        PageType.LOCAL_LANDING,
        location="los-angeles",
        service="plumber",
        raw_path="/la/plumber",
    )
    second = _page(
        "https://example.com/los-angeles/plumber",
        PageType.LOCAL_LANDING,
        location="los-angeles",
        service="plumber",
        raw_path="/los-angeles/plumber",
    )
    reg = SiteRegistry([first, second], config)
    p = reg.get_local_landing_page("los-angeles", "plumber")
    assert p is first


# --------------------------------------------------------------------------- #
# List getters
# --------------------------------------------------------------------------- #


def test_get_local_landing_pages_for_service(registry: SiteRegistry) -> None:
    pages = registry.get_local_landing_pages_for_service("plumber")
    assert len(pages) == 2
    assert {p.location for p in pages} == {"los-angeles", "chicago"}
    assert registry.get_local_landing_pages_for_service("hvac") == []


def test_get_local_landing_pages_for_location(registry: SiteRegistry) -> None:
    pages = registry.get_local_landing_pages_for_location("los-angeles")
    assert len(pages) == 1
    assert registry.get_local_landing_pages_for_location("seattle") == []


def test_get_subservice_landing_pages(registry: SiteRegistry) -> None:
    pages = registry.get_subservice_landing_pages("los-angeles", "plumber")
    assert len(pages) == 1
    assert pages[0].subservice == "24-hour"
    assert registry.get_subservice_landing_pages("chicago", "plumber") == []


def test_get_neighborhoods_for_location(registry: SiteRegistry) -> None:
    pages = registry.get_neighborhoods_for_location("los-angeles")
    assert len(pages) == 1
    assert registry.get_neighborhoods_for_location("chicago") == []


def test_get_neighborhood_service_pages(registry: SiteRegistry) -> None:
    pages = registry.get_neighborhood_service_pages("los-angeles", "los-feliz")
    assert len(pages) == 1
    assert pages[0].service == "plumber"
    assert (
        registry.get_neighborhood_service_pages("los-angeles", "venice") == []
    )


# --------------------------------------------------------------------------- #
# get_parent
# --------------------------------------------------------------------------- #


def test_parent_of_local_landing_is_top_level_location(
    registry: SiteRegistry,
) -> None:
    ll = registry.get_local_landing_page("los-angeles", "plumber")
    parent = registry.get_parent(ll)
    assert parent is not None and parent.page_type == PageType.TOP_LEVEL_LOCATION
    assert parent.location == "los-angeles"


def test_parent_of_sub_service_is_top_level_service(
    registry: SiteRegistry,
) -> None:
    sub = registry.get_subservice("plumber", "24-hour")
    parent = registry.get_parent(sub)
    assert parent is not None and parent.page_type == PageType.TOP_LEVEL_SERVICE
    assert parent.service == "plumber"


def test_parent_of_subservice_landing_is_local_landing(
    registry: SiteRegistry,
) -> None:
    sub_ll = registry.get_by_type(PageType.SUBSERVICE_LANDING)[0]
    parent = registry.get_parent(sub_ll)
    assert parent is not None and parent.page_type == PageType.LOCAL_LANDING
    assert parent.location == "los-angeles" and parent.service == "plumber"


def test_parent_of_neighborhood_is_top_level_location(
    registry: SiteRegistry,
) -> None:
    nb = registry.get_neighborhood("los-angeles", "los-feliz")
    parent = registry.get_parent(nb)
    assert parent is not None and parent.page_type == PageType.TOP_LEVEL_LOCATION


def test_parent_of_neighborhood_service_is_neighborhood(
    registry: SiteRegistry,
) -> None:
    nb_svc = registry.get_neighborhood_service_pages(
        "los-angeles", "los-feliz"
    )[0]
    parent = registry.get_parent(nb_svc)
    assert parent is not None and parent.page_type == PageType.NEIGHBORHOOD
    assert parent.neighborhood == "los-feliz"


def test_parent_of_bio_is_about_us(registry: SiteRegistry) -> None:
    bio = registry.get_by_type(PageType.BIO)[0]
    parent = registry.get_parent(bio)
    assert parent is not None and parent.page_type == PageType.ABOUT_US


def test_parent_of_bio_returns_none_if_about_us_missing(
    config: ClientConfig,
) -> None:
    bio = _page(
        "https://example.com/about-us/jane-doe",
        PageType.BIO,
        bio_name="jane-doe",
    )
    reg = SiteRegistry([bio], config)
    assert reg.get_parent(bio) is None


def test_parent_of_blog_post_is_blog_archive(registry: SiteRegistry) -> None:
    post = registry.get_blog_posts()[0]
    parent = registry.get_parent(post)
    assert parent is not None and parent.page_type == PageType.BLOG_ARCHIVE


def test_parent_of_top_level_pages_is_none(registry: SiteRegistry) -> None:
    home = registry.get_by_type(PageType.HOME)[0]
    tls = registry.get_top_level_service("plumber")
    tll = registry.get_top_level_location("los-angeles")
    about = registry.get_by_type(PageType.ABOUT_US)[0]
    blog_archive = registry.get_by_type(PageType.BLOG_ARCHIVE)[0]
    for p in (home, tls, tll, about, blog_archive):
        assert registry.get_parent(p) is None


def test_parent_strict_when_intermediate_missing(config: ClientConfig) -> None:
    """SUBSERVICE_LANDING parent is None if its LOCAL_LANDING is absent
    (resolved ambiguity #2: strict semantics, no grandparent fallback)."""
    sub_ll = _page(
        "https://example.com/los-angeles/plumber/24-hour",
        PageType.SUBSERVICE_LANDING,
        location="los-angeles",
        service="plumber",
        subservice="24-hour",
    )
    tll = _page(
        "https://example.com/los-angeles",
        PageType.TOP_LEVEL_LOCATION,
        location="los-angeles",
    )
    reg = SiteRegistry([sub_ll, tll], config)
    assert reg.get_parent(sub_ll) is None


# --------------------------------------------------------------------------- #
# Canonical conflicts
# --------------------------------------------------------------------------- #


def test_canonical_conflicts_clusters_duplicates(config: ClientConfig) -> None:
    a = _page(
        "https://example.com/los-angeles/plumber",
        PageType.LOCAL_LANDING,
        location="los-angeles",
        service="plumber",
        raw_path="/los-angeles/plumber",
    )
    b = _page(
        "https://example.com/la/plumber",
        PageType.LOCAL_LANDING,
        location="los-angeles",
        service="plumber",
        raw_path="/la/plumber",
    )
    standalone = _page(
        "https://example.com/chicago/plumber",
        PageType.LOCAL_LANDING,
        location="chicago",
        service="plumber",
    )
    reg = SiteRegistry([a, b, standalone], config)
    conflicts = reg.get_canonical_conflicts()
    assert len(conflicts) == 1
    assert set(conflicts[0]) == {a, b}


def test_canonical_conflicts_distinguishes_by_blog_slug(
    config: ClientConfig,
) -> None:
    """Per resolved ambiguity #1: blog posts with different slugs DO NOT cluster."""
    a = _page(
        "https://example.com/blog/post-a",
        PageType.BLOG_POST,
        blog_slug="post-a",
    )
    b = _page(
        "https://example.com/blog/post-b",
        PageType.BLOG_POST,
        blog_slug="post-b",
    )
    reg = SiteRegistry([a, b], config)
    assert reg.get_canonical_conflicts() == []


def test_canonical_conflicts_clusters_duplicate_blog_slugs(
    config: ClientConfig,
) -> None:
    a = _page(
        "https://example.com/blog/post-a",
        PageType.BLOG_POST,
        blog_slug="post-a",
        raw_path="/blog/post-a",
    )
    b = _page(
        "https://example.com/blog/2024/post-a",
        PageType.BLOG_POST,
        blog_slug="post-a",
        raw_path="/blog/2024/post-a",
    )
    reg = SiteRegistry([a, b], config)
    conflicts = reg.get_canonical_conflicts()
    assert len(conflicts) == 1
    assert {p.url for p in conflicts[0]} == {a.url, b.url}


def test_canonical_conflicts_distinguishes_bios_by_name(
    config: ClientConfig,
) -> None:
    jane = _page(
        "https://example.com/about-us/jane",
        PageType.BIO,
        bio_name="jane",
    )
    john = _page(
        "https://example.com/about-us/john",
        PageType.BIO,
        bio_name="john",
    )
    reg = SiteRegistry([jane, john], config)
    assert reg.get_canonical_conflicts() == []


def test_canonical_conflicts_excludes_unknown(config: ClientConfig) -> None:
    a = _page(
        "https://example.com/foo",
        PageType.UNKNOWN,
        raw_path="/foo",
    )
    b = _page(
        "https://example.com/bar",
        PageType.UNKNOWN,
        raw_path="/bar",
    )
    reg = SiteRegistry([a, b], config)
    assert reg.get_canonical_conflicts() == []


def test_canonical_conflicts_no_duplicates_returns_empty(
    registry: SiteRegistry,
) -> None:
    assert registry.get_canonical_conflicts() == []
