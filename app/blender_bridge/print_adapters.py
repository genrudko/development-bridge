from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import unquote, urlparse

from .print_pipeline import ArtifactRef, StageResult
from .printing import PrintContext


class ProviderCaller(Protocol):
    async def call(self, tool_name: str, arguments: dict[str, Any]) -> Any: ...


class PrintCapabilityUnavailable(RuntimeError):
    pass


class UpstreamToolError(RuntimeError):
    pass


def _local_path(artifact: ArtifactRef) -> str:
    if artifact.kind != "geometry_3mf":
        raise ValueError("expected geometry_3mf artifact")
    uri = artifact.uri
    if uri.startswith("file://"):
        parsed = urlparse(uri)
        path = unquote(parsed.path)
        if parsed.netloc:
            path = f"//{parsed.netloc}{path}"
        if len(path) >= 3 and path[0] == "/" and path[2] == ":":
            path = path[1:]
        return path
    if "://" in uri:
        raise ValueError("print providers require a local geometry path")
    return uri


def _error_message(result: dict[str, Any]) -> str:
    content = result.get("content")
    if isinstance(content, list):
        for block in content:
            if (
                isinstance(block, dict)
                and block.get("type") == "text"
                and isinstance(block.get("text"), str)
            ):
                return block["text"]
    return "provider tool failed"


def _payload(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise UpstreamToolError("provider returned a non-object result")
    if result.get("isError") is True:
        raise UpstreamToolError(_error_message(result))
    structured = result.get("structuredContent")
    if not isinstance(structured, dict):
        structured = result.get("structured_content")
    if isinstance(structured, dict):
        payload = structured
    elif isinstance(result.get("content"), list):
        payload = None
        for block in result["content"]:
            if not isinstance(block, dict) or block.get("type") != "text":
                continue
            text = block.get("text")
            if not isinstance(text, str):
                continue
            try:
                parsed = json.loads(text)
            except ValueError:
                continue
            if isinstance(parsed, dict):
                payload = parsed
                break
        if payload is None:
            payload = result
    else:
        payload = result
    if payload.get("error") not in (None, False, "", [], {}):
        raise UpstreamToolError(str(payload.get("error")))
    return payload


async def _call(
    caller: ProviderCaller, name: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    return _payload(await caller.call(name, arguments))


def _diagnostic_messages(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    messages: list[str] = []
    for item in items:
        if isinstance(item, dict) and isinstance(item.get("message"), str):
            messages.append(item["message"])
    return messages


@dataclass(slots=True)
class ThreeMfMcpAdapter:
    caller: ProviderCaller
    namespace: str = "3mf"

    async def validate(self, artifact: ArtifactRef) -> StageResult:
        try:
            payload = await _call(
                self.caller,
                f"{self.namespace}.check_compliance",
                {"path": _local_path(artifact)},
            )
        except (ValueError, UpstreamToolError, OSError) as exc:
            return StageResult.failed(
                "3MF validation provider failed", data={"error": str(exc)}
            )
        validation = payload.get("validation")
        if payload.get("parseable") is not True or not isinstance(validation, dict):
            return StageResult.failed(
                "3MF validator returned an incomplete report", data=payload
            )
        strict = validation.get("strict")
        non_strict = validation.get("nonStrict")
        findings = validation.get("findings")
        if (
            not isinstance(strict, dict)
            or not isinstance(non_strict, dict)
            or not isinstance(findings, list)
        ):
            return StageResult.failed(
                "3MF validator returned an incomplete validation summary", data=payload
            )
        required_bools = (
            validation.get("compliant"),
            validation.get("preflightPassed"),
            strict.get("valid"),
            non_strict.get("valid"),
        )
        if not all(isinstance(value, bool) for value in required_bools):
            return StageResult.failed(
                "3MF validator returned invalid validation flags", data=payload
            )
        warnings = _diagnostic_messages(strict.get("warnings"))
        warnings += _diagnostic_messages(non_strict.get("warnings"))
        warnings += [
            item["message"]
            for item in findings
            if isinstance(item, dict)
            and item.get("severity") == "warning"
            and isinstance(item.get("message"), str)
        ]
        passed = (
            validation["compliant"]
            and validation["preflightPassed"]
            and strict["valid"]
        )
        if not passed:
            return StageResult.blocked(
                "3MF compliance or deterministic preflight failed",
                data=payload,
                warnings=tuple(warnings),
            )
        return StageResult.passed(
            "3MF compliance and preflight passed",
            data=payload,
            warnings=tuple(warnings),
        )


@dataclass(slots=True)
class OrcaMcpAdapter:
    caller: ProviderCaller
    namespace: str = "orca"
    slice_timeout_seconds: int = 300

    async def import_geometry(self, artifact: ArtifactRef) -> StageResult:
        try:
            payload = await _call(
                self.caller,
                f"{self.namespace}.load_model",
                {"path": _local_path(artifact)},
            )
        except (ValueError, UpstreamToolError, OSError) as exc:
            return StageResult.failed(
                "OrcaSlicer model import failed", data={"error": str(exc)}
            )
        return StageResult.passed("Geometry loaded into OrcaSlicer", data=payload)

    async def apply_print_context(self, context: PrintContext) -> StageResult:
        warnings: list[str] = []
        try:
            await _call(
                self.caller,
                f"{self.namespace}.select_preset",
                {"type": "printer", "name": context.printer.preset},
            )
            await _call(
                self.caller,
                f"{self.namespace}.select_preset",
                {"type": "filament", "name": context.filament.preset},
            )
            current = await _call(
                self.caller,
                f"{self.namespace}.get_config",
                {"keys": ["nozzle_diameter"]},
            )
        except UpstreamToolError as exc:
            return StageResult.blocked(
                "OrcaSlicer rejected the requested printer or filament context",
                data={"error": str(exc)},
            )
        config = current.get("config")
        if not isinstance(config, dict) or "nozzle_diameter" not in config:
            return StageResult.failed(
                "OrcaSlicer did not report nozzle_diameter", data=current
            )
        nozzle_value = config["nozzle_diameter"]
        if isinstance(nozzle_value, (list, tuple)):
            nozzle_value = nozzle_value[0] if nozzle_value else None
        try:
            actual_nozzle = float(nozzle_value)
        except (TypeError, ValueError):
            return StageResult.failed(
                "OrcaSlicer returned an invalid nozzle_diameter", data=current
            )
        if abs(actual_nozzle - context.nozzle.diameter_mm) > 1e-6:
            return StageResult.blocked(
                "OrcaSlicer nozzle diameter does not match the requested print context",
                data={
                    "expected_nozzle_mm": context.nozzle.diameter_mm,
                    "actual_nozzle_mm": actual_nozzle,
                },
            )

        changes: dict[str, Any] = {}
        filament = context.filament
        if filament.flow_ratio is not None:
            changes["filament_flow_ratio"] = filament.flow_ratio
        if filament.max_volumetric_speed_mm3_s is not None:
            changes["filament_max_volumetric_speed"] = (
                filament.max_volumetric_speed_mm3_s
            )
        if filament.nozzle_temperature_c is not None:
            changes["nozzle_temperature"] = filament.nozzle_temperature_c
        if filament.pressure_advance is not None:
            warnings.append(
                "pressure_advance retained as context only; no universal Orca profile mapping was applied"
            )
        if filament.bed_temperature_c is not None:
            warnings.append(
                "bed_temperature_c retained as context only; bed surface is required before choosing an Orca plate-temperature key"
            )
        warnings.append(
            f"nozzle material {context.nozzle.material!r} is evidence only; Orca nozzle_diameter was verified but material was not rewritten"
        )
        if changes:
            try:
                applied = await _call(
                    self.caller,
                    f"{self.namespace}.set_config",
                    {"changes": changes},
                )
            except UpstreamToolError as exc:
                return StageResult.blocked(
                    "OrcaSlicer rejected calibrated context overrides",
                    data={"error": str(exc), "changes": changes},
                    warnings=tuple(warnings),
                )
            errors = applied.get("errors")
            if errors not in (None, {}, []):
                return StageResult.blocked(
                    "OrcaSlicer rejected one or more calibrated context overrides",
                    data=applied,
                    warnings=tuple(warnings),
                )
        return StageResult.passed(
            "OrcaSlicer printer, filament, and verified calibration context applied",
            data={"applied_overrides": changes},
            warnings=tuple(warnings),
        )

    async def validate_profile_physics(self) -> StageResult:
        try:
            payload = await _call(
                self.caller,
                f"{self.namespace}.check_profile_physics",
                {},
            )
        except UpstreamToolError as exc:
            return StageResult.failed(
                "OrcaSlicer physics gate failed", data={"error": str(exc)}
            )
        verdict = payload.get("verdict")
        warnings = tuple(
            item.get("detail", "")
            for item in payload.get("warn", [])
            if isinstance(item, dict) and item.get("detail")
        )
        if verdict == "blocked":
            return StageResult.blocked(
                "OrcaSlicer physics gate blocked the profile",
                data=payload,
                warnings=warnings,
            )
        if verdict == "warnings":
            return StageResult.passed(
                "OrcaSlicer physics gate passed with warnings",
                data=payload,
                warnings=warnings,
            )
        if verdict == "ok":
            return StageResult.passed("OrcaSlicer physics gate passed", data=payload)
        return StageResult.failed(
            "OrcaSlicer physics gate returned an unknown verdict", data=payload
        )

    async def slice(self) -> StageResult:
        try:
            payload = await _call(
                self.caller,
                f"{self.namespace}.slice_and_wait",
                {"timeout": self.slice_timeout_seconds},
            )
        except UpstreamToolError as exc:
            return StageResult.failed(
                "OrcaSlicer slice failed", data={"error": str(exc)}
            )
        warnings = tuple(str(value) for value in payload.get("warnings", []) if value)
        if payload.get("state") != "done":
            return StageResult.failed(
                "OrcaSlicer did not produce a completed slice",
                data=payload,
                warnings=warnings,
            )
        return StageResult.passed(
            "OrcaSlicer slice completed", data=payload, warnings=warnings
        )

    async def compare_variants(
        self, variants: list[dict[str, Any]]
    ) -> StageResult:
        if not 2 <= len(variants) <= 8:
            raise ValueError("OrcaSlicer comparison requires 2 to 8 variants")
        normalized: list[dict[str, Any]] = []
        names: set[str] = set()
        for variant in variants:
            if not isinstance(variant, dict):
                raise ValueError("each print variant must be an object")
            name = variant.get("name")
            changes = variant.get("changes")
            if not isinstance(name, str) or not name.strip() or name in names:
                raise ValueError("print variant names must be non-empty and unique")
            if not isinstance(changes, dict):
                raise ValueError("each print variant requires a changes object")
            names.add(name)
            normalized.append({"name": name, "changes": dict(changes)})
        try:
            payload = await _call(
                self.caller,
                f"{self.namespace}.compare_slices",
                {
                    "variants": normalized,
                    "detail": False,
                    "timeout": self.slice_timeout_seconds,
                },
            )
        except UpstreamToolError as exc:
            return StageResult.failed(
                "OrcaSlicer slice comparison failed", data={"error": str(exc)}
            )
        return StageResult.passed(
            "OrcaSlicer slice variants compared", data=payload
        )

    async def save_project(self) -> ArtifactRef:
        raise PrintCapabilityUnavailable(
            "OrcaSlicer MCP does not expose project 3MF save/export; the fork has an internal export_3mf path but no remote/MCP tool for it"
        )
