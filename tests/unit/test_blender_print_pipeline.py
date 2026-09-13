import pytest

from app.blender_bridge.print_pipeline import (
    ArtifactRef,
    PrintPipeline,
    StageResult,
)
from app.blender_bridge.printing import (
    FilamentContext,
    NozzleContext,
    PrintContext,
    PrinterContext,
)


def print_context():
    return PrintContext(
        printer=PrinterContext(preset="AD5X 0.4", model="Flashforge AD5X"),
        nozzle=NozzleContext(diameter_mm=0.4, material="hardened_steel"),
        filament=FilamentContext(
            preset="PETG calibrated",
            material="PETG",
            flow_ratio=0.97,
            pressure_advance=0.045,
            max_volumetric_speed_mm3_s=12.5,
            nozzle_temperature_c=240,
            bed_temperature_c=75,
        ),
        goal="balanced",
    )


class FakeGeometry:
    def __init__(self, events, *, preflight=None):
        self.events = events
        self.preflight_result = preflight or StageResult.passed("mesh ok")
        self.repair_calls = 0

    async def preflight(self, source):
        self.events.append("preflight")
        return self.preflight_result

    async def repair(self, source):
        self.events.append("repair")
        self.repair_calls += 1
        self.preflight_result = StageResult.passed("repaired")
        return StageResult.passed("repair complete")

    async def export_geometry_3mf(self, source):
        self.events.append("export_3mf")
        return ArtifactRef(
            kind="geometry_3mf",
            uri="artifact://geometry.3mf",
            mime_type="model/3mf",
        )


class FakeValidator:
    def __init__(self, events, result=None):
        self.events = events
        self.result = result or StageResult.passed("3mf valid")

    async def validate(self, artifact):
        self.events.append("validate_3mf")
        assert artifact.kind == "geometry_3mf"
        return self.result


class FakeSlicer:
    def __init__(self, events, *, physics=None):
        self.events = events
        self.physics = physics or StageResult.passed("physics ok")
        self.context_payload = None
        self.saved = 0

    async def import_geometry(self, artifact):
        self.events.append("orca_import")
        return StageResult.passed("imported")

    async def apply_print_context(self, context):
        self.events.append("apply_context")
        self.context_payload = context.to_provider_payload()
        return StageResult.passed("context applied")

    async def validate_profile_physics(self):
        self.events.append("physics")
        return self.physics

    async def slice(self):
        self.events.append("slice")
        return StageResult.passed(
            "sliced", data={"time_seconds": 3600, "filament_grams": 87.2}
        )

    async def compare_variants(self, variants):
        self.events.append("compare")
        return StageResult.passed("compared", data={"variants": variants})

    async def save_project(self):
        self.events.append("save_project")
        self.saved += 1
        return ArtifactRef(
            kind="print_project",
            uri="artifact://project.3mf",
            mime_type="model/3mf",
        )


@pytest.mark.asyncio
async def test_pipeline_orders_preflight_export_validation_orca_context_physics_and_slice():
    events = []
    slicer = FakeSlicer(events)
    pipeline = PrintPipeline(FakeGeometry(events), FakeValidator(events), slicer)
    context = print_context()

    result = await pipeline.prepare_and_slice({"object": "Housing"}, context)

    assert result.state == "passed"
    assert result.geometry_3mf.uri == "artifact://geometry.3mf"
    assert result.slice_result.data["filament_grams"] == 87.2
    assert slicer.context_payload == context.to_provider_payload()
    assert events == [
        "preflight",
        "export_3mf",
        "validate_3mf",
        "orca_import",
        "apply_context",
        "physics",
        "slice",
    ]
    assert slicer.saved == 0


@pytest.mark.asyncio
async def test_3mf_validation_block_stops_before_slicer_handoff():
    events = []
    pipeline = PrintPipeline(
        FakeGeometry(events),
        FakeValidator(events, StageResult.blocked("non-manifold mesh")),
        FakeSlicer(events),
    )

    result = await pipeline.prepare_and_slice({"object": "BadMesh"}, print_context())

    assert result.state == "blocked"
    assert result.blocked_stage == "validate_3mf"
    assert events == ["preflight", "export_3mf", "validate_3mf"]


@pytest.mark.asyncio
async def test_repair_is_never_implicit_and_requires_explicit_allow_repair():
    events = []
    blocked = StageResult.blocked("mesh repair required")
    geometry = FakeGeometry(events, preflight=blocked)
    pipeline = PrintPipeline(geometry, FakeValidator(events), FakeSlicer(events))

    result = await pipeline.prepare_and_slice({"object": "Mesh"}, print_context())
    assert result.state == "blocked"
    assert geometry.repair_calls == 0
    assert events == ["preflight"]

    events.clear()
    result = await pipeline.prepare_and_slice(
        {"object": "Mesh"}, print_context(), allow_repair=True
    )
    assert result.state == "passed"
    assert geometry.repair_calls == 1
    assert events[:3] == ["preflight", "repair", "preflight"]


@pytest.mark.asyncio
async def test_physics_block_prevents_slice_and_project_save():
    events = []
    slicer = FakeSlicer(
        events, physics=StageResult.blocked("volumetric flow exceeded")
    )
    pipeline = PrintPipeline(FakeGeometry(events), FakeValidator(events), slicer)

    result = await pipeline.prepare_and_slice({"object": "Part"}, print_context())

    assert result.state == "blocked"
    assert result.blocked_stage == "profile_physics"
    assert "slice" not in events
    assert "save_project" not in events


@pytest.mark.asyncio
async def test_final_project_save_is_explicit_after_success():
    events = []
    slicer = FakeSlicer(events)
    pipeline = PrintPipeline(FakeGeometry(events), FakeValidator(events), slicer)
    result = await pipeline.prepare_and_slice({"object": "Part"}, print_context())

    artifact = await pipeline.save_project(result)

    assert artifact.kind == "print_project"
    assert slicer.saved == 1
    assert events[-1] == "save_project"


@pytest.mark.asyncio
async def test_compare_variants_returns_evidence_without_selecting_winner():
    events = []
    slicer = FakeSlicer(events)
    pipeline = PrintPipeline(FakeGeometry(events), FakeValidator(events), slicer)
    result = await pipeline.prepare_and_slice({"object": "Part"}, print_context())
    variants = [
        {"name": "A", "layer_height": 0.16},
        {"name": "B", "layer_height": 0.24},
    ]

    comparison = await pipeline.compare_variants(result, variants)

    assert comparison.state == "passed"
    assert comparison.data == {"variants": variants}
    assert "winner" not in comparison.data
