"""Auditor: neighborhood pages must link to sibling neighborhoods and neighborhood service pages.

Per docs/sop.md section "Neighborhood Relationships":
> Neighborhood Page → Related neighborhoods: Link to every other Neighborhood
> Page that shares the same parent location. No cap.
> Neighborhood Page → Neighborhood Service Pages within this neighborhood:
> Link to every Neighborhood Service Page for this neighborhood. No cap.
"""

import pandas as pd

from engine.registry import SiteRegistry
from engine.config import ClientConfig
from engine.violations import Severity, Violation

NAME = "neighborhood_silo"
SEVERITY = Severity.WARNING


def run(
    registry: SiteRegistry,
    links_df: pd.DataFrame,
    config: ClientConfig,
) -> list[Violation]:
    """Check that neighborhood pages link to sibling neighborhoods and their service pages."""
    raise NotImplementedError
