"""Auditor: every page must expose the required universal nav/footer links.

Per docs/sop.md section "Navigation (Applies to Every Page)":
> Every page on the site exposes the following links via the nav bar or footer:
> Home Page, About Us, Contact Us, Privacy Policy, Top Level Service Pages,
> Areas We Serve Page, Blog Archive.
"""

import pandas as pd

from engine.registry import SiteRegistry
from engine.config import ClientConfig
from engine.violations import Severity, Violation

NAME = "universal_nav"
SEVERITY = Severity.CRITICAL


def run(
    registry: SiteRegistry,
    links_df: pd.DataFrame,
    config: ClientConfig,
) -> list[Violation]:
    """Check that every page links to the required universal nav/footer targets."""
    raise NotImplementedError
