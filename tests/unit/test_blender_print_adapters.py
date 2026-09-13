import pytest

from app.blender_bridge.print_adapters import (
    OrcaMcpAdapter,
    PrintCapabilityUnavailable,
    ThreeMfMcpAdapter,
)
from app.blender_bridge.print_pipeline import ArtifactRef
from app.blender_bridge.printing import (
    FilamentContext,
    NozzleContext,
    PrintContext,
    PrinterContext,
)


class FakeCaller:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    async def call(self, tool_name, arguments):
        self.calls.append((tool_name, arguments))
        reply = self.replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        return reply


def artifact():
    return ArtifactRef("geometry_3mf", r"C:\prints\part.3mf", "model/3mf")


def context():
    return PrintContext(
        printer=PrinterContext("AD5X 0.4", "Flashforge AD5X"),
        nozzle=NozzleContext(0.4, "hardened_steel"),
        filament=FilamentContext(
            "PETG calibrated",
            "PETG",
            flow_ratio=0.97,
            pressure_advance=0.045,
            max_volumetric_speed_mm3_s=12.5,
            nozzle_temperature_c=240,
            bed_temperature_c=75,
        ),
    )


@pytest.mark.asyncio
async def test_3mf_adapter_uses_check_compliance_and_maps_clean_report_to_passed():
    caller = FakeCaller(
        [
            {
                "structuredContent": {
                    "parseable": True,
                    "validation": {
                        "compliant": True,
                        "preflightPassed": True,
                        "strict": {"valid": True, "warnings": [], "errors": []},
                        "nonStrict": {"valid": True, "warnings": [], "errors": []},
                        "findings": [],
                    },
                }
            }
        ]
    )
    result = await ThreeMfMcpAdapter(caller).validate(artifact())
    assert result.state == "passed"
    assert caller.calls == [
        ("3mf.check_compliance", {"path": r"C:\prints\part.3mf"})
    ]


@pytest.mark.asyncio
async def test_3mf_adapter_blocks_noncompliant_or_preflight_failed_package():
    caller = FakeCaller(
        [
            {
                "structuredContent": {
                    "parseable": True,
                    "validation": {
                        "compliant": False,
                        "preflightPassed": False,
                        "strict": {
                            "valid": False,
                            "warnings": [],
                            "errors": [{"message": "bad package"}],
                        },
                        "nonStrict": {"valid": True, "warnings": [], "errors": []},
                        "findings": [
                            {
                                "severity": "error",
                                "code": "non_manifold",
                                "message": "non-manifold",
                            }
                        ],
                    },
                }
            }
        ]
    )
    result = await ThreeMfMcpAdapter(caller).validate(artifact())
    assert result.state == "blocked"
    assert result.data["validation"]["preflightPassed"] is False


@pytest.mark.asyncio
async def test_3mf_adapter_fails_closed_on_malformed_provider_payload():
    result = await ThreeMfMcpAdapter(
        FakeCaller([{"structuredContent": {"parseable": True}}])
    ).validate(artifact())
    assert result.state == "failed"


@pytest.mark.asyncio
async def test_orca_context_selects_presets_verifies_nozzle_then_applies_only_verified_calibration_keys():
    caller = FakeCaller(
        [
            {"structuredContent": {"selected": "AD5X 0.4"}},
            {"structuredContent": {"selected": "PETG calibrated"}},
            {"structuredContent": {"config": {"nozzle_diameter": "0.4"}}},
            {
                "structuredContent": {
                    "applied": [
                        "filament_flow_ratio",
                        "filament_max_volumetric_speed",
                        "nozzle_temperature",
                    ],
                    "errors": {},
                }
            },
        ]
    )
    result = await OrcaMcpAdapter(caller).apply_print_context(context())
    assert result.state == "passed"
    assert caller.calls == [
        ("orca.select_preset", {"type": "printer", "name": "AD5X 0.4"}),
        (
            "orca.select_preset",
            {"type": "filament", "name": "PETG calibrated"},
        ),
        ("orca.get_config", {"keys": ["nozzle_diameter"]}),
        (
            "orca.set_config",
            {
                "changes": {
                    "filament_flow_ratio": 0.97,
                    "filament_max_volumetric_speed": 12.5,
                    "nozzle_temperature": 240,
                }
            },
        ),
    ]
    assert any("pressure_advance" in warning for warning in result.warnings)
    assert any("bed_temperature_c" in warning for warning in result.warnings)


@pytest.mark.asyncio
async def test_orca_context_blocks_nozzle_mismatch_instead_of_overriding_machine_geometry():
    caller = FakeCaller(
        [
            {"structuredContent": {"selected": "AD5X 0.4"}},
            {"structuredContent": {"selected": "PETG calibrated"}},
            {"structuredContent": {"config": {"nozzle_diameter": "0.6"}}},
        ]
    )
    result = await OrcaMcpAdapter(caller).apply_print_context(context())
    assert result.state == "blocked"
    assert "nozzle" in result.summary.lower()
    assert all(name != "orca.set_config" for name, _ in caller.calls)


@pytest.mark.asyncio
async def test_orca_physics_block_stays_blocked():
    caller = FakeCaller(
        [
            {
                "structuredContent": {
                    "verdict": "blocked",
                    "fail": [{"name": "flow", "detail": "too high"}],
                    "warn": [],
                    "pass": [],
                }
            }
        ]
    )
    result = await OrcaMcpAdapter(caller).validate_profile_physics()
    assert result.state == "blocked"


@pytest.mark.asyncio
async def test_orca_slice_and_compare_use_exact_upstream_argument_shapes():
    caller = FakeCaller(
        [
            {
                "structuredContent": {
                    "state": "done",
                    "stats": {
                        "estimated_time_seconds": 100,
                        "filament_used_g": 10,
                    },
                    "warnings": [],
                }
            },
            {
                "structuredContent": {
                    "recommended": "fast",
                    "recommended_is_dominant": False,
                    "variants": [{"name": "fine"}, {"name": "fast"}],
                }
            },
        ]
    )
    adapter = OrcaMcpAdapter(caller, slice_timeout_seconds=420)
    sliced = await adapter.slice()
    compared = await adapter.compare_variants(
        [
            {"name": "fine", "changes": {"layer_height": 0.16}},
            {"name": "fast", "changes": {"layer_height": 0.24}},
        ]
    )
    assert sliced.state == "passed"
    assert compared.state == "passed"
    assert caller.calls == [
        ("orca.slice_and_wait", {"timeout": 420}),
        (
            "orca.compare_slices",
            {
                "variants": [
                    {"name": "fine", "changes": {"layer_height": 0.16}},
                    {"name": "fast", "changes": {"layer_height": 0.24}},
                ],
                "detail": False,
                "timeout": 420,
            },
        ),
    ]
    assert compared.data["recommended"] == "fast"


@pytest.mark.asyncio
async def test_orca_save_project_is_explicitly_unavailable_not_faked():
    with pytest.raises(PrintCapabilityUnavailable, match="project 3MF"):
        await OrcaMcpAdapter(FakeCaller([])).save_project()
