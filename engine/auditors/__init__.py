"""Auditor registry: imports all auditors and exposes them as a list.

Each auditor module exports NAME (str), SEVERITY (Severity), and run().
"""

from engine.auditors import (
    blog_link_budget,
    canonical_conflicts,
    click_depth,
    duplicate_links,
    location_silo,
    neighborhood_silo,
    service_silo,
    universal_nav,
)

ALL_AUDITORS = [
    universal_nav,
    click_depth,
    duplicate_links,
    blog_link_budget,
    service_silo,
    location_silo,
    neighborhood_silo,
    canonical_conflicts,
]
