"""URL classifier: maps a raw URL to a PageClassification.

Reads the client config to match URL slug tokens against known services,
locations, subservices, and neighborhoods. Returns PageType.UNKNOWN for
any URL that cannot be matched - never guesses.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TypeVar
from urllib.parse import urlparse

import pandas as pd

from engine.config import ClientConfig


class PageType(StrEnum):
    HOME = "home"
    ABOUT_US = "about_us"
    BIO = "bio"
    CONTACT_US = "contact_us"
    PRIVACY_POLICY = "privacy_policy"
    SERVICES_HUB = "services_hub"
    AREAS_WE_SERVE_HUB = "areas_we_serve_hub"
    TOP_LEVEL_SERVICE = "top_level_service"
    TOP_LEVEL_LOCATION = "top_level_location"
    SUB_SERVICE = "sub_service"
    LOCAL_LANDING = "local_landing"
    NEIGHBORHOOD = "neighborhood"
    SUBSERVICE_LANDING = "subservice_landing"
    NEIGHBORHOOD_SERVICE = "neighborhood_service"
    BLOG_ARCHIVE = "blog_archive"
    BLOG_POST = "blog_post"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PageClassification:
    url: str
    page_type: PageType
    location: str | None = None
    service: str | None = None
    subservice: str | None = None
    neighborhood: str | None = None
    bio_name: str | None = None
    blog_slug: str | None = None
    raw_path: str = ""
    confidence: float = 1.0


@dataclass(frozen=True)
class ClassifierIndexes:
    """Lookup tables built once per config; passed to per-URL classification."""

    service_index: dict[str, str]
    """alias or slug -> canonical service slug"""

    location_index: dict[str, str]
    """alias or slug -> canonical location slug"""

    neighborhood_index: dict[str, tuple[str, str]]
    """alias or slug -> (canonical location slug, canonical neighborhood slug)"""

    subservices_by_parent: dict[str, dict[str, str]]
    """canonical parent service slug -> {alias or slug: canonical subservice slug}"""

    ignore_patterns: list[re.Pattern[str]]


def _build_indexes(config: ClientConfig) -> ClassifierIndexes:
    service_index: dict[str, str] = {}
    for svc in config.services:
        service_index[svc.slug] = svc.slug
        for alias in svc.aliases:
            service_index[alias] = svc.slug

    location_index: dict[str, str] = {}
    neighborhood_index: dict[str, tuple[str, str]] = {}
    for loc in config.locations:
        location_index[loc.slug] = loc.slug
        for alias in loc.aliases:
            location_index[alias] = loc.slug
        for nb in loc.neighborhoods:
            neighborhood_index[nb.slug] = (loc.slug, nb.slug)
            for alias in nb.aliases:
                neighborhood_index[alias] = (loc.slug, nb.slug)

    subservices_by_parent: dict[str, dict[str, str]] = {}
    for sub in config.subservices:
        bucket = subservices_by_parent.setdefault(sub.parent, {})
        bucket[sub.slug] = sub.slug
        for alias in sub.aliases:
            bucket[alias] = sub.slug

    ignore_patterns = [re.compile(p) for p in config.url_patterns_to_ignore]

    return ClassifierIndexes(
        service_index=service_index,
        location_index=location_index,
        neighborhood_index=neighborhood_index,
        subservices_by_parent=subservices_by_parent,
        ignore_patterns=ignore_patterns,
    )


def _normalize_url(url: str) -> str:
    """Strip scheme/host/www; lowercase; drop trailing slash on non-root; drop query+fragment."""
    url = url.strip()
    if not url:
        return "/"

    if "://" in url:
        parsed = urlparse(url)
        path = parsed.path or "/"
    elif url.startswith("/"):
        # Bare path: still strip query/fragment manually
        path = url
    else:
        # Host with no scheme: prepend // so urlparse picks up netloc
        parsed = urlparse("//" + url, scheme="https")
        path = parsed.path or "/"

    path = path.split("?", 1)[0].split("#", 1)[0]
    path = path.lower()
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return path or "/"


def _is_ignored(path: str, patterns: list[re.Pattern[str]]) -> bool:
    return any(p.search(path) for p in patterns)


R = TypeVar("R")


def _try_split(
    segment: str,
    left_index: dict[str, str],
    right_index: dict[str, R],
) -> tuple[str, R, float] | None:
    """Try to split a single hyphenated segment into (left, right) where left matches
    `left_index` and right matches `right_index`.

    Tries the explicit `-in-` separator first, then iterates over hyphen split points
    preferring the longest left match. Returns the canonical values from each index
    along with a confidence of 0.8 (subtoken match), or None if no split matches.
    """
    if "-in-" in segment:
        left_raw, right_raw = segment.split("-in-", 1)
        if left_raw in left_index and right_raw in right_index:
            return (left_index[left_raw], right_index[right_raw], 0.8)

    tokens = segment.split("-")
    for i in range(len(tokens) - 1, 0, -1):
        left_raw = "-".join(tokens[:i])
        right_raw = "-".join(tokens[i:])
        if left_raw in left_index and right_raw in right_index:
            return (left_index[left_raw], right_index[right_raw], 0.8)

    return None


def _classify_path(
    url: str, path: str, indexes: ClassifierIndexes
) -> PageClassification:
    """The main page-type decision tree. Operates on a normalized path."""

    if path == "/":
        return PageClassification(url=url, page_type=PageType.HOME, raw_path=path)

    segments = [s for s in path.split("/") if s]

    # ---- Fixed-name pages ----
    match segments:
        case ["about-us"]:
            return PageClassification(
                url=url, page_type=PageType.ABOUT_US, raw_path=path
            )
        case ["contact-us"]:
            return PageClassification(
                url=url, page_type=PageType.CONTACT_US, raw_path=path
            )
        case ["privacy-policy"]:
            return PageClassification(
                url=url, page_type=PageType.PRIVACY_POLICY, raw_path=path
            )
        case ["services"]:
            return PageClassification(
                url=url, page_type=PageType.SERVICES_HUB, raw_path=path
            )
        case ["areas-we-serve"]:
            return PageClassification(
                url=url, page_type=PageType.AREAS_WE_SERVE_HUB, raw_path=path
            )
        case ["blog"]:
            return PageClassification(
                url=url, page_type=PageType.BLOG_ARCHIVE, raw_path=path
            )

    if len(segments) == 2 and segments[0] == "about-us":
        return PageClassification(
            url=url,
            page_type=PageType.BIO,
            bio_name=segments[1],
            raw_path=path,
        )

    if len(segments) >= 2 and segments[0] == "blog":
        return PageClassification(
            url=url,
            page_type=PageType.BLOG_POST,
            blog_slug=segments[1],
            raw_path=path,
        )

    svc_idx = indexes.service_index
    loc_idx = indexes.location_index
    nb_idx = indexes.neighborhood_index
    sub_idx = indexes.subservices_by_parent

    # ---- 1-segment paths ----
    if len(segments) == 1:
        seg = segments[0]

        if seg in svc_idx:
            return PageClassification(
                url=url,
                page_type=PageType.TOP_LEVEL_SERVICE,
                service=svc_idx[seg],
                raw_path=path,
                confidence=1.0,
            )
        if seg in loc_idx:
            return PageClassification(
                url=url,
                page_type=PageType.TOP_LEVEL_LOCATION,
                location=loc_idx[seg],
                raw_path=path,
                confidence=1.0,
            )

        # Flat slug: service + location
        svc_loc = _try_split(seg, svc_idx, loc_idx)
        if svc_loc is not None:
            svc, loc, conf = svc_loc
            return PageClassification(
                url=url,
                page_type=PageType.LOCAL_LANDING,
                location=loc,
                service=svc,
                raw_path=path,
                confidence=conf,
            )

        # Flat slug: service + neighborhood -> LOCAL_LANDING (location inferred)
        svc_nb = _try_split(seg, svc_idx, nb_idx)
        if svc_nb is not None:
            svc, (loc, _nb), conf = svc_nb
            return PageClassification(
                url=url,
                page_type=PageType.LOCAL_LANDING,
                location=loc,
                service=svc,
                raw_path=path,
                confidence=conf,
            )

        return PageClassification(
            url=url, page_type=PageType.UNKNOWN, raw_path=path, confidence=0.0
        )

    # ---- 2-segment paths ----
    if len(segments) == 2:
        s1, s2 = segments

        # [location][neighborhood]
        if s1 in loc_idx and s2 in nb_idx and nb_idx[s2][0] == loc_idx[s1]:
            return PageClassification(
                url=url,
                page_type=PageType.NEIGHBORHOOD,
                location=loc_idx[s1],
                neighborhood=nb_idx[s2][1],
                raw_path=path,
                confidence=1.0,
            )

        # [service][subservice] - per ambiguity #5, checked before [svc][loc]
        if s1 in svc_idx:
            parent = svc_idx[s1]
            if parent in sub_idx and s2 in sub_idx[parent]:
                return PageClassification(
                    url=url,
                    page_type=PageType.SUB_SERVICE,
                    service=parent,
                    subservice=sub_idx[parent][s2],
                    raw_path=path,
                    confidence=1.0,
                )

        # [location][service]
        if s1 in loc_idx and s2 in svc_idx:
            return PageClassification(
                url=url,
                page_type=PageType.LOCAL_LANDING,
                location=loc_idx[s1],
                service=svc_idx[s2],
                raw_path=path,
                confidence=1.0,
            )

        # [service][location] (service-first nested)
        if s1 in svc_idx and s2 in loc_idx:
            return PageClassification(
                url=url,
                page_type=PageType.LOCAL_LANDING,
                location=loc_idx[s2],
                service=svc_idx[s1],
                raw_path=path,
                confidence=1.0,
            )

        # [service][neighborhood] -> NEIGHBORHOOD_SERVICE (per ambiguity #2)
        if s1 in svc_idx and s2 in nb_idx:
            loc, nb = nb_idx[s2]
            return PageClassification(
                url=url,
                page_type=PageType.NEIGHBORHOOD_SERVICE,
                location=loc,
                neighborhood=nb,
                service=svc_idx[s1],
                raw_path=path,
                confidence=0.8,
            )

        # [location] + flat service-neighborhood (Orlando/NYC inline-neighborhood pattern)
        if s1 in loc_idx:
            loc_slug = loc_idx[s1]
            local_nb_idx: dict[str, str] = {
                alias: nb_slug
                for alias, (parent_loc, nb_slug) in nb_idx.items()
                if parent_loc == loc_slug
            }
            svc_nb = _try_split(s2, svc_idx, local_nb_idx)
            if svc_nb is not None:
                svc, nb, conf = svc_nb
                return PageClassification(
                    url=url,
                    page_type=PageType.NEIGHBORHOOD_SERVICE,
                    location=loc_slug,
                    neighborhood=nb,
                    service=svc,
                    raw_path=path,
                    confidence=conf,
                )

        return PageClassification(
            url=url, page_type=PageType.UNKNOWN, raw_path=path, confidence=0.0
        )

    # ---- 3-segment paths ----
    if len(segments) == 3:
        s1, s2, s3 = segments

        # [location][service][subservice]
        if s1 in loc_idx and s2 in svc_idx:
            parent = svc_idx[s2]
            if parent in sub_idx and s3 in sub_idx[parent]:
                return PageClassification(
                    url=url,
                    page_type=PageType.SUBSERVICE_LANDING,
                    location=loc_idx[s1],
                    service=parent,
                    subservice=sub_idx[parent][s3],
                    raw_path=path,
                    confidence=1.0,
                )

        # [location][neighborhood][service]
        if (
            s1 in loc_idx
            and s2 in nb_idx
            and nb_idx[s2][0] == loc_idx[s1]
            and s3 in svc_idx
        ):
            return PageClassification(
                url=url,
                page_type=PageType.NEIGHBORHOOD_SERVICE,
                location=loc_idx[s1],
                neighborhood=nb_idx[s2][1],
                service=svc_idx[s3],
                raw_path=path,
                confidence=1.0,
            )

        return PageClassification(
            url=url, page_type=PageType.UNKNOWN, raw_path=path, confidence=0.0
        )

    return PageClassification(
        url=url, page_type=PageType.UNKNOWN, raw_path=path, confidence=0.0
    )


def classify(url: str, config: ClientConfig) -> PageClassification | None:
    """Classify a single URL. Returns None if the URL matches an ignore pattern."""
    indexes = _build_indexes(config)
    return _classify_one(url, indexes)


def _classify_one(
    url: str, indexes: ClassifierIndexes
) -> PageClassification | None:
    path = _normalize_url(url)
    if _is_ignored(path, indexes.ignore_patterns):
        return None
    return _classify_path(url, path, indexes)


def classify_all(
    urls: list[str], config: ClientConfig
) -> tuple[list[PageClassification], list[str]]:
    """Classify a batch of URLs. Returns (classifications, ignored_urls)."""
    indexes = _build_indexes(config)
    classifications: list[PageClassification] = []
    ignored: list[str] = []
    for url in urls:
        result = _classify_one(url, indexes)
        if result is None:
            ignored.append(url)
        else:
            classifications.append(result)
    return classifications, ignored


def read_urls(input_dir: Path) -> list[str]:
    """Read URLs from clients/[client]/input/urls.xlsx or urls.csv.

    Auto-detects format. Tries column names "Address" (Website Auditor default),
    then "url"/"URL", then falls back to column 0.
    """
    xlsx_path = input_dir / "urls.xlsx"
    csv_path = input_dir / "urls.csv"

    if xlsx_path.exists():
        df = pd.read_excel(xlsx_path)
    elif csv_path.exists():
        df = pd.read_csv(csv_path)
    else:
        raise FileNotFoundError(
            f"No urls.xlsx or urls.csv found in {input_dir}"
        )

    for col in ("Address", "url", "URL"):
        if col in df.columns:
            return df[col].dropna().astype(str).tolist()
    return df.iloc[:, 0].dropna().astype(str).tolist()
