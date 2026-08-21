from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.capabilities import CapabilitySet


@dataclass(frozen=True, slots=True)
class Repository:
    project_id: str
    id: str
    root: Path
    capabilities: CapabilitySet


@dataclass(frozen=True, slots=True)
class Project:
    id: str
    name: str
    repositories: tuple[Repository, ...]

