from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.api.errors import ErrorCode
from app.fusion_cad.errors import FusionCadError
from app.fusion_cad.models import (
    BoundingBox,
    CreatedBySelector,
    EntitySelector,
    NamePattern,
    TagSelector,
)


class SelectorQueryResult(BaseModel):
    """Authoritative deterministic result of a multi-entity selector query."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    matched_count: int
    normalized_selector: EntitySelector
    refs: tuple[str, ...] = Field(default_factory=tuple)
    entities: tuple[Any, ...] = Field(default_factory=tuple)


class SelectorEngine:
    """Evaluates declarative semantic selectors against CAD entities with strict cardinality enforcement."""

    def normalize(
        self, selector: EntitySelector | Mapping[str, Any] | None
    ) -> EntitySelector:
        """Normalize selector input into canonical immutable EntitySelector."""
        if selector is None:
            return EntitySelector()

        if isinstance(selector, EntitySelector):
            d = selector.model_dump()
        elif isinstance(selector, Mapping):
            d = dict(selector)
        else:
            raise FusionCadError(
                ErrorCode.INVALID_ARGUMENT,
                f"Selector must be an EntitySelector or Mapping, got {type(selector).__name__}",
            )

        # 1. Normalize kind -> tuple[str, ...]
        if "kind" in d and d["kind"] is not None:
            kind_val = d["kind"]
            if isinstance(kind_val, str):
                d["kind"] = (kind_val,)
            elif isinstance(kind_val, (list, tuple, set)):
                d["kind"] = tuple(sorted(str(k) for k in kind_val))

        # 2. Normalize name -> NamePattern
        if "name" in d and d["name"] is not None:
            name_val = d["name"]
            if isinstance(name_val, str):
                if any(ch in name_val for ch in r"^$*+?{}[]\|()"):
                    d["name"] = NamePattern(regex=name_val)
                else:
                    d["name"] = NamePattern(regex=f"^{re.escape(name_val)}$")
            elif isinstance(name_val, Mapping):
                d["name"] = NamePattern(**name_val)

        # 3. Normalize component_path -> tuple[str, ...]
        if "component_path" in d and d["component_path"] is not None:
            d["component_path"] = tuple(str(x) for x in d["component_path"])

        # 4. Normalize created_by -> CreatedBySelector
        if "created_by" in d and isinstance(d["created_by"], Mapping):
            d["created_by"] = CreatedBySelector(**d["created_by"])

        # 5. Normalize tag -> TagSelector
        if "tag" in d and isinstance(d["tag"], Mapping):
            tag_d = dict(d["tag"])
            tag_d.setdefault("group", "bridge.cad/v1")
            d["tag"] = TagSelector(**tag_d)

        # 6. Normalize role -> tuple[str, ...]
        if "role" in d and d["role"] is not None:
            role_val = d["role"]
            if isinstance(role_val, str):
                d["role"] = (role_val,)
            elif isinstance(role_val, (list, tuple, set)):
                d["role"] = tuple(sorted(str(r) for r in role_val))

        # 7. Normalize bbox_region -> BoundingBox
        if "bbox_region" in d and isinstance(d["bbox_region"], Mapping):
            d["bbox_region"] = BoundingBox(**d["bbox_region"])

        return EntitySelector(**d)

    @staticmethod
    def _extract_attr(entity: Any, field: str, default: Any = None) -> Any:
        if isinstance(entity, Mapping):
            return entity.get(field, default)
        return getattr(entity, field, default)

    def matches(
        self,
        selector: EntitySelector,
        entity: Any,
        context: Mapping[str, Any] | None = None,
    ) -> bool:
        """Check if an entity matches all non-None criteria of the normalized selector."""
        # 1. kind
        if selector.kind is not None:
            ent_kind = self._extract_attr(entity, "kind")
            if ent_kind is None:
                return False
            allowed_kinds = (
                selector.kind if isinstance(selector.kind, tuple) else (selector.kind,)
            )
            if ent_kind not in allowed_kinds:
                return False

        # 2. name
        if selector.name is not None:
            ent_name = self._extract_attr(entity, "name")
            if ent_name is None:
                return False
            pattern = (
                selector.name.regex
                if isinstance(selector.name, NamePattern)
                else str(selector.name)
            )
            try:
                if not re.search(pattern, str(ent_name)):
                    return False
            except re.error:
                return False

        # 3. component_path
        if selector.component_path is not None:
            ent_path = self._extract_attr(entity, "component_path")
            if ent_path is None:
                return False
            ent_path_tuple = (
                tuple(ent_path)
                if isinstance(ent_path, (list, tuple))
                else (str(ent_path),)
            )
            # Prefix or exact match
            if len(ent_path_tuple) < len(selector.component_path):
                return False
            if (
                ent_path_tuple[: len(selector.component_path)]
                != selector.component_path
            ):
                return False

        # 4. occurrence
        if selector.occurrence is not None:
            ent_occ = self._extract_attr(entity, "occurrence")
            if ent_occ != selector.occurrence:
                return False

        # 5. feature_type
        if selector.feature_type is not None:
            ent_feat = self._extract_attr(entity, "feature_type")
            if ent_feat != selector.feature_type:
                return False

        # 6. created_by
        if selector.created_by is not None:
            ent_creator = self._extract_attr(entity, "created_by")
            if ent_creator is None:
                return False
            cr_tool = self._extract_attr(ent_creator, "tool")
            cr_op = self._extract_attr(ent_creator, "operation")
            cr_op_id = self._extract_attr(ent_creator, "operation_id")
            if cr_tool != selector.created_by.tool:
                return False
            if (
                selector.created_by.operation is not None
                and cr_op != selector.created_by.operation
            ):
                return False
            if (
                selector.created_by.operation_id is not None
                and cr_op_id != selector.created_by.operation_id
            ):
                return False

        # 7. tag
        if selector.tag is not None:
            tags = (
                self._extract_attr(entity, "tags")
                or self._extract_attr(entity, "attributes")
                or ()
            )
            found = False
            for t in tags:
                t_group = self._extract_attr(t, "group", "bridge.cad/v1")
                t_name = self._extract_attr(t, "name")
                t_val = self._extract_attr(t, "value")
                if (
                    t_group == selector.tag.group
                    and t_name == selector.tag.name
                    and (selector.tag.value is None or t_val == selector.tag.value)
                ):
                    found = True
                    break
            if not found:
                return False

        # 8. role
        if selector.role is not None:
            ent_role = self._extract_attr(entity, "role")
            if ent_role is None:
                return False
            ent_roles = (
                set(ent_role)
                if isinstance(ent_role, (list, tuple, set))
                else {ent_role}
            )
            sel_roles = (
                set(selector.role)
                if isinstance(selector.role, (list, tuple, set))
                else {selector.role}
            )
            if not ent_roles.intersection(sel_roles):
                return False

        # 9. visible
        if selector.visible is not None:
            ent_vis = self._extract_attr(entity, "visible")
            if ent_vis != selector.visible:
                return False

        # 10. appearance
        if selector.appearance is not None:
            ent_app = self._extract_attr(entity, "appearance")
            if ent_app != selector.appearance:
                return False

        # 11. bbox_region
        if selector.bbox_region is not None:
            ent_bbox = self._extract_attr(entity, "bounding_box") or self._extract_attr(
                entity, "bbox"
            )
            if ent_bbox is None:
                return False
            q = selector.bbox_region
            b = ent_bbox

            # Frame safety: never compare raw coordinates across different frames
            if b.frame != q.frame:
                transform_matrix = None
                if context and isinstance(context, Mapping):
                    transform_matrix = context.get("transform_matrix")
                    if transform_matrix is None and "transforms" in context:
                        transforms = context["transforms"]
                        if isinstance(transforms, Mapping):
                            transform_matrix = transforms.get((b.frame, q.frame))
                            if transform_matrix is None:
                                transform_matrix = transforms.get(
                                    (b.frame.space, q.frame.space)
                                )
                if transform_matrix is None:
                    ent_tf = self._extract_attr(entity, "transform_matrix") or self._extract_attr(
                        entity, "transform"
                    )
                    if isinstance(ent_tf, (list, tuple)):
                        transform_matrix = ent_tf

                if transform_matrix is None:
                    # Fail closed: never compare raw coordinates from different frames
                    return False

                try:
                    from app.fusion_cad.refs import convert_bounding_box

                    b = convert_bounding_box(b, q.frame, transform_matrix=transform_matrix)
                except (FusionCadError, ValueError, TypeError):
                    return False

            # Check bounding box overlap in identical coordinate frame
            separated = (
                b.max_point.x < q.min_point.x
                or b.min_point.x > q.max_point.x
                or b.max_point.y < q.min_point.y
                or b.min_point.y > q.max_point.y
                or b.max_point.z < q.min_point.z
                or b.min_point.z > q.max_point.z
            )
            if separated:
                return False

        # 12. logical_object
        if selector.logical_object is not None:
            ent_log = self._extract_attr(entity, "logical_object")
            if ent_log != selector.logical_object:
                return False

        # 13. transaction_id
        if selector.transaction_id is not None:
            ent_tx = self._extract_attr(entity, "transaction_id")
            if ent_tx != selector.transaction_id:
                return False

        # 14. recipe
        if selector.recipe is not None:
            ent_rec = self._extract_attr(entity, "recipe")
            if ent_rec != selector.recipe:
                return False

        return True

    def filter(
        self,
        selector: EntitySelector | Mapping[str, Any] | None,
        candidates: Iterable[Any],
        context: Mapping[str, Any] | None = None,
    ) -> list[Any]:
        """Filter candidate entities deterministically."""
        norm_sel = self.normalize(selector)
        matched = [c for c in candidates if self.matches(norm_sel, c, context=context)]

        # Deterministic sorting by ref, then name
        def sort_key(item: Any) -> tuple[str, str]:
            ref = str(self._extract_attr(item, "ref", ""))
            name = str(self._extract_attr(item, "name", ""))
            return ref, name

        matched.sort(key=sort_key)
        return matched

    def enforce_single_target(
        self,
        matches: Sequence[Any],
        selector: EntitySelector | None = None,
    ) -> Any:
        """Enforce strict single-target cardinality: 0 => SELECTOR_EMPTY, >1 => SELECTOR_AMBIGUOUS."""
        count = len(matches)
        if count == 0:
            raise FusionCadError(
                ErrorCode.SELECTOR_EMPTY,
                "Selector matched nothing where a target is required",
                details={
                    "selector": selector.model_dump(exclude_none=True)
                    if selector
                    else None,
                    "matched_count": 0,
                },
            )
        if count > 1:
            matched_refs = [str(self._extract_attr(m, "ref", "")) for m in matches]
            raise FusionCadError(
                ErrorCode.SELECTOR_AMBIGUOUS,
                f"Selector matched {count} entities where exactly one is required",
                details={
                    "selector": selector.model_dump(exclude_none=True)
                    if selector
                    else None,
                    "matched_count": count,
                    "matched_refs": matched_refs,
                },
            )
        return matches[0]

    def resolve_one(
        self,
        selector: EntitySelector | Mapping[str, Any] | None,
        candidates: Iterable[Any],
        context: Mapping[str, Any] | None = None,
    ) -> Any:
        """Resolve exactly one target entity; fails closed with SELECTOR_EMPTY or SELECTOR_AMBIGUOUS."""
        norm_sel = self.normalize(selector)
        matches = self.filter(norm_sel, candidates, context=context)
        return self.enforce_single_target(matches, selector=norm_sel)

    def query(
        self,
        selector: EntitySelector | Mapping[str, Any] | None,
        candidates: Iterable[Any],
        context: Mapping[str, Any] | None = None,
    ) -> SelectorQueryResult:
        """Execute deterministic multi-entity selector query returning matched_count and normalized selector."""
        norm_sel = self.normalize(selector)
        matches = self.filter(norm_sel, candidates, context=context)
        refs = tuple(
            str(self._extract_attr(m, "ref", ""))
            for m in matches
            if self._extract_attr(m, "ref")
        )
        return SelectorQueryResult(
            matched_count=len(matches),
            normalized_selector=norm_sel,
            refs=refs,
            entities=tuple(matches),
        )
