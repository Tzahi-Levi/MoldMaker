"""Casting-material vs mold-material compatibility (pure)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from .presets import PresetLibrary

# Mold types where the printed part (box/shell/case) is NOT in direct contact with the casting.
# Temperature/forbidden-material problems are demoted from errors to warnings for these.
INDIRECT_TYPES = ("silicone_box", "brush_on_mother", "slip_cast_case")


@dataclass
class CompatResult:
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_text(self) -> str:
        parts = [f"ERROR: {e}" for e in self.errors]
        parts += [f"Warning: {w}" for w in self.warnings]
        parts += [f"Note: {n}" for n in self.notes]
        return "\n".join(parts) if parts else "No compatibility issues found."


def check(lib: PresetLibrary, casting_id: str, mold_type: str, mold_material_id: str) -> CompatResult:
    """Evaluate a casting material / mold type / mold material combination."""
    res = CompatResult()
    cm = lib.casting[casting_id]
    mm = lib.mold_materials[mold_material_id]
    indirect = mold_type in INDIRECT_TYPES

    def problem(msg: str) -> None:
        if indirect:
            res.warnings.append(msg + " (The printed part is not in direct contact with the casting, but check heat transfer.)")
        else:
            res.errors.append(msg)

    if mold_type not in cm.allowed_mold_types:
        res.errors.append(f"{cm.label} does not support mold type '{mold_type}'.")

    if mold_material_id in cm.forbidden_mold_materials:
        problem(f"{mm.label} must not be used with {cm.label}.")

    if cm.process_temp_C is not None and cm.process_temp_C > mm.max_service_C:
        problem(
            f"{cm.label} process temperature ({cm.process_temp_C:.0f} C) exceeds {mm.label} "
            f"max service temperature ({mm.max_service_C:.0f} C)."
        )

    if (mold_material_id not in cm.recommended_mold_materials
            and mold_material_id not in cm.forbidden_mold_materials):
        res.warnings.append(f"{mm.label} is not in the recommended list for {cm.label}.")

    if mm.estimated:
        res.notes.append(f"{mm.label} max service temperature is an engineering estimate; verify with your filament/resin datasheet.")

    res.warnings.extend(cm.warnings)

    note = cm.mold_type_notes.get(mold_type)
    if note:
        res.notes.append(note)

    if cm.confidence == "low":
        res.warnings.append(f"Defaults for {cm.label} are low-confidence; verify every value.")
    est = [k for k in cm.estimated if k in cm.defaults]
    if est:
        res.notes.append("Engineering-estimate defaults (verify): " + ", ".join(est) + ".")

    release = str(cm.defaults.get("release_note", "")).strip()
    if release:
        res.notes.append(f"Release: {release}")
    return res
