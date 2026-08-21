from app.api.errors import BridgeError, ErrorCode

from .models import Capability, CapabilitySet


class CapabilityPolicy:
    def require(
        self,
        capabilities: CapabilitySet,
        capability: Capability,
        *,
        project_id: str,
        repository_id: str,
    ) -> None:
        if capabilities.allows(capability):
            return
        raise BridgeError(
            ErrorCode.PERMISSION_DENIED,
            "Repository capability is not enabled",
            details={
                "project_id": project_id,
                "repository_id": repository_id,
                "capability": capability.value,
            },
        )

