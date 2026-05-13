"""Auditor: blog posts must link to exactly 1 service page and 2 related posts.

Per docs/sop.md section "Blog Post Relationships":
> Link to exactly one Top-Level Service Page or Sub-Service Page.
> Link to exactly two other blog posts in the same silo.
"""

import pandas as pd

from engine.registry import SiteRegistry
from engine.config import ClientConfig
from engine.violations import Severity, Violation

NAME = "blog_link_budget"
SEVERITY = Severity.WARNING


def run(
    registry: SiteRegistry,
    links_df: pd.DataFrame,
    config: ClientConfig,
) -> list[Violation]:
    """Check that each blog post has exactly 1 service link and exactly 2 silo blog links."""
    raise NotImplementedError
