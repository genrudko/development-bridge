import pytest

from app.api.errors import BridgeError, ErrorCode
from app.capabilities import Capability, CapabilityPolicy, CapabilitySet


def test_capability_set_is_explicit_and_immutable():
    capabilities = CapabilitySet.from_mapping({"read": True, "write": False})
    assert capabilities.allows(Capability.READ)
    assert not capabilities.allows(Capability.WRITE)


def test_unknown_capability_is_rejected():
    with pytest.raises(BridgeError) as raised:
        CapabilitySet.from_mapping({"unknown": True})
    assert raised.value.code is ErrorCode.INVALID_ARGUMENT


def test_policy_rejects_missing_capability():
    with pytest.raises(BridgeError) as raised:
        CapabilityPolicy().require(
            CapabilitySet.from_mapping({}),
            Capability.GIT_READ,
            project_id="project",
            repository_id="repository",
        )
    assert raised.value.code is ErrorCode.PERMISSION_DENIED

