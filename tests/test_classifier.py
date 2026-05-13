"""Tests for engine.classifier."""

from pathlib import Path

import pytest

from engine.classifier import (
    PageType,
    _normalize_url,
    classify,
    classify_all,
)
from engine.config import ClientConfig, load as load_config

FIXTURE = Path(__file__).parent / "fixtures" / "sample_config.yml"


@pytest.fixture
def config() -> ClientConfig:
    return load_config(FIXTURE)


# --------------------------------------------------------------------------- #
# URL normalization
# --------------------------------------------------------------------------- #


def test_normalize_strips_scheme_host_and_trailing_slash() -> None:
    assert _normalize_url("https://example.com/about-us/") == "/about-us"


def test_normalize_root() -> None:
    assert _normalize_url("https://example.com/") == "/"
    assert _normalize_url("https://example.com") == "/"


def test_normalize_strips_query_and_fragment() -> None:
    assert _normalize_url("https://example.com/foo/?q=1#frag") == "/foo"


def test_normalize_lowercases() -> None:
    assert _normalize_url("https://example.com/About-Us/") == "/about-us"


# --------------------------------------------------------------------------- #
# Fixed page types
# --------------------------------------------------------------------------- #


def test_home(config: ClientConfig) -> None:
    c = classify("https://example.com/", config)
    assert c is not None and c.page_type == PageType.HOME


def test_about_us(config: ClientConfig) -> None:
    c = classify("https://example.com/about-us/", config)
    assert c is not None and c.page_type == PageType.ABOUT_US


def test_bio_populates_name(config: ClientConfig) -> None:
    c = classify("https://example.com/about-us/jane-doe/", config)
    assert c is not None
    assert c.page_type == PageType.BIO
    assert c.bio_name == "jane-doe"


def test_contact_us(config: ClientConfig) -> None:
    c = classify("https://example.com/contact-us/", config)
    assert c is not None and c.page_type == PageType.CONTACT_US


def test_privacy_policy(config: ClientConfig) -> None:
    c = classify("https://example.com/privacy-policy/", config)
    assert c is not None and c.page_type == PageType.PRIVACY_POLICY


def test_services_hub(config: ClientConfig) -> None:
    c = classify("https://example.com/services/", config)
    assert c is not None and c.page_type == PageType.SERVICES_HUB


def test_areas_we_serve_hub(config: ClientConfig) -> None:
    c = classify("https://example.com/areas-we-serve/", config)
    assert c is not None and c.page_type == PageType.AREAS_WE_SERVE_HUB


def test_blog_archive(config: ClientConfig) -> None:
    c = classify("https://example.com/blog/", config)
    assert c is not None and c.page_type == PageType.BLOG_ARCHIVE


def test_blog_post(config: ClientConfig) -> None:
    c = classify("https://example.com/blog/how-to-fix-a-pipe/", config)
    assert c is not None
    assert c.page_type == PageType.BLOG_POST
    assert c.blog_slug == "how-to-fix-a-pipe"


# --------------------------------------------------------------------------- #
# Top-level service and location
# --------------------------------------------------------------------------- #


def test_top_level_service(config: ClientConfig) -> None:
    c = classify("https://example.com/plumber/", config)
    assert c is not None
    assert c.page_type == PageType.TOP_LEVEL_SERVICE
    assert c.service == "plumber"
    assert c.confidence == 1.0


def test_top_level_location(config: ClientConfig) -> None:
    c = classify("https://example.com/los-angeles/", config)
    assert c is not None
    assert c.page_type == PageType.TOP_LEVEL_LOCATION
    assert c.location == "los-angeles"
    assert c.confidence == 1.0


def test_location_alias_resolves_to_canonical(config: ClientConfig) -> None:
    c = classify("https://example.com/la/", config)
    assert c is not None
    assert c.page_type == PageType.TOP_LEVEL_LOCATION
    assert c.location == "los-angeles"


# --------------------------------------------------------------------------- #
# Local landing pages - all three URL shapes
# --------------------------------------------------------------------------- #


def test_local_landing_location_first_nested(config: ClientConfig) -> None:
    """SOP-canonical: /[location]/[service]/"""
    c = classify("https://example.com/los-angeles/plumber/", config)
    assert c is not None
    assert c.page_type == PageType.LOCAL_LANDING
    assert c.location == "los-angeles"
    assert c.service == "plumber"
    assert c.confidence == 1.0


def test_local_landing_service_first_nested(config: ClientConfig) -> None:
    """WHIT variant: /[service]/[location]/"""
    c = classify("https://example.com/plumber/los-angeles/", config)
    assert c is not None
    assert c.page_type == PageType.LOCAL_LANDING
    assert c.location == "los-angeles"
    assert c.service == "plumber"
    assert c.confidence == 1.0


def test_local_landing_flat(config: ClientConfig) -> None:
    """WHIT variant: flat slug /[service]-[location]"""
    c = classify("https://example.com/plumber-los-angeles", config)
    assert c is not None
    assert c.page_type == PageType.LOCAL_LANDING
    assert c.location == "los-angeles"
    assert c.service == "plumber"
    assert c.confidence == 0.8


def test_local_landing_flat_with_in_infix(config: ClientConfig) -> None:
    """WHIT variant: /[service]-in-[location]"""
    c = classify("https://example.com/plumber-in-los-angeles", config)
    assert c is not None
    assert c.page_type == PageType.LOCAL_LANDING
    assert c.service == "plumber"
    assert c.location == "los-angeles"
    assert c.confidence == 0.8


def test_local_landing_flat_service_plus_neighborhood(
    config: ClientConfig,
) -> None:
    """Per ambiguity #3: /[service]-[neighborhood] classifies as LOCAL_LANDING
    with the neighborhood's parent location inferred."""
    c = classify("https://example.com/plumber-los-feliz", config)
    assert c is not None
    assert c.page_type == PageType.LOCAL_LANDING
    assert c.service == "plumber"
    assert c.location == "los-angeles"
    assert c.confidence == 0.8


def test_local_landing_redundant_location_with_in_infix(
    config: ClientConfig,
) -> None:
    """WHIT redundant-location pattern: /[loc]/[svc]-in-[same-loc]."""
    c = classify("https://example.com/los-angeles/plumber-in-los-angeles", config)
    assert c is not None
    assert c.page_type == PageType.LOCAL_LANDING
    assert c.location == "los-angeles"
    assert c.service == "plumber"
    assert c.confidence == 0.8


def test_local_landing_redundant_location_hyphen_split(
    config: ClientConfig,
) -> None:
    """Redundant location without -in- infix: /[loc]/[svc]-[same-loc]."""
    c = classify("https://example.com/los-angeles/plumber-los-angeles", config)
    assert c is not None
    assert c.page_type == PageType.LOCAL_LANDING
    assert c.location == "los-angeles"
    assert c.service == "plumber"
    assert c.confidence == 0.8


# --------------------------------------------------------------------------- #
# Sub-service and subservice landing
# --------------------------------------------------------------------------- #


def test_sub_service(config: ClientConfig) -> None:
    c = classify("https://example.com/plumber/24-hour/", config)
    assert c is not None
    assert c.page_type == PageType.SUB_SERVICE
    assert c.service == "plumber"
    assert c.subservice == "24-hour"
    assert c.confidence == 1.0


def test_subservice_landing(config: ClientConfig) -> None:
    c = classify("https://example.com/los-angeles/plumber/24-hour/", config)
    assert c is not None
    assert c.page_type == PageType.SUBSERVICE_LANDING
    assert c.location == "los-angeles"
    assert c.service == "plumber"
    assert c.subservice == "24-hour"
    assert c.confidence == 1.0


# --------------------------------------------------------------------------- #
# Neighborhood and neighborhood service
# --------------------------------------------------------------------------- #


def test_neighborhood(config: ClientConfig) -> None:
    c = classify("https://example.com/los-angeles/los-feliz/", config)
    assert c is not None
    assert c.page_type == PageType.NEIGHBORHOOD
    assert c.location == "los-angeles"
    assert c.neighborhood == "los-feliz"


def test_neighborhood_service_canonical(config: ClientConfig) -> None:
    """SOP-canonical: /[location]/[neighborhood]/[service]/"""
    c = classify("https://example.com/los-angeles/los-feliz/plumber/", config)
    assert c is not None
    assert c.page_type == PageType.NEIGHBORHOOD_SERVICE
    assert c.location == "los-angeles"
    assert c.neighborhood == "los-feliz"
    assert c.service == "plumber"
    assert c.confidence == 1.0


def test_neighborhood_service_service_first_nested(config: ClientConfig) -> None:
    """Per ambiguity #2: /[service]/[neighborhood]/ classifies as
    NEIGHBORHOOD_SERVICE with the parent location inferred."""
    c = classify("https://example.com/plumber/los-feliz/", config)
    assert c is not None
    assert c.page_type == PageType.NEIGHBORHOOD_SERVICE
    assert c.location == "los-angeles"
    assert c.neighborhood == "los-feliz"
    assert c.service == "plumber"
    assert c.confidence == 0.8


def test_neighborhood_service_inline_neighborhood_in_segment2(
    config: ClientConfig,
) -> None:
    """WHIT variant: /[location]/[service]-[neighborhood]"""
    c = classify("https://example.com/los-angeles/plumber-los-feliz", config)
    assert c is not None
    assert c.page_type == PageType.NEIGHBORHOOD_SERVICE
    assert c.location == "los-angeles"
    assert c.neighborhood == "los-feliz"
    assert c.service == "plumber"
    assert c.confidence == 0.8


# --------------------------------------------------------------------------- #
# Unknown and ignored
# --------------------------------------------------------------------------- #


def test_unknown(config: ClientConfig) -> None:
    c = classify("https://example.com/some-random-page/", config)
    assert c is not None
    assert c.page_type == PageType.UNKNOWN
    assert c.confidence == 0.0


def test_ignored_url_returns_none(config: ClientConfig) -> None:
    """URLs matching url_patterns_to_ignore return None, not UNKNOWN."""
    c = classify("https://example.com/cdn-cgi/something", config)
    assert c is None


def test_classify_all_separates_ignored(config: ClientConfig) -> None:
    urls = [
        "https://example.com/",
        "https://example.com/cdn-cgi/foo",
        "https://example.com/plumber/",
    ]
    classifications, ignored = classify_all(urls, config)
    assert len(classifications) == 2
    assert len(ignored) == 1
    assert ignored == ["https://example.com/cdn-cgi/foo"]
    types = {c.page_type for c in classifications}
    assert types == {PageType.HOME, PageType.TOP_LEVEL_SERVICE}


def test_raw_path_populated(config: ClientConfig) -> None:
    c = classify("https://example.com/About-Us/", config)
    assert c is not None
    assert c.raw_path == "/about-us"
