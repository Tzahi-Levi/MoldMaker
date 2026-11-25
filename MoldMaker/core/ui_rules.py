"""Which dialog groups/fields apply to which mold type (pure, so it can be unit-tested)."""
from __future__ import annotations

from typing import Dict, Tuple

GROUPS = ("grp_registration", "grp_pour", "grp_clamping", "grp_shell")

_SPLIT_TYPES = ("two_part", "core_cavity", "slip_cast_case", "brush_on_mother")

# Fields of the "Shell / skin / plaster" group and the mold types that use them.
SHELL_FIELDS: Dict[str, Tuple[str, ...]] = {
    "skin": ("brush_on_mother",),
    "shell": ("brush_on_mother", "vacuum_buck"),
    "flange_w": ("brush_on_mother", "vacuum_buck"),
    "plaster_t": ("slip_cast_case",),
    "case_wall": ("slip_cast_case",),
    "well_h": ("slip_cast_case",),
    "well_d": ("slip_cast_case",),
    "vent_hole_d": ("vacuum_buck",),
    "pin_d": ("core_cavity",),
    "insert_step": ("core_cavity",),
    "gate_d": ("core_cavity",),
    "slot_depth": ("core_cavity",),
    "slot_w": ("core_cavity",),
    "silhouette_split": ("core_cavity",),
    "apply_draft": ("core_cavity",),
}


def visible_groups(mold_type: str, silicone_two_part: bool = False) -> Dict[str, bool]:
    """Visibility of the optional dialog groups."""
    shell = any(mold_type in types for types in SHELL_FIELDS.values())
    if mold_type == "silicone_box":
        split = silicone_two_part
        v = {"grp_registration": split, "grp_pour": split, "grp_clamping": False}
    elif mold_type in ("two_part", "core_cavity"):
        v = {"grp_registration": True, "grp_pour": True, "grp_clamping": True}
    elif mold_type == "brush_on_mother":
        v = {"grp_registration": True, "grp_pour": False, "grp_clamping": True}
    else:  # open_block, vacuum_buck, slip_cast_case (natches are formed by hand in the clay bed)
        v = {"grp_registration": False, "grp_pour": False, "grp_clamping": False}
    v["grp_shell"] = shell
    return v


def visible_shell_fields(mold_type: str) -> Dict[str, bool]:
    return {field: mold_type in types for field, types in SHELL_FIELDS.items()}


def parting_applies(mold_type: str, silicone_two_part: bool = False) -> bool:
    return mold_type in _SPLIT_TYPES or (mold_type == "silicone_box" and silicone_two_part)
