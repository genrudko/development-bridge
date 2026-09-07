from __future__ import annotations

from collections.abc import Iterable, Mapping
from types import MappingProxyType
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.api.errors import ErrorCode
from app.fusion_cad.errors import FusionCadError, trusted_detail
from app.fusion_cad.models import CapabilityRecord, ImmutableMapping


class FusionRuntimeIdentity(BaseModel):
    """Runtime identity and environment facts for a Fusion CAD workstation node."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    application: str | None = None
    fusion_version: str | None = None
    relay_version: str | None = None
    platform: str | None = None
    api_version: str = "fusion.cad/v1"
    implementation: str | None = None
    local_tool: str | None = None
    probe_details: ImmutableMapping = Field(default_factory=ImmutableMapping)

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        if isinstance(data, (dict, Mapping)):
            d = dict(data)
            facts: dict[str, Any] = {}
            if "probe_facts" in d:
                raw_facts = d.pop("probe_facts")
                if isinstance(raw_facts, (dict, Mapping)):
                    facts.update(dict(raw_facts))
            if "facts" in d:
                raw_facts = d.pop("facts")
                if isinstance(raw_facts, (dict, Mapping)):
                    facts.update(dict(raw_facts))
            if "probe_details" in d:
                raw_details = d.pop("probe_details")
                if isinstance(raw_details, (dict, Mapping)):
                    facts.update(dict(raw_details))
            d["probe_details"] = ImmutableMapping(facts)
            return d
        return data


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
    """Deterministic, immutable matrix of runtime capabilities and limitations."""

    __slots__ = ("_frozen", "_identity", "_records")

    def __init__(
        self,
        records: Iterable[CapabilityRecord] | Mapping[str, CapabilityRecord],
        identity: FusionRuntimeIdentity | None = None,
    ) -> None:
        seen: set[str] = set()
        records_dict: dict[str, CapabilityRecord] = {}
        record_items = records.values() if isinstance(records, Mapping) else records
        for r in record_items:
            if r.name in seen:
                raise ValueError(f"Duplicate capability record name: '{r.name}'")
            seen.add(r.name)
            records_dict[r.name] = r

        object.__setattr__(self, "_records", MappingProxyType(records_dict))
        object.__setattr__(self, "_identity", identity)
        object.__setattr__(self, "_frozen", True)

    def __setattr__(self, name: str, value: Any) -> None:
        if getattr(self, "_frozen", False):
            raise TypeError("CapabilityMatrix is immutable and read-only")
        super().__setattr__(name, value)

    def __delattr__(self, name: str) -> None:
        raise TypeError("CapabilityMatrix is immutable and read-only")

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
            details: dict[str, Any] = {"capability": trusted_detail(name)}
            if record is not None:
                details["record"] = record.model_dump(mode="json")
                if record.limitations:
                    details["limitations"] = trusted_detail(list(record.limitations))
            raise FusionCadError(
                ErrorCode.CAPABILITY_UNAVAILABLE,
                f"Capability '{name}' is unavailable on this Fusion CAD runtime",
                retryable=False,
                details=details,
            )

        if record.state == "degraded":
            if not allow_degraded:
                details = {
                    "capability": trusted_detail(name),
                    "record": record.model_dump(mode="json"),
                    "limitations": trusted_detail(list(record.limitations)),
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

    def __contains__(self, name: object) -> bool:
        return name in self._records

    def __len__(self) -> int:
        return len(self._records)

    def __iter__(self):
        return iter(self._records)

    def __getitem__(self, name: str) -> CapabilityRecord:
        rec = self._records.get(name)
        if rec is None:
            raise KeyError(name)
        return rec

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
        facts = probe_data.get("probe_facts") or probe_data.get("probe_details") or {}
        if not isinstance(facts, dict):
            facts = {}
        fusion_version = probe_data.get("fusion_version")
        relay_version = probe_data.get("relay_version")

        probe_err = facts.get("adsk_core_probe_error") or facts.get("adsk_fusion_probe_error")
        probe_failed = bool(probe_err) or (
            not facts.get("has_app")
            and not facts.get("has_adsk_fusion")
            and not facts.get("has_design_access")
        )

        if identity is None:
            identity_data: dict[str, Any] = {
                "application": probe_data.get("application"),
                "fusion_version": str(fusion_version) if fusion_version is not None else None,
                "relay_version": str(relay_version) if relay_version is not None else None,
                "platform": str(probe_data["platform"]) if probe_data.get("platform") is not None else None,
                "api_version": str(probe_data.get("api_version", "fusion.cad/v1")),
                "implementation": str(probe_data["implementation"]) if probe_data.get("implementation") is not None else None,
                "local_tool": str(probe_data["local_tool"]) if probe_data.get("local_tool") is not None else None,
                "probe_details": facts,
            }
            identity = FusionRuntimeIdentity.model_validate(identity_data)

        records: list[CapabilityRecord] = []

        def err_limits(default_msg: str) -> tuple[str, ...]:
            limits = [default_msg]
            if facts.get("adsk_core_probe_error"):
                limits.append(f"adsk.core probe error: {facts['adsk_core_probe_error']}")
            if facts.get("adsk_fusion_probe_error"):
                limits.append(f"adsk.fusion probe error: {facts['adsk_fusion_probe_error']}")
            return tuple(limits)

        # 1. entity.token_resolver
        if not probe_failed and facts.get("has_entity_token_resolver") and facts.get("has_design_access"):
            records.append(CapabilityRecord(
                name="entity.token_resolver",
                state="supported",
                implementation="adsk.fusion.Design.findEntityByToken",
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))
        elif not probe_failed and facts.get("has_entity_token_resolver"):
            records.append(CapabilityRecord(
                name="entity.token_resolver",
                state="degraded",
                implementation="adsk.fusion.Design.findEntityByToken",
                limitations=("Native design entity-token resolver present on class but unverified without active design context",),
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))
        else:
            records.append(CapabilityRecord(
                name="entity.token_resolver",
                state="unavailable",
                limitations=err_limits("Native design entity-token resolver not available on this Fusion runtime"),
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))

        # 2. design.access
        if not probe_failed and facts.get("has_design_access"):
            records.append(CapabilityRecord(
                name="design.access",
                state="supported",
                implementation="adsk.fusion.Design",
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))
        elif not probe_failed and facts.get("has_design_class"):
            records.append(CapabilityRecord(
                name="design.access",
                state="degraded",
                implementation="adsk.fusion.Design",
                limitations=("Design product class present but active design context unavailable on active document",),
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))
        else:
            records.append(CapabilityRecord(
                name="design.access",
                state="unavailable",
                limitations=err_limits("Design product access not available on active document"),
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))

        # 3. timeline.access
        if not probe_failed and facts.get("has_timeline_access") and facts.get("has_design_access"):
            records.append(CapabilityRecord(
                name="timeline.access",
                state="supported",
                implementation="adsk.fusion.Timeline",
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))
        elif not probe_failed and facts.get("has_timeline_access"):
            records.append(CapabilityRecord(
                name="timeline.access",
                state="degraded",
                implementation="adsk.fusion.Timeline",
                limitations=("Timeline access unverified without active design context",),
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))
        else:
            records.append(CapabilityRecord(
                name="timeline.access",
                state="unavailable",
                limitations=err_limits("Timeline access not available on active design"),
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))

        # 4. sketch.access
        if not probe_failed and facts.get("has_sketch_access") and facts.get("has_design_access"):
            records.append(CapabilityRecord(
                name="sketch.access",
                state="supported",
                implementation="adsk.fusion.Sketches",
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))
        elif not probe_failed and (facts.get("has_sketch_access") or facts.get("has_sketch_class")):
            records.append(CapabilityRecord(
                name="sketch.access",
                state="degraded",
                implementation="adsk.fusion.Sketches",
                limitations=("Sketch collection access unverified without active root component context",),
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))
        else:
            records.append(CapabilityRecord(
                name="sketch.access",
                state="unavailable",
                limitations=err_limits("Sketch collection access not available on active root component"),
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))

        # 5. inspect.measure (Finding 3: do not claim contract-level supported from hasattr alone)
        if not probe_failed and facts.get("has_measure_manager"):
            records.append(CapabilityRecord(
                name="inspect.measure",
                state="degraded",
                implementation="adsk.core.MeasureManager",
                limitations=("MeasureManager object presence does not guarantee contract-level geometric measurement without active document and entity context",),
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))
        else:
            records.append(CapabilityRecord(
                name="inspect.measure",
                state="unavailable",
                limitations=err_limits("MeasureManager API not available"),
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))

        # 6. view.camera (Finding 2: property existence is insufficient; prefer degraded/unavailable)
        if not probe_failed and (facts.get("has_camera") or facts.get("has_active_camera") or facts.get("camera_runtime_verified")):
            records.append(CapabilityRecord(
                name="view.camera",
                state="degraded",
                implementation="adsk.core.Camera",
                limitations=("Camera class presence does not guarantee contract-level viewport camera control without active viewport and camera runtime context",),
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))
        else:
            records.append(CapabilityRecord(
                name="view.camera",
                state="unavailable",
                limitations=err_limits("Camera control API not available"),
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))

        # 7. view.viewport_conversion (Finding 2: method presence is insufficient; prefer degraded/unavailable)
        if not probe_failed and (facts.get("has_viewport_conversion") or facts.get("has_viewport_conversion_context") or facts.get("viewport_conversion_verified")):
            records.append(CapabilityRecord(
                name="view.viewport_conversion",
                state="degraded",
                implementation="adsk.core.Viewport",
                limitations=("Viewport screen/model coordinate conversion methods present on class but unverified without active viewport runtime context",),
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))
        else:
            records.append(CapabilityRecord(
                name="view.viewport_conversion",
                state="unavailable",
                limitations=err_limits("Viewport screen/model coordinate conversion methods not available"),
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))

        # 8. view.pick (Finding 3: load-bearing pick remains degraded/unavailable until later live feasibility proof)
        if not probe_failed and facts.get("has_selection_primitives"):
            records.append(CapabilityRecord(
                name="view.pick",
                state="degraded",
                implementation="native-preselect",
                limitations=("Visual pick requires live feasibility proof; load-bearing pick remains degraded pending live verification",),
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))
        elif not probe_failed and facts.get("has_viewport_conversion"):
            records.append(CapabilityRecord(
                name="view.pick",
                state="degraded",
                implementation="viewport-raycast",
                limitations=("Raycast geometry intersection without native preselection; load-bearing pick remains degraded pending live verification",),
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))
        else:
            records.append(CapabilityRecord(
                name="view.pick",
                state="unavailable",
                limitations=err_limits("Neither selection primitives nor viewport projection methods available"),
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))

        # 9. selection.primitives (Finding 2: activeSelections/count is insufficient; prefer degraded/unavailable)
        if not probe_failed and (facts.get("has_selection_primitives") or facts.get("has_active_selections_context") or facts.get("selection_runtime_verified")):
            records.append(CapabilityRecord(
                name="selection.primitives",
                state="degraded",
                implementation="adsk.core.UserInterface.activeSelections",
                limitations=("UserInterface activeSelections attribute present but interactive selection collection runtime behavior unverified without active selection context",),
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))
        else:
            records.append(CapabilityRecord(
                name="selection.primitives",
                state="unavailable",
                limitations=err_limits("Interactive selection primitives not available"),
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))

        # 10. transaction.preview_hooks (Finding 2: preview API presence is insufficient; prefer degraded/unavailable)
        if not probe_failed and (facts.get("has_command_preview") or facts.get("preview_hooks_verified")):
            records.append(CapabilityRecord(
                name="transaction.preview_hooks",
                state="degraded",
                implementation="adsk.core.Command.executePreview",
                limitations=("Command execution preview hooks present on classes but runtime preview execution unverified without live command lifecycle",),
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))
        else:
            records.append(CapabilityRecord(
                name="transaction.preview_hooks",
                state="unavailable",
                limitations=err_limits("Command execution preview hooks not available"),
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))

        # 11. transaction.preview_replay (Finding 3: load-bearing transaction remains degraded/unavailable until later live feasibility proof)
        if not probe_failed and facts.get("has_command_preview") and facts.get("has_undo_redo"):
            records.append(CapabilityRecord(
                name="transaction.preview_replay",
                state="degraded",
                implementation="command-preview-replay",
                limitations=("Staged transaction preview and replay semantics require live feasibility proof; load-bearing transaction remains degraded pending live verification",),
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))
        elif not probe_failed and facts.get("has_undo_redo"):
            records.append(CapabilityRecord(
                name="transaction.preview_replay",
                state="degraded",
                implementation="undo-redo-fallback",
                limitations=("Command preview hooks not available; rollback relies on active transaction undo; load-bearing transaction remains degraded pending live verification",),
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))
        else:
            records.append(CapabilityRecord(
                name="transaction.preview_replay",
                state="unavailable",
                limitations=err_limits("Neither command preview nor undo/redo available for transaction replay"),
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))

        # 12. metadata.attributes (Finding 2: collection/add/count is insufficient; prefer degraded/unavailable)
        if not probe_failed and (facts.get("has_attributes") or facts.get("has_attributes_context") or facts.get("attributes_runtime_verified")):
            records.append(CapabilityRecord(
                name="metadata.attributes",
                state="degraded",
                implementation="adsk.core.Attributes",
                limitations=("Custom attributes API present but active document attribute collection runtime access unverified",),
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))
        else:
            records.append(CapabilityRecord(
                name="metadata.attributes",
                state="unavailable",
                limitations=err_limits("Custom attributes API not available"),
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))

        # 13. style.sketch_text (Finding 3: do not claim contract-level supported from hasattr alone)
        if not probe_failed and facts.get("has_sketch_text"):
            records.append(CapabilityRecord(
                name="style.sketch_text",
                state="degraded",
                implementation="adsk.fusion.SketchTexts",
                limitations=("SketchText creation and extrusion contract semantics unverified from object existence alone; requires active sketch context and text engine validation",),
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))
        else:
            records.append(CapabilityRecord(
                name="style.sketch_text",
                state="unavailable",
                limitations=err_limits("SketchText API not available"),
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))

        # 14. transaction.undo_redo (Finding 2: undo API presence is insufficient; prefer degraded/unavailable)
        if not probe_failed and (facts.get("has_undo_redo") or facts.get("has_undo_redo_context") or facts.get("undo_redo_verified")):
            records.append(CapabilityRecord(
                name="transaction.undo_redo",
                state="degraded",
                implementation="adsk.core.Application",
                limitations=("Application executeTextCommand / Transaction presence does not guarantee contract-level undo/redo behavior without active transaction context",),
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))
        else:
            records.append(CapabilityRecord(
                name="transaction.undo_redo",
                state="unavailable",
                limitations=err_limits("Application text command / transaction undo not available"),
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))

        # 15. revision.mutation_indicators (Finding 2: require active document context)
        if not probe_failed and (facts.get("mutation_indicators_verified") or (facts.get("has_mutation_indicators") and facts.get("has_active_document"))):
            records.append(CapabilityRecord(
                name="revision.mutation_indicators",
                state="supported",
                implementation="adsk.core.Document.isModified",
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))
        elif not probe_failed and facts.get("has_mutation_indicators"):
            records.append(CapabilityRecord(
                name="revision.mutation_indicators",
                state="degraded",
                implementation="adsk.core.Document.isModified",
                limitations=("Document mutation modified indicator unverified without active document runtime context",),
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))
        else:
            records.append(CapabilityRecord(
                name="revision.mutation_indicators",
                state="unavailable",
                limitations=err_limits("Document mutation modified indicator not available"),
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))

        # 16. revision.external_change_detection (Finding 3: do not claim contract-level supported from hasattr alone)
        if not probe_failed and facts.get("has_mutation_indicators") and facts.get("has_timeline_access"):
            records.append(CapabilityRecord(
                name="revision.external_change_detection",
                state="degraded",
                implementation="timeline-fingerprint-guard",
                limitations=("Fusion-side revision freshness guard and external-change atomicity not guaranteed at contract level; unverified without active runtime atomicity proof",),
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))
        elif not probe_failed and facts.get("has_mutation_indicators"):
            records.append(CapabilityRecord(
                name="revision.external_change_detection",
                state="degraded",
                implementation="document-modified-indicator",
                limitations=("Heuristic document change detection without granular timeline markers; atomicity not guaranteed",),
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))
        else:
            records.append(CapabilityRecord(
                name="revision.external_change_detection",
                state="unavailable",
                limitations=err_limits("No reliable mutation indicators available for external change detection"),
                fusion_version=fusion_version,
                relay_version=relay_version,
            ))

        # 17. export.dxf (Finding 3: DXF is capability-gated until P2)
        records.append(CapabilityRecord(
            name="export.dxf",
            state="unavailable",
            limitations=err_limits("DXF export contract semantics not supported on this runtime; capability-gated until P2"),
            fusion_version=fusion_version,
            relay_version=relay_version,
        ))

        # 18. view.section (Finding 3: section analysis is capability-gated until P2)
        records.append(CapabilityRecord(
            name="view.section",
            state="unavailable",
            limitations=err_limits("Section view analysis contract semantics not available on this runtime; capability-gated until P2"),
            fusion_version=fusion_version,
            relay_version=relay_version,
        ))

        # 19. assembly.joints (Finding 3: assembly joints are capability-gated until P2)
        records.append(CapabilityRecord(
            name="assembly.joints",
            state="unavailable",
            limitations=err_limits("Assembly joint operations not supported on this runtime; capability-gated until P2"),
            fusion_version=fusion_version,
            relay_version=relay_version,
        ))

        return cls(records, identity=identity)