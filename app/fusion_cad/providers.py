from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.api.errors import ErrorCode
from app.fusion_cad.errors import FusionCadError, trusted_detail
from app.settings import FusionCadSettings

ProviderRole = Literal["reference", "rich", "eyes"]


@dataclass(frozen=True, slots=True)
class FusionCadProviderRoute:
    logical_node: str
    reference_node: str
    rich_node: str | None = None
    eyes_node: str | None = None


class FusionCadProviderUnavailable(FusionCadError):
    def __init__(self, logical_node: str, role: ProviderRole) -> None:
        super().__init__(
            ErrorCode.CAPABILITY_UNAVAILABLE,
            f"Fusion CAD provider role '{role}' is not configured for logical node '{logical_node}'",
            retryable=False,
            details={
                "node_id": trusted_detail(logical_node),
                "capability": trusted_detail(f"provider.{role}"),
            },
        )


class FusionCadProviderRouter:
    def __init__(self, settings: FusionCadSettings | None = None) -> None:
        self._settings = settings or FusionCadSettings()

    def route(self, logical_node: str) -> FusionCadProviderRoute:
        configured = self._settings.provider_routes.get(logical_node)
        if configured is None:
            return FusionCadProviderRoute(
                logical_node=logical_node,
                reference_node=logical_node,
            )
        return FusionCadProviderRoute(
            logical_node=logical_node,
            reference_node=configured.reference_node,
            rich_node=configured.rich_node,
            eyes_node=configured.eyes_node,
        )

    def require(self, logical_node: str, role: ProviderRole) -> str:
        route = self.route(logical_node)
        node = getattr(route, f"{role}_node")
        if node is None:
            raise FusionCadProviderUnavailable(logical_node, role)
        return node
