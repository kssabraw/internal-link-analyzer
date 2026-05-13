"""Auditor: location silo linking — location pages must link down to their local landing pages.

Per docs/sop.md section "Location Silo (Downward Links From Location Pages)":
> Top-Level Location Page → Related Local Landing Pages: Link to every Local
> Landing Page under this location. No cap.
> Local Landing Page → Subservice Landing Pages within this location/service:
> Link to every Subservice Landing Page for this location + service. No cap.
"""

import pandas as pd

from engine.registry import SiteRegistry
from engine.config import ClientConfig
from engine.violations import Severity, Violation

NAME = "location_silo"
SEVERITY = Severity.CRITICAL


def run(
    registry: SiteRegistry,
    links_df: pd.DataFrame,
    config: ClientConfig,
) -> list[Violation]:
    """Check that location pages link to all their local landing / subservice landing pages."""
    raise NotImplementedError
