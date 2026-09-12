import pytest

from app.blender_bridge.printing import (
    FilamentContext,
    NozzleContext,
    PrintContext,
    PrinterContext,
)


def test_print_context_preserves_real_presets_and_calibration_for_orca_provider():
    context = PrintContext(
        printer=PrinterContext(preset="Flashforge AD5X 0.4", model="Flashforge AD5X"),
        nozzle=NozzleContext(diameter_mm=0.4, material="hardened_steel"),
        filament=FilamentContext(
            preset="Geeetech PETG Metal",
            material="PETG",
            flow_ratio=0.97,
            pressure_advance=0.045,
            max_volumetric_speed_mm3_s=12.5,
            nozzle_temperature_c=240,
            bed_temperature_c=75,
        ),
        goal="balanced",
    )

    payload = context.to_provider_payload()

    assert payload["printer"]["preset"] == "Flashforge AD5X 0.4"
    assert payload["nozzle"]["diameter_mm"] == 0.4
    assert payload["filament"]["flow_ratio"] == 0.97
    assert payload["filament"]["max_volumetric_speed_mm3_s"] == 12.5
    assert payload["goal"] == "balanced"


def test_print_context_rejects_non_physical_calibration_values():
    with pytest.raises(ValueError, match="diameter_mm"):
        NozzleContext(diameter_mm=0, material="brass")

    with pytest.raises(ValueError, match="max_volumetric_speed_mm3_s"):
        FilamentContext(
            preset="bad",
            material="PLA",
            max_volumetric_speed_mm3_s=0,
        )
