from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from .printing import PrintContext


StageState = Literal["passed", "blocked", "failed"]
ArtifactKind = Literal["geometry_3mf", "print_project", "gcode"]


@dataclass(frozen=True, slots=True)
class StageResult:
    state: StageState
    summary: str
    data: dict[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()

    @classmethod
    def passed(
        cls,
        summary: str,
        *,
        data: dict[str, Any] | None = None,
        warnings: tuple[str, ...] = (),
    ) -> "StageResult":
        return cls("passed", summary, dict(data or {}), warnings)

    @classmethod
    def blocked(
        cls,
        summary: str,
        *,
        data: dict[str, Any] | None = None,
        warnings: tuple[str, ...] = (),
    ) -> "StageResult":
        return cls("blocked", summary, dict(data or {}), warnings)

    @classmethod
    def failed(
        cls,
        summary: str,
        *,
        data: dict[str, Any] | None = None,
        warnings: tuple[str, ...] = (),
    ) -> "StageResult":
        return cls("failed", summary, dict(data or {}), warnings)


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    kind: ArtifactKind
    uri: str
    mime_type: str

    def __post_init__(self) -> None:
        if not self.uri:
            raise ValueError("artifact uri must not be empty")
        if not self.mime_type:
            raise ValueError("artifact mime_type must not be empty")


@dataclass(frozen=True, slots=True)
class PrintPipelineResult:
    state: StageState
    stages: dict[str, StageResult]
    geometry_3mf: ArtifactRef | None = None
    slice_result: StageResult | None = None
    blocked_stage: str | None = None


class GeometryPrintAdapter(Protocol):
    async def preflight(self, source: dict[str, Any]) -> StageResult: ...
    async def repair(self, source: dict[str, Any]) -> StageResult: ...
    async def export_geometry_3mf(self, source: dict[str, Any]) -> ArtifactRef: ...


class ThreeMfValidationAdapter(Protocol):
    async def validate(self, artifact: ArtifactRef) -> StageResult: ...


class SlicerAdapter(Protocol):
    async def import_geometry(self, artifact: ArtifactRef) -> StageResult: ...
    async def apply_print_context(self, context: PrintContext) -> StageResult: ...
    async def validate_profile_physics(self) -> StageResult: ...
    async def slice(self) -> StageResult: ...
    async def compare_variants(self, variants: list[dict[str, Any]]) -> StageResult: ...
    async def save_project(self) -> ArtifactRef: ...


class PrintPipeline:
    def __init__(
        self,
        geometry: GeometryPrintAdapter,
        validator: ThreeMfValidationAdapter,
        slicer: SlicerAdapter,
    ) -> None:
        self.geometry = geometry
        self.validator = validator
        self.slicer = slicer

    @staticmethod
    def _stopped(
        *,
        stage_name: str,
        stage: StageResult,
        stages: dict[str, StageResult],
        geometry_3mf: ArtifactRef | None = None,
    ) -> PrintPipelineResult:
        return PrintPipelineResult(
            state=stage.state,
            stages=dict(stages),
            geometry_3mf=geometry_3mf,
            blocked_stage=stage_name,
        )

    async def prepare_and_slice(
        self,
        source: dict[str, Any],
        context: PrintContext,
        *,
        allow_repair: bool = False,
    ) -> PrintPipelineResult:
        stages: dict[str, StageResult] = {}

        preflight = await self.geometry.preflight(source)
        stages["preflight"] = preflight
        if preflight.state != "passed":
            if preflight.state != "blocked" or not allow_repair:
                return self._stopped(
                    stage_name="preflight", stage=preflight, stages=stages
                )
            repair = await self.geometry.repair(source)
            stages["repair"] = repair
            if repair.state != "passed":
                return self._stopped(
                    stage_name="repair", stage=repair, stages=stages
                )
            preflight = await self.geometry.preflight(source)
            stages["preflight_after_repair"] = preflight
            if preflight.state != "passed":
                return self._stopped(
                    stage_name="preflight", stage=preflight, stages=stages
                )

        geometry_3mf = await self.geometry.export_geometry_3mf(source)
        if geometry_3mf.kind != "geometry_3mf":
            raise ValueError("geometry adapter must return a geometry_3mf artifact")

        validation = await self.validator.validate(geometry_3mf)
        stages["validate_3mf"] = validation
        if validation.state != "passed":
            return self._stopped(
                stage_name="validate_3mf",
                stage=validation,
                stages=stages,
                geometry_3mf=geometry_3mf,
            )

        imported = await self.slicer.import_geometry(geometry_3mf)
        stages["orca_import"] = imported
        if imported.state != "passed":
            return self._stopped(
                stage_name="orca_import",
                stage=imported,
                stages=stages,
                geometry_3mf=geometry_3mf,
            )

        applied = await self.slicer.apply_print_context(context)
        stages["apply_context"] = applied
        if applied.state != "passed":
            return self._stopped(
                stage_name="apply_context",
                stage=applied,
                stages=stages,
                geometry_3mf=geometry_3mf,
            )

        physics = await self.slicer.validate_profile_physics()
        stages["profile_physics"] = physics
        if physics.state != "passed":
            return self._stopped(
                stage_name="profile_physics",
                stage=physics,
                stages=stages,
                geometry_3mf=geometry_3mf,
            )

        sliced = await self.slicer.slice()
        stages["slice"] = sliced
        if sliced.state != "passed":
            return self._stopped(
                stage_name="slice",
                stage=sliced,
                stages=stages,
                geometry_3mf=geometry_3mf,
            )

        return PrintPipelineResult(
            state="passed",
            stages=stages,
            geometry_3mf=geometry_3mf,
            slice_result=sliced,
        )

    async def compare_variants(
        self,
        result: PrintPipelineResult,
        variants: list[dict[str, Any]],
    ) -> StageResult:
        if result.state != "passed":
            raise ValueError("variants can only be compared after a successful slice")
        if not variants:
            raise ValueError("at least one print variant is required")
        return await self.slicer.compare_variants(variants)

    async def save_project(self, result: PrintPipelineResult) -> ArtifactRef:
        if result.state != "passed":
            raise ValueError("project can only be saved after a successful pipeline")
        artifact = await self.slicer.save_project()
        if artifact.kind != "print_project":
            raise ValueError("slicer must return a print_project artifact")
        return artifact
