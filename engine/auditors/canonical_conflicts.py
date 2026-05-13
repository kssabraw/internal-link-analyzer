"""Auditor: detect URLs that resolve to identical PageClassifications (likely duplicates).

Two pages with the same (page_type, location, service, subservice, neighborhood)
tuple are a canonical conflict — they will compete for the same keyword.
"""

import pandas as pd

from engine.registry import SiteRegistry
from engine.config import ClientConfig
from engine.violations import Severity, Violation

NAME = "canonical_conflicts"
SEVERITY = Severity.CRITICAL


def run(
    registry: SiteRegistry,
    links_df: pd.DataFrame,
    config: ClientConfig,
) -> list[Violation]:
    """Check for multiple URLs that classify identically."""
    raise NotImplementedError
