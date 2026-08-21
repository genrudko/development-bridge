from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping

from app.api.errors import BridgeError, ErrorCode


class Capability(StrEnum):
    READ = "read"
    WRITE = "write"
    GIT_READ = "git_read"
    GIT_WRITE = "git_write"
    EXECUTE = "execute"


@dataclass(frozen=True, slots=True)
class CapabilitySet:
    enabled: frozenset[Capability]

    @classmethod
    def from_mapping(cls, configured: Mapping[str, bool]) -> CapabilitySet:
        try:
            enabled = frozenset(
                Capability(name) for name, value in configured.items() if value
            )
            for name in configured:
                Capability(name)
        except ValueError as exc:
            raise BridgeError(
                ErrorCode.INVALID_ARGUMENT,
                "Unknown repository capability",
                details={"capability": str(exc).split(":", 1)[0]},
            ) from exc
        return cls(enabled=enabled)

    def allows(self, capability: Capability) -> bool:
        return capability in self.enabled

    def as_dict(self) -> dict[str, bool]:
        return {capability.value: self.allows(capability) for capability in Capability}
