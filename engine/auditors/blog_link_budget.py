"""Auditor: blog posts must link to exactly 1 service + 2 related blog posts.

Per docs/sop.md section "Blog Post Relationships":
> Blog Post -> Related service or subservice: Link to exactly one Top-Level
> Service Page or Sub-Service Page - the service the post is promoting.
> Determine this from the post's target keyword, URL slug, and title tag.
>
> Blog Post -> Related blog posts in the same silo: Link to exactly two
> other blog posts in the same silo. Silo membership and topical adjacency
> are both determined by keyword overlap in the URL slug and title tag.
> Choose the two posts with the strongest keyword overlap to this post.

v1 scope: count-only. We have URL slugs but no title-tag data in the
Website Auditor export, so we can't verify "the right service" or "the
most topically related" blog post choice. We check the budget (exactly 1
service link, exactly 2 silo blog links) and leave target-selection
judgment to the human SEO.

Deduplication: linking the same target multiple times still counts as
one for the budget (the duplicate_links auditor surfaces the duplication
separately).
"""

from __future__ import annotations

from collections import defaultdict

import pandas as pd

from engine.classifier import PageType
from engine.config import ClientConfig
from engine.registry import SiteRegistry
from engine.violations import Severity, Violation

NAME = "blog_link_budget"
SEVERITY = Severity.WARNING

EXPECTED_SERVICE_LINKS = 1
EXPECTED_SILO_BLOG_LINKS = 2

_SERVICE_TYPES: frozenset[PageType] = frozenset(
    {PageType.TOP_LEVEL_SERVICE, PageType.SUB_SERVICE}
)


def run(
    registry: SiteRegistry,
    links_df: pd.DataFrame,
    config: ClientConfig,
) -> list[Violation]:
    """Emit violations for blog posts that don't meet the 1-service + 2-blog budget."""
    pages_by_path: dict[str, object] = {
        p.raw_path: p for p in registry.all_pages()
    }

    outgoing_by_source: dict[str, set[str]] = defaultdict(set)
    for source, target in zip(
        links_df["source_url"], links_df["target_url"], strict=True
    ):
        outgoing_by_source[source].add(target)

    violations: list[Violation] = []
    for post in registry.get_blog_posts():
        outgoing = outgoing_by_source.get(post.raw_path, set())

        service_links = 0
        silo_blog_links = 0
        for target in outgoing:
            if target == post.raw_path:
                continue  # self-link doesn't count toward the budget
            target_page = pages_by_path.get(target)
            if target_page is None:
                continue
            if target_page.page_type in _SERVICE_TYPES:
                service_links += 1
            elif target_page.page_type == PageType.BLOG_POST:
                silo_blog_links += 1

        # Service-link budget
        if service_links == 0:
            violations.append(
                Violation(
                    rule=f"{NAME}.missing_service_link",
                    severity=SEVERITY,
                    source_url=post.url,
                    page_type=post.page_type,
                    expected=(
                        f"exactly {EXPECTED_SERVICE_LINKS} service link"
                    ),
                    actual="0 service links",
                    message=(
                        "Blog post does not link to any service / sub-service "
                        "page (SOP requires exactly 1)"
                    ),
                )
            )
        elif service_links > EXPECTED_SERVICE_LINKS:
            violations.append(
                Violation(
                    rule=f"{NAME}.too_many_service_links",
                    severity=SEVERITY,
                    source_url=post.url,
                    page_type=post.page_type,
                    expected=(
                        f"exactly {EXPECTED_SERVICE_LINKS} service link"
                    ),
                    actual=f"{service_links} service links",
                    message=(
                        f"Blog post links to {service_links} service pages "
                        f"(SOP requires exactly 1)"
                    ),
                )
            )

        # Silo-blog-link budget
        if silo_blog_links < EXPECTED_SILO_BLOG_LINKS:
            violations.append(
                Violation(
                    rule=f"{NAME}.too_few_silo_blog_links",
                    severity=SEVERITY,
                    source_url=post.url,
                    page_type=post.page_type,
                    expected=(
                        f"exactly {EXPECTED_SILO_BLOG_LINKS} links to other "
                        "blog posts in the same silo"
                    ),
                    actual=f"{silo_blog_links} silo blog links",
                    message=(
                        f"Blog post links to {silo_blog_links} other blog "
                        f"posts (SOP requires exactly 2)"
                    ),
                )
            )
        elif silo_blog_links > EXPECTED_SILO_BLOG_LINKS:
            violations.append(
                Violation(
                    rule=f"{NAME}.too_many_silo_blog_links",
                    severity=SEVERITY,
                    source_url=post.url,
                    page_type=post.page_type,
                    expected=(
                        f"exactly {EXPECTED_SILO_BLOG_LINKS} links to other "
                        "blog posts in the same silo"
                    ),
                    actual=f"{silo_blog_links} silo blog links",
                    message=(
                        f"Blog post links to {silo_blog_links} other blog "
                        f"posts (SOP requires exactly 2)"
                    ),
                )
            )

    return violations
