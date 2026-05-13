"""Pydantic models for client config (ClientConfig and related models).

Loaded from clients/[slug]/config.yml via pyyaml and validated here.
"""

from pathlib import Path

import yaml
from pydantic import BaseModel


class ServiceConfig(BaseModel):
    slug: str
    display: str
    aliases: list[str] = []


class NeighborhoodConfig(BaseModel):
    slug: str
    display: str | None = None
    aliases: list[str] = []


class LocationConfig(BaseModel):
    slug: str
    display: str
    aliases: list[str] = []
    neighborhoods: list[NeighborhoodConfig] = []


class SubserviceConfig(BaseModel):
    parent: str
    slug: str
    display: str
    aliases: list[str] = []


class ClientConfig(BaseModel):
    client: str
    domain: str
    services: list[ServiceConfig]
    locations: list[LocationConfig]
    subservices: list[SubserviceConfig] = []
    url_patterns_to_ignore: list[str] = []


def load(config_path: Path | str) -> ClientConfig:
    """Load and validate a client config from a YAML file."""
    path = Path(config_path)
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return ClientConfig.model_validate(raw)
