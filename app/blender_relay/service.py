from __future__ import annotations

import json
import re
from collections.abc import Mapping

from app.blender_hub.catalog import is_mutating
from app.blender_relay.models import BlenderPublication, BlenderToolDescriptor, freeze_json, thaw_json
from app.settings import BlenderBridgeSettings

_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,62}\.[A-Za-z0-9][A-Za-z0-9_.-]{0,62}$")
_OWNED = {"operator.ask", "operator.notify", "hub.status"}
_ANNOTATION_HINTS = {"readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint"}
_ANNOTATION_KEYS = {"title", *_ANNOTATION_HINTS}


class BlenderRelayService:
    def __init__(self, settings: BlenderBridgeSettings, desktop_nodes) -> None:
        self.settings = settings
        self.desktop_nodes = desktop_nodes
        self._publication = BlenderPublication(0, 0, 0, ())

    def snapshot(self) -> BlenderPublication:
        return self._publication

    def accept_registration(self, node_id, session_generation, protocol_profile, tools) -> BlenderPublication:
        if node_id != self.settings.node_id:
            raise ValueError("wrong Blender node")
        if protocol_profile != "mcp-v1":
            raise ValueError("unsupported Blender protocol profile")
        if not isinstance(session_generation, int) or isinstance(session_generation, bool) or session_generation < 1:
            raise ValueError("invalid desktop session generation")
        if not isinstance(tools, list):
            raise ValueError("tools must be an array")
        try:
            freeze_json(tools)
            encoded = json.dumps(tools, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        except (TypeError, ValueError) as error:
            raise ValueError("tool evidence must be JSON") from error
        if len(encoded.encode("utf-8")) > self.settings_evidence_limit:
            raise ValueError("tool evidence exceeds configured limit")
        proposed = [self._descriptor(item) for item in tools]
        names = [item.name for item in proposed]
        if len(names) != len(set(names)):
            raise ValueError("duplicate tool name")
        ordered = tuple(sorted(proposed, key=lambda item: item.name))
        current = self._publication
        changed = self._canonical_tools(ordered) != self._canonical_tools(current.tools)
        accepted = BlenderPublication(current.publication_revision + 1, current.surface_revision + int(changed), session_generation, ordered)
        self._publication = accepted
        return accepted

    @property
    def settings_evidence_limit(self) -> int:
        return int(getattr(self.desktop_nodes, "settings", None).max_request_bytes) if getattr(self.desktop_nodes, "settings", None) is not None else 262_144

    def _descriptor(self, raw) -> BlenderToolDescriptor:
        if not isinstance(raw, dict):
            raise ValueError("tool descriptor must be an object")
        name = raw.get("name")
        if not isinstance(name, str) or len(name) > 128 or not _NAME.fullmatch(name):
            raise ValueError("tool name must be a bounded qualified name")
        namespace = name.split(".", 1)[0]
        if namespace in {"operator", "hub"} and name not in _OWNED:
            raise ValueError("synthetic namespace collision")
        title, description = raw.get("title"), raw.get("description")
        if title is not None and (not isinstance(title, str) or len(title) > 256): raise ValueError("invalid title")
        if description is not None and (not isinstance(description, str) or len(description) > 4096): raise ValueError("invalid description")
        input_schema = raw.get("inputSchema")
        output_schema = raw.get("outputSchema")
        annotations = raw.get("annotations", {})
        if not isinstance(input_schema, dict) or (output_schema is not None and not isinstance(output_schema, dict)) or not isinstance(annotations, dict):
            raise ValueError("schemas and annotations must be objects")
        if set(annotations) - _ANNOTATION_KEYS:
            raise ValueError("annotations contain unsupported aliases")
        if "title" in annotations and annotations["title"] is not None and type(annotations["title"]) is not str:
            raise ValueError("annotation title must be a string or null")
        if any(annotations[key] is not None and type(annotations[key]) is not bool for key in _ANNOTATION_HINTS if key in annotations):
            raise ValueError("annotation hints must be booleans or null")
        if "execution" in raw and not isinstance(raw["execution"], dict):
            raise ValueError("execution must be an object")
        if "_meta" in raw and not isinstance(raw["_meta"], dict):
            raise ValueError("_meta must be an object")
        if "icons" in raw and (
            not isinstance(raw["icons"], list)
            or not all(isinstance(item, dict) for item in raw["icons"])
        ):
            raise ValueError("icons must be an array of objects")
        publication = {key: raw[key] for key in ("execution", "icons", "_meta") if key in raw}
        return BlenderToolDescriptor(name, title, description, input_schema, output_schema, annotations, publication, is_mutating(annotations))

    @staticmethod
    def _canonical_tools(tools) -> str:
        values = [{"name": t.name, "title": t.title, "description": t.description, "inputSchema": thaw_json(t.input_schema), "outputSchema": thaw_json(t.output_schema), "annotations": thaw_json(t.annotations), **thaw_json(t.publication_metadata)} for t in tools]
        return json.dumps(values, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    async def invoke(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
        if not isinstance(arguments, dict) or not all(isinstance(key, str) for key in arguments):
            raise ValueError("arguments must be an object")
        publication = self._publication
        descriptor = next((item for item in publication.tools if item.name == name), None)
        if descriptor is None:
            raise ValueError("unknown Blender tool")
        try:
            frozen_arguments = freeze_json(json.loads(json.dumps(arguments, ensure_ascii=False, allow_nan=False)))
            result = await self.desktop_nodes.call(self.settings.node_id, name, thaw_json(frozen_arguments), journal={"mutation": descriptor.mutating}, expected_session_generation=publication.session_generation, timeout_seconds=self.settings.call_timeout_seconds)
        except (TypeError, ValueError):
            raise ValueError("invalid Blender relay request") from None
        except Exception:
            raise RuntimeError("Blender desktop relay unavailable") from None
        if not isinstance(result, dict):
            raise ValueError("invalid desktop MCP result")
        return result
