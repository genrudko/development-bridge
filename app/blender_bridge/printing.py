from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal


PrintGoal = Literal[
    "balanced",
    "dimensional_accuracy",
    "strength",
    "surface_quality",
    "fastest_safe",
]


@dataclass(frozen=True, slots=True)
class PrinterContext:
    preset: str
    model: str

    def __post_init__(self) -> None:
        if not self.preset.strip():
            raise ValueError("preset must not be empty")
        if not self.model.strip():
            raise ValueError("model must not be empty")


@dataclass(frozen=True, slots=True)
class NozzleContext:
    diameter_mm: float
    material: str

    def __post_init__(self) -> None:
        if self.diameter_mm <= 0:
            raise ValueError("diameter_mm must be greater than zero")
        if not self.material.strip():
            raise ValueError("material must not be empty")


@dataclass(frozen=True, slots=True)
class FilamentContext:
    preset: str
    material: str
    flow_ratio: float | None = None
    pressure_advance: float | None = None
    max_volumetric_speed_mm3_s: float | None = None
    nozzle_temperature_c: int | None = None
    bed_temperature_c: int | None = None

    def __post_init__(self) -> None:
        if not self.preset.strip():
            raise ValueError("preset must not be empty")
        if not self.material.strip():
            raise ValueError("material must not be empty")
        if self.flow_ratio is not None and self.flow_ratio <= 0:
            raise ValueError("flow_ratio must be greater than zero")
        if self.pressure_advance is not None and self.pressure_advance < 0:
            raise ValueError("pressure_advance must be zero or greater")
        if self.max_volumetric_speed_mm3_s is not None and self.max_volumetric_speed_mm3_s <= 0:
            raise ValueError("max_volumetric_speed_mm3_s must be greater than zero")


@dataclass(frozen=True, slots=True)
class PrintContext:
    printer: PrinterContext
    nozzle: NozzleContext
    filament: FilamentContext
    goal: PrintGoal = "balanced"

    def to_provider_payload(self) -> dict[str, object]:
        return {
            "printer": asdict(self.printer),
            "nozzle": asdict(self.nozzle),
            "filament": asdict(self.filament),
            "goal": self.goal,
        }
