"""Violation dataclass and Severity enum used across all auditors."""

from dataclasses import dataclass
from enum import StrEnum

from engine.classifier import PageType


class Severity(StrEnum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True)
class Violation:
    rule: str
    severity: Severity
    source_url: str
    page_type: PageType
    expected: str | None
    actual: str | None
    message: str
