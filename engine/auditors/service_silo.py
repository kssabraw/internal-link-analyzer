"""Auditor: service silo linking — service pages must link down to their local landing pages.

Per docs/sop.md section "Service Silo (Downward Links From Service Pages)":
> Top-Level Service Page → Related Local Landing Pages: Link to every Local
> Landing Page that uses this service. No cap.
> Sub-Service Page → Related Subservice Landing Pages: Link to every Subservice
> Landing Page that uses this subservice. No cap.
"""

import pandas as pd

from engine.registry import SiteRegistry
from engine.config import ClientConfig
from engine.violations import Severity, Violation

NAME = "service_silo"
SEVERITY = Severity.CRITICAL


def run(
    registry: SiteRegistry,
    links_df: pd.DataFrame,
    config: ClientConfig,
) -> list[Violation]:
    """Check that service pages link to all their local landing / subservice landing pages."""
    raise NotImplementedError
