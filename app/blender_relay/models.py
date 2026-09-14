from __future__ import annotations

from dataclasses import dataclass
import math
from types import MappingProxyType
from typing import Mapping


JsonMapping = Mapping[str, object]


def freeze_json(value: object) -> object:
    if type(value) is dict:
        if not all(type(key) is str for key in value):
            raise ValueError("JSON object keys must be strings")
        return MappingProxyType({key: freeze_json(item) for key, item in value.items()})
    if type(value) is list:
        return tuple(freeze_json(item) for item in value)
    if value is None or type(value) in {bool, int, str}:
        return value
    if type(value) is float and math.isfinite(value):
        return value
    raise ValueError("value must have an exact JSON shape")


def thaw_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw_json(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class BlenderToolDescriptor:
    name: str
    title: str | None
    description: str | None
    input_schema: JsonMapping
    output_schema: JsonMapping | None
    annotations: JsonMapping
    publication_metadata: JsonMapping
    mutating: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "input_schema", freeze_json(dict(self.input_schema)))
        object.__setattr__(self, "output_schema", None if self.output_schema is None else freeze_json(dict(self.output_schema)))
        object.__setattr__(self, "annotations", freeze_json(dict(self.annotations)))
        object.__setattr__(self, "publication_metadata", freeze_json(dict(self.publication_metadata)))


@dataclass(frozen=True, slots=True)
class BlenderPublication:
    publication_revision: int
    surface_revision: int
    session_generation: int
    tools: tuple[BlenderToolDescriptor, ...]
