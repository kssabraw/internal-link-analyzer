"""Auditor: no page should link to the same target URL more than once.

Per docs/sop.md section "Global Rules":
> Never link to the same page twice on the same page. Google generally counts
> only the first link's anchor text, so a duplicate link with different anchor
> is wasted.
"""

import pandas as pd

from engine.registry import SiteRegistry
from engine.config import ClientConfig
from engine.violations import Severity, Violation

NAME = "duplicate_links"
SEVERITY = Severity.WARNING


def run(
    registry: SiteRegistry,
    links_df: pd.DataFrame,
    config: ClientConfig,
) -> list[Violation]:
    """Check for pages that link to the same target more than once."""
    raise NotImplementedError
