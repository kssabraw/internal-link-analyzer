"""Auditor: all commercial pages must be reachable from the homepage in ≤3 clicks.

Per docs/sop.md section "Click-Depth Target":
> All commercial pages — service pages, location pages, local landing pages,
> neighborhood pages, and their third-level descendants — must be reachable
> from the homepage in 3 clicks or fewer.
"""

import pandas as pd

from engine.registry import SiteRegistry
from engine.config import ClientConfig
from engine.violations import Severity, Violation

NAME = "click_depth"
SEVERITY = Severity.CRITICAL


def run(
    registry: SiteRegistry,
    links_df: pd.DataFrame,
    config: ClientConfig,
) -> list[Violation]:
    """Check that no commercial page exceeds 3 clicks from the homepage."""
    raise NotImplementedError
