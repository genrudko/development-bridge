import importlib

import pytest

from app.settings import BridgeSettings


def _providers_module():
    try:
        return importlib.import_module("app.fusion_cad.providers")
    except ModuleNotFoundError as exc:
        pytest.fail(f"provider router module is missing: {exc}")


def test_provider_router_maps_arbitrary_logical_node_to_explicit_roles():
    module = _providers_module()
    settings = BridgeSettings.model_validate({
        "fusion_cad": {
            "provider_routes": {
                "cad-a": {
                    "reference_node": "reference-a",
                    "rich_node": "rich-a",
                    "eyes_node": "eyes-a",
                }
            }
        }
    })
    router = module.FusionCadProviderRouter(settings.fusion_cad)

    route = router.route("cad-a")

    assert route.logical_node == "cad-a"
    assert route.reference_node == "reference-a"
    assert route.rich_node == "rich-a"
    assert route.eyes_node == "eyes-a"


def test_provider_router_unknown_logical_node_is_reference_only():
    module = _providers_module()
    router = module.FusionCadProviderRouter(BridgeSettings().fusion_cad)

    route = router.route("cad-unconfigured")

    assert route.logical_node == "cad-unconfigured"
    assert route.reference_node == "cad-unconfigured"
    assert route.rich_node is None
    assert route.eyes_node is None


def test_provider_router_requires_rich_role_without_fallback_substitution():
    module = _providers_module()
    router = module.FusionCadProviderRouter(BridgeSettings().fusion_cad)

    with pytest.raises(module.FusionCadProviderUnavailable) as exc_info:
        router.require("cad-unconfigured", "rich")
    assert exc_info.value.details["capability"] == "provider.rich"
    assert exc_info.value.details["node_id"] == "cad-unconfigured"


def test_provider_router_require_returns_configured_role_node():
    module = _providers_module()
    settings = BridgeSettings.model_validate({
        "fusion_cad": {
            "provider_routes": {
                "logical-z": {
                    "reference_node": "ref-z",
                    "rich_node": "rich-z",
                }
            }
        }
    })
    router = module.FusionCadProviderRouter(settings.fusion_cad)

    assert router.require("logical-z", "reference") == "ref-z"
    assert router.require("logical-z", "rich") == "rich-z"


def test_container_injects_configured_fusion_provider_router():
    from app.container import build_container

    settings = BridgeSettings.model_validate({
        "fusion_cad": {
            "provider_routes": {
                "logical-cad": {
                    "reference_node": "reference-cad",
                    "rich_node": "rich-cad",
                    "eyes_node": "eyes-cad",
                }
            }
        }
    })

    container = build_container(settings)
    assert container.fusion_cad is not None
    route = container.fusion_cad.provider_router.route("logical-cad")
    assert route.reference_node == "reference-cad"
    assert route.rich_node == "rich-cad"
    assert route.eyes_node == "eyes-cad"
