"""SiteRegistry: built once from classified pages, provides indexed lookups.

Parent/child relationships are resolved through classification attributes,
not URL string parsing.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from urllib.parse import urlparse

from engine.classifier import PageClassification, PageType, normalize_url
from engine.config import ClientConfig

# Page types excluded from canonical conflict detection.
# UNKNOWN pages don't have meaningful identity attributes for clustering.
_CONFLICT_EXCLUDED_TYPES: frozenset[PageType] = frozenset({PageType.UNKNOWN})


def _canonical_rank(page: PageClassification, input_order: int) -> tuple:
    """Sort key for picking the most-canonical URL within a conflict cluster.

    Lower tuples come first. Preferences, in order:

    1. URL has no query string (`?foo=bar`).
    2. URL has no fragment (`#anchor`).
    3. For TOP_LEVEL_SERVICE / SUB_SERVICE: URL path is nested under `/services/`
       (the SOP-permitted nested convention). Has no effect on other page types.
    4. URL path ends with a trailing slash (matches SOP convention which writes
       every example with `/path/`).
    5. Input order — preserves "first-encountered wins" semantics for clusters
       where no other preference distinguishes the members.
    """
    parsed = urlparse(page.url)
    has_query = bool(parsed.query)
    has_fragment = bool(parsed.fragment)
    path = parsed.path or ""

    prefers_services_nesting = page.page_type in {
        PageType.TOP_LEVEL_SERVICE,
        PageType.SUB_SERVICE,
    }
    not_services_nested = (
        1
        if prefers_services_nesting and not path.startswith("/services/")
        else 0
    )

    no_trailing_slash = 0 if (path.endswith("/") and path != "/") else 1
    # `/` is the home page; trailing-slash check is moot. Score it 0 so home
    # variants don't get penalized just because the path is short.
    if path == "/":
        no_trailing_slash = 0

    return (
        1 if has_query else 0,
        1 if has_fragment else 0,
        not_services_nested,
        no_trailing_slash,
        input_order,
    )


@dataclass(frozen=True)
class _ConflictKey:
    """Identity tuple used for canonical conflict clustering.

    Includes bio_name and blog_slug per resolved ambiguity #1 (option b),
    so BIO and BLOG_POST pages only cluster on true duplicates.
    """

    page_type: PageType
    location: str | None
    service: str | None
    subservice: str | None
    neighborhood: str | None
    bio_name: str | None
    blog_slug: str | None


class SiteRegistry:
    """Indexed view over a list of PageClassifications.

    All lookup methods are O(1) or O(n_pages_of_relevant_type). Indexes are
    built once at construction. The input list is assumed to already exclude
    URLs filtered by `url_patterns_to_ignore` (the classifier returns None
    for those, and `classify_all` separates them out).
    """

    def __init__(
        self,
        classifications: list[PageClassification],
        config: ClientConfig,
    ) -> None:
        self._pages: list[PageClassification] = list(classifications)
        self._config = config
        self._build_indexes()
        self._canonical_conflicts = self._compute_canonical_conflicts()

    # ----- index construction -----

    def _build_indexes(self) -> None:
        self._by_url: dict[str, PageClassification] = {}
        self._by_type: dict[PageType, list[PageClassification]] = defaultdict(list)
        self._top_level_services: dict[str, PageClassification] = {}
        self._top_level_locations: dict[str, PageClassification] = {}
        self._local_landings_by_service: dict[str, list[PageClassification]] = (
            defaultdict(list)
        )
        self._local_landings_by_location: dict[str, list[PageClassification]] = (
            defaultdict(list)
        )
        self._local_landing_by_loc_svc: dict[
            tuple[str, str], PageClassification
        ] = {}
        self._subservices: dict[tuple[str, str], PageClassification] = {}
        self._subservice_landings_by_loc_svc: dict[
            tuple[str, str], list[PageClassification]
        ] = defaultdict(list)
        self._neighborhoods: dict[tuple[str, str], PageClassification] = {}
        self._neighborhoods_by_location: dict[
            str, list[PageClassification]
        ] = defaultdict(list)
        self._neighborhood_services_by_loc_nb: dict[
            tuple[str, str], list[PageClassification]
        ] = defaultdict(list)

        for page in self._pages:
            if page.raw_path:
                # First-wins on URL-key collisions (preserves classify_all order)
                self._by_url.setdefault(page.raw_path, page)
            self._by_type[page.page_type].append(page)

            match page.page_type:
                case PageType.TOP_LEVEL_SERVICE:
                    if page.service is not None:
                        self._top_level_services.setdefault(page.service, page)
                case PageType.TOP_LEVEL_LOCATION:
                    if page.location is not None:
                        self._top_level_locations.setdefault(page.location, page)
                case PageType.LOCAL_LANDING:
                    if page.service is not None:
                        self._local_landings_by_service[page.service].append(page)
                    if page.location is not None:
                        self._local_landings_by_location[page.location].append(page)
                    if page.location is not None and page.service is not None:
                        self._local_landing_by_loc_svc.setdefault(
                            (page.location, page.service), page
                        )
                case PageType.SUB_SERVICE:
                    if page.service is not None and page.subservice is not None:
                        self._subservices.setdefault(
                            (page.service, page.subservice), page
                        )
                case PageType.SUBSERVICE_LANDING:
                    if page.location is not None and page.service is not None:
                        self._subservice_landings_by_loc_svc[
                            (page.location, page.service)
                        ].append(page)
                case PageType.NEIGHBORHOOD:
                    if page.location is not None and page.neighborhood is not None:
                        self._neighborhoods.setdefault(
                            (page.location, page.neighborhood), page
                        )
                        self._neighborhoods_by_location[page.location].append(page)
                case PageType.NEIGHBORHOOD_SERVICE:
                    if page.location is not None and page.neighborhood is not None:
                        self._neighborhood_services_by_loc_nb[
                            (page.location, page.neighborhood)
                        ].append(page)
                case _:
                    pass

    # ----- canonical conflicts -----

    @staticmethod
    def _conflict_key(page: PageClassification) -> _ConflictKey:
        return _ConflictKey(
            page_type=page.page_type,
            location=page.location,
            service=page.service,
            subservice=page.subservice,
            neighborhood=page.neighborhood,
            bio_name=page.bio_name,
            blog_slug=page.blog_slug,
        )

    def _compute_canonical_conflicts(self) -> list[list[PageClassification]]:
        clusters: dict[_ConflictKey, list[tuple[int, PageClassification]]] = (
            defaultdict(list)
        )
        for input_order, page in enumerate(self._pages):
            if page.page_type in _CONFLICT_EXCLUDED_TYPES:
                continue
            clusters[self._conflict_key(page)].append((input_order, page))

        # Sort each cluster so the most-canonical URL is first. Tiebreak on
        # input-order preserves "first-encountered wins" semantics where the
        # canonical preferences don't otherwise distinguish members.
        result: list[list[PageClassification]] = []
        for entries in clusters.values():
            if len(entries) < 2:
                continue
            sorted_entries = sorted(
                entries, key=lambda io_p: _canonical_rank(io_p[1], io_p[0])
            )
            result.append([p for _, p in sorted_entries])
        return result

    # ----- public API -----

    def all_pages(self) -> list[PageClassification]:
        return list(self._pages)

    def get_by_url(self, url: str) -> PageClassification | None:
        return self._by_url.get(normalize_url(url))

    def get_by_type(self, page_type: PageType) -> list[PageClassification]:
        return list(self._by_type.get(page_type, []))

    def get_top_level_service(self, service: str) -> PageClassification | None:
        return self._top_level_services.get(service)

    def get_top_level_location(self, location: str) -> PageClassification | None:
        return self._top_level_locations.get(location)

    def get_local_landing_pages_for_service(
        self, service: str
    ) -> list[PageClassification]:
        return list(self._local_landings_by_service.get(service, []))

    def get_local_landing_pages_for_location(
        self, location: str
    ) -> list[PageClassification]:
        return list(self._local_landings_by_location.get(location, []))

    def get_local_landing_page(
        self, location: str, service: str
    ) -> PageClassification | None:
        """Return the first LOCAL_LANDING for (location, service).

        If multiple URLs classify identically, returns the first one
        encountered in the input list. canonical_conflicts surfaces the
        duplication separately.
        """
        return self._local_landing_by_loc_svc.get((location, service))

    def get_subservice(
        self, service: str, subservice: str
    ) -> PageClassification | None:
        return self._subservices.get((service, subservice))

    def get_subservice_landing_pages(
        self, location: str, service: str
    ) -> list[PageClassification]:
        return list(
            self._subservice_landings_by_loc_svc.get((location, service), [])
        )

    def get_neighborhood(
        self, location: str, neighborhood: str
    ) -> PageClassification | None:
        return self._neighborhoods.get((location, neighborhood))

    def get_neighborhoods_for_location(
        self, location: str
    ) -> list[PageClassification]:
        return list(self._neighborhoods_by_location.get(location, []))

    def get_neighborhood_service_pages(
        self, location: str, neighborhood: str
    ) -> list[PageClassification]:
        return list(
            self._neighborhood_services_by_loc_nb.get((location, neighborhood), [])
        )

    def get_blog_posts(self) -> list[PageClassification]:
        return self.get_by_type(PageType.BLOG_POST)

    def get_canonical_conflicts(self) -> list[list[PageClassification]]:
        return [list(cluster) for cluster in self._canonical_conflicts]

    def get_parent(
        self, page: PageClassification
    ) -> PageClassification | None:
        """Direct parent in the SOP hierarchy.

        Returns None if the direct parent doesn't exist in the registry
        (strict semantics per resolved ambiguity #2 - missing parents are
        flagged by a dedicated auditor, not silently filled in).
        """
        match page.page_type:
            case PageType.LOCAL_LANDING:
                if page.location is None:
                    return None
                return self._top_level_locations.get(page.location)

            case PageType.SUB_SERVICE:
                if page.service is None:
                    return None
                return self._top_level_services.get(page.service)

            case PageType.SUBSERVICE_LANDING:
                if page.location is None or page.service is None:
                    return None
                return self._local_landing_by_loc_svc.get(
                    (page.location, page.service)
                )

            case PageType.NEIGHBORHOOD:
                if page.location is None:
                    return None
                return self._top_level_locations.get(page.location)

            case PageType.NEIGHBORHOOD_SERVICE:
                if page.location is None or page.neighborhood is None:
                    return None
                return self._neighborhoods.get(
                    (page.location, page.neighborhood)
                )

            case PageType.BIO:
                about_us = self._by_type.get(PageType.ABOUT_US, [])
                return about_us[0] if about_us else None

            case PageType.BLOG_POST:
                blog_archive = self._by_type.get(PageType.BLOG_ARCHIVE, [])
                return blog_archive[0] if blog_archive else None

            case _:
                return None
