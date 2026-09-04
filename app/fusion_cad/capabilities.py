from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.api.errors import ErrorCode
from app.fusion_cad.errors import FusionCadError
from app.fusion_cad.models import CapabilityRecord, ImmutableMapping


class FusionRuntimeIdentity(BaseModel):
    """Runtime identity and environment facts for a Fusion CAD workstation node."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    application: str = "Autodesk Fusion"
    fusion_version: str | None = None
    relay_version: str | None = None
    platform: str | None = None
    api_version: str = "fusion.cad/v1"
    implementation: str = "fusion-desktop-mcp"
    probe_details: ImmutableMapping = Field(default_factory=ImmutableMapping)


# Canonical operation to prerequisite capability mapping:
OPERATION_REQUIRED_CAPABILITIES: dict[tuple[str, str], str | None] = {
    # 1. fusion_read
    ("read", "capabilities"): None,
    ("read", "echo"): None,
    ("read", "model_snapshot"): "design.access",
    ("read", "entity"): "entity.token_resolver",
    ("read", "feature_tree"): "timeline.access",
    ("read", "sketch"): "sketch.access",
    ("read", "parameters"): "design.access",
    ("read", "visibility"): "design.access",
    ("read", "selection"): "selection.primitives",
    ("read", "query"): "design.access",

    # 2. fusion_inspect (15 operations)
    ("inspect", "describe"): "inspect.measure",
    ("inspect", "bounding_box"): "inspect.measure",
    ("inspect", "oriented_bbox"): "inspect.measure",
    ("inspect", "centroid"): "inspect.measure",
    ("inspect", "area"): "inspect.measure",
    ("inspect", "perimeter"): "inspect.measure",
    ("inspect", "volume"): "inspect.measure",
    ("inspect", "distance"): "inspect.measure",
    ("inspect", "minimum_distance"): "inspect.measure",
    ("inspect", "angle"): "inspect.measure",
    ("inspect", "parallel"): "inspect.measure",
    ("inspect", "perpendicular"): "inspect.measure",
    ("inspect", "coplanar"): "inspect.measure",
    ("inspect", "concentric"): "inspect.measure",
    ("inspect", "face_to_face_thickness"): "inspect.measure",

    # 3. fusion_view
    ("view", "camera_read"): "view.camera",
    ("view", "camera_set"): "view.camera",
    ("view", "fit"): "view.camera",
    ("view", "zoom_entity"): "view.camera",
    ("view", "orient_to_face"): "view.camera",
    ("view", "standard_view"): "view.camera",
    ("view", "screenshot"): "view.camera",
    ("view", "pick"): "view.pick",

    # 4. fusion_metadata
    ("metadata", "get"): "metadata.attributes",
    ("metadata", "query"): "metadata.attributes",
    ("metadata", "provenance"): "metadata.attributes",
    ("metadata", "set"): "metadata.attributes",
    ("metadata", "remove"): "metadata.attributes",
    ("metadata", "tag"): "metadata.attributes",
    ("metadata", "untag"): "metadata.attributes",
    ("metadata", "set_role"): "metadata.attributes",
    ("metadata", "clear_role"): "metadata.attributes",

    # 5. fusion_style
    ("style", "text_read"): "style.sketch_text",
    ("style", "text_create"): "style.sketch_text",
    ("style", "text_update"): "style.sketch_text",
    ("style", "text_delete"): "style.sketch_text",
    ("style", "text_extrude"): "style.sketch_text",
    ("style", "text_cut"): "style.sketch_text",
    ("style", "show"): "design.access",
    ("style", "hide"): "design.access",
    ("style", "show_only"): "design.access",
    ("style", "isolate"): "design.access",
    ("style", "restore"): "design.access",
    ("style", "set"): "design.access",

    # 6. fusion_validate
    ("validate", "run"): "design.access",

    # 7. fusion_transaction
    ("transaction", "begin"): "transaction.preview_replay",
    ("transaction", "stage"): "transaction.preview_replay",
    ("transaction", "status"): "transaction.preview_replay",
    ("transaction", "abort"): "transaction.preview_replay",
    ("transaction", "preview"): "transaction.preview_replay",
    ("transaction", "commit"): "transaction.preview_replay",
    ("transaction", "rollback"): "transaction.preview_replay",
}


def get_required_capability(
    group: str,
    operation: str,
    payload: Mapping[str, Any] | None = None,
) -> str | None:
    if (group, operation) in OPERATION_REQUIRED_CAPABILITIES:
        return OPERATION_REQUIRED_CAPABILITIES[(group, operation)]

    if group == "mutate":
        if operation in ("text_read", "text_create", "text_update", "text_delete", "text_extrude", "text_cut"):
            return "style.sketch_text"
        if operation in ("show", "hide", "show_only", "isolate", "restore"):
            return "design.access"
        if operation in ("get", "remove", "tag", "untag", "set_role", "clear_role", "provenance"):
            return "metadata.attributes"
        if operation == "set":
            if payload and "visible" in payload:
                return "design.access"
            return "metadata.attributes"
        if operation == "query":
            if payload and "selector" in payload:
                return "design.access"
            return "metadata.attributes"

    return None


class CapabilityMatrix:
    """Deterministic matrix of runtime capabilities and limitations."""

    def __init__(
        self,
        records: Iterable[CapabilityRecord] | Mapping[str, CapabilityRecord],
        identity: FusionRuntimeIdentity | None = None,
    ) -> None:
        if isinstance(records, Mapping):
            self._records: dict[str, CapabilityRecord] = dict(records)
        else:
            self._records = {r.name: r for r in records}
        self._identity = identity

    @property
    def identity(self) -> FusionRuntimeIdentity | None:
        return self._identity

    @property
    def records(self) -> tuple[CapabilityRecord, ...]:
        return tuple(sorted(self._records.values(), key=lambda r: r.name))

    def get(self, name: str) -> CapabilityRecord | None:
        return self._records.get(name)

    def require(self, name: str, allow_degraded: bool = False) -> CapabilityRecord:
        record = self._records.get(name)
        if record is None or record.state == "unavailable":
            details: dict[str, Any] = {"capability": name}
            if record is not None:
                details["record"] = record.model_dump(mode="json")
                if record.limitations:
                    details["limitations"] = list(record.limitations)
            raise FusionCadError(
                ErrorCode.CAPABILITY_UNAVAILABLE,
                f"Capability '{name}' is unavailable on this Fusion CAD runtime",
                retryable=False,
                details=details,
            )

        if record.state == "degraded":
            if not allow_degraded:
                details = {
                    "capability": name,
                    "record": record.model_dump(mode="json"),
                    "limitations": list(record.limitations),
                }
                lim_text = f": {', '.join(record.limitations)}" if record.limitations else ""
                raise FusionCadError(
                    ErrorCode.CAPABILITY_DEGRADED,
                    f"Capability '{name}' is degraded on this Fusion CAD runtime and requires explicit opt-in{lim_text}",
                    retryable=False,
                    details=details,
                )
            return record

        return record

    @classmethod
    def from_records(
        cls,
        records: Iterable[CapabilityRecord],
        identity: FusionRuntimeIdentity | None = None,
    ) -> CapabilityMatrix:
        return cls(records, identity=identity)

    @classmethod
    def from_probe(
        cls,
        probe_data: dict[str, Any],
        identity: FusionRuntimeIdentity | None = None,
    ) -> CapabilityMatrix:
        facts = probe_data.get("probe_facts", {}) if isinstance(probe_data.get("probe_facts"), dict) else probe_data
        fusion_version = probe_data.get("fusion_version")
        relay_version = probe_data.get("relay_version", "1.0.0")

        if identity is None:
            identity = FusionRuntimeIdentity(
                application=str(probe_data.get("application", "Autodesk Fusion")),
                fusion_version=str(fusion_version) if fusion_version is not None else None,
                relay_version=str(relay_version) if relay_version is not None else None,
                platform=str(probe_data.get("platform", "Windows")) if probe_data.get("platform") is not None else None,
                probe_details=ImmutableMapping(facts),
            )

        records: list[CapabilityRecord] = []

        # 1. entity.token_resolver
        if facts.get("has_entity_token_resolver"):
            records.append(CapabilityRecord(
                name="entity.token_resolver",
                state="supported",
                implementation="adsk.fusion.Design.findEntityByToken",
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))
        else:
            records.append(CapabilityRecord(
                name="entity.token_resolver",
                state="unavailable",
                limitations=("Native design entity-token resolver not available on this Fusion runtime",),
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))

        # 2. design.access
        if facts.get("has_design_access"):
            records.append(CapabilityRecord(
                name="design.access",
                state="supported",
                implementation="adsk.fusion.Design",
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))
        else:
            records.append(CapabilityRecord(
                name="design.access",
                state="unavailable",
                limitations=("Design product access not available",),
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))

        # 3. timeline.access
        if facts.get("has_timeline_access"):
            records.append(CapabilityRecord(
                name="timeline.access",
                state="supported",
                implementation="adsk.fusion.Timeline",
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))
        else:
            records.append(CapabilityRecord(
                name="timeline.access",
                state="unavailable",
                limitations=("Timeline access not available",),
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))

        # 4. sketch.access
        if facts.get("has_sketch_access"):
            records.append(CapabilityRecord(
                name="sketch.access",
                state="supported",
                implementation="adsk.fusion.Sketches",
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))
        else:
            records.append(CapabilityRecord(
                name="sketch.access",
                state="unavailable",
                limitations=("Sketch collection access not available",),
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))

        # 5. inspect.measure
        if facts.get("has_measure_manager"):
            records.append(CapabilityRecord(
                name="inspect.measure",
                state="supported",
                implementation="adsk.core.MeasureManager",
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))
        else:
            records.append(CapabilityRecord(
                name="inspect.measure",
                state="unavailable",
                limitations=("MeasureManager API not available",),
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))

        # 6. view.camera
        if facts.get("has_camera"):
            records.append(CapabilityRecord(
                name="view.camera",
                state="supported",
                implementation="adsk.core.Camera",
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))
        else:
            records.append(CapabilityRecord(
                name="view.camera",
                state="unavailable",
                limitations=("Camera control API not available",),
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))

        # 7. view.viewport_conversion
        if facts.get("has_viewport_conversion"):
            records.append(CapabilityRecord(
                name="view.viewport_conversion",
                state="supported",
                implementation="adsk.core.Viewport",
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))
        else:
            records.append(CapabilityRecord(
                name="view.viewport_conversion",
                state="unavailable",
                limitations=("Viewport screen/model coordinate conversion methods not available",),
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))

        # 8. view.pick
        if facts.get("has_selection_primitives"):
            records.append(CapabilityRecord(
                name="view.pick",
                state="supported",
                implementation="native-preselect",
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))
        elif facts.get("has_viewport_conversion"):
            records.append(CapabilityRecord(
                name="view.pick",
                state="degraded",
                implementation="viewport-raycast",
                limitations=("Raycast geometry intersection without native preselection",),
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))
        else:
            records.append(CapabilityRecord(
                name="view.pick",
                state="unavailable",
                limitations=("Neither selection primitives nor viewport projection methods available",),
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))

        # 9. selection.primitives
        if facts.get("has_selection_primitives"):
            records.append(CapabilityRecord(
                name="selection.primitives",
                state="supported",
                implementation="adsk.core.UserInterface.activeSelections",
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))
        else:
            records.append(CapabilityRecord(
                name="selection.primitives",
                state="unavailable",
                limitations=("Interactive selection primitives not available",),
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))

        # 10. transaction.preview_hooks
        if facts.get("has_command_preview"):
            records.append(CapabilityRecord(
                name="transaction.preview_hooks",
                state="supported",
                implementation="adsk.core.Command.executePreview",
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))
        else:
            records.append(CapabilityRecord(
                name="transaction.preview_hooks",
                state="unavailable",
                limitations=("Command execution preview hooks not available",),
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))

        # 11. transaction.preview_replay
        if facts.get("has_command_preview") and facts.get("has_undo_redo"):
            records.append(CapabilityRecord(
                name="transaction.preview_replay",
                state="supported",
                implementation="command-preview-replay",
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))
        elif facts.get("has_undo_redo"):
            records.append(CapabilityRecord(
                name="transaction.preview_replay",
                state="degraded",
                implementation="undo-redo-fallback",
                limitations=("Command preview hooks not available; rollback relies on active transaction undo",),
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))
        else:
            records.append(CapabilityRecord(
                name="transaction.preview_replay",
                state="unavailable",
                limitations=("Neither command preview nor undo/redo available for transaction replay",),
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))

        # 12. metadata.attributes
        if facts.get("has_attributes"):
            records.append(CapabilityRecord(
                name="metadata.attributes",
                state="supported",
                implementation="adsk.core.Attributes",
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))
        else:
            records.append(CapabilityRecord(
                name="metadata.attributes",
                state="unavailable",
                limitations=("Custom attributes API not available",),
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))

        # 13. style.sketch_text
        if facts.get("has_sketch_text"):
            records.append(CapabilityRecord(
                name="style.sketch_text",
                state="supported",
                implementation="adsk.fusion.SketchTexts",
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))
        else:
            records.append(CapabilityRecord(
                name="style.sketch_text",
                state="unavailable",
                limitations=("SketchText creation and extrusion not available",),
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))

        # 14. transaction.undo_redo
        if facts.get("has_undo_redo"):
            records.append(CapabilityRecord(
                name="transaction.undo_redo",
                state="supported",
                implementation="adsk.core.Application",
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))
        else:
            records.append(CapabilityRecord(
                name="transaction.undo_redo",
                state="unavailable",
                limitations=("Application text command / transaction undo not available",),
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))

        # 15. revision.mutation_indicators
        if facts.get("has_mutation_indicators"):
            records.append(CapabilityRecord(
                name="revision.mutation_indicators",
                state="supported",
                implementation="adsk.core.Document.isModified",
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))
        else:
            records.append(CapabilityRecord(
                name="revision.mutation_indicators",
                state="unavailable",
                limitations=("Document mutation modified indicator not available",),
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))

        # 16. revision.external_change_detection
        if facts.get("has_mutation_indicators") and facts.get("has_timeline_access"):
            records.append(CapabilityRecord(
                name="revision.external_change_detection",
                state="supported",
                implementation="timeline-fingerprint-guard",
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))
        elif facts.get("has_mutation_indicators"):
            records.append(CapabilityRecord(
                name="revision.external_change_detection",
                state="degraded",
                implementation="document-modified-indicator",
                limitations=("Heuristic document change detection without granular timeline markers",),
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))
        else:
            records.append(CapabilityRecord(
                name="revision.external_change_detection",
                state="unavailable",
                limitations=("No reliable mutation indicators available for external change detection",),
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))

        # 17. export.dxf
        if facts.get("has_export_manager"):
            records.append(CapabilityRecord(
                name="export.dxf",
                state="supported",
                implementation="adsk.fusion.ExportManager",
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))
        else:
            records.append(CapabilityRecord(
                name="export.dxf",
                state="unavailable",
                limitations=("DXF export options not available on this runtime",),
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))

        # 18. view.section
        if facts.get("has_section_view"):
            records.append(CapabilityRecord(
                name="view.section",
                state="supported",
                implementation="adsk.fusion.SectionAnalysis",
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))
        else:
            records.append(CapabilityRecord(
                name="view.section",
                state="unavailable",
                limitations=("Section view/analysis API not available on this runtime",),
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))

        # 19. assembly.joints
        if facts.get("has_joint_access"):
            records.append(CapabilityRecord(
                name="assembly.joints",
                state="supported",
                implementation="adsk.fusion.Joints",
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))
        else:
            records.append(CapabilityRecord(
                name="assembly.joints",
                state="unavailable",
                limitations=("Joint creation and assembly operations not available on this runtime",),
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))

        return cls(records, identity=identity)

    @classmethod
    def default_supported(
        cls,
        fusion_version: str | None = None,
        relay_version: str | None = None,
    ) -> CapabilityMatrix:
        all_facts = {
            "has_app": True,
            "has_measure_manager": True,
            "has_selection_primitives": True,
            "has_active_document": True,
            "has_mutation_indicators": True,
            "has_attributes": True,
            "has_adsk_fusion": True,
            "has_design_access": True,
            "has_timeline_access": True,
            "has_entity_token_resolver": True,
            "has_sketch_access": True,
            "has_sketch_text": True,
            "has_export_manager": True,
            "has_joint_access": True,
            "has_camera": True,
            "has_viewport_conversion": True,
            "has_command_preview": True,
            "has_undo_redo": True,
            "has_section_view": True,
        }
        return cls.from_probe(
            {
                "application": "Autodesk Fusion",
                "fusion_version": fusion_version or "2.0.18000",
                "relay_version": relay_version or "1.0.0",
                "platform": "Windows",
                "probe_facts": all_facts,
            }
        )
