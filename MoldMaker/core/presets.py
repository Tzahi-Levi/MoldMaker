"""Load and validate presets/materials.json (pure, stdlib only)."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from . import model


class PresetError(ValueError):
    """Raised when the presets file is missing, unreadable, or fails schema validation."""

    def __init__(self, problems: List[str]):
        self.problems = list(problems)
        super().__init__("Invalid presets:\n  - " + "\n  - ".join(self.problems))


# Required keys in each material's (merged) `defaults` and their validators.
_NUMERIC_DEFAULTS = (
    "wall_mm", "draft_deg", "shrink_pct", "key_d_mm", "key_clearance_mm",
    "sprue_d_mm", "funnel_d_mm", "vent_d_mm",
)
_REQUIRED_DEFAULTS = _NUMERIC_DEFAULTS + ("key_type", "bolt_size", "release_note")
# Optional keys whose type we also check when present.
_OPTIONAL_NUMERIC = (
    "wall_min_mm", "wall_printed_mm", "key_chamfer_mm", "silicone_density_g_cc", "min_section_mm",
    "vent_depth_mm", "machining_stock_mm", "shell_mm", "shell_min_mm", "plaster_thickness_mm",
    "case_wall_mm", "slip_well_height_mm", "plaster_slurry_density_g_cc", "draft_min_deg",
    "draft_male_deg", "draft_female_deg", "vent_hole_d_mm", "bolt_count", "skin_mm", "flange_w_mm", "slip_well_d_mm",
)


@dataclass(frozen=True)
class MoldMaterial:
    id: str
    label: str
    max_service_C: float
    estimated: bool = False


@dataclass(frozen=True)
class CastingMaterial:
    id: str
    label: str
    allowed_mold_types: Tuple[str, ...]
    default_mold_type: str
    recommended_mold_materials: Tuple[str, ...]
    forbidden_mold_materials: Tuple[str, ...]
    defaults: Dict[str, Any]
    warnings: Tuple[str, ...] = ()
    process_temp_C: Optional[float] = None
    estimated: Tuple[str, ...] = ()
    confidence: str = "normal"
    mold_type_notes: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class PresetLibrary:
    casting: Dict[str, CastingMaterial]
    mold_materials: Dict[str, MoldMaterial]

    def casting_list(self) -> List[CastingMaterial]:
        return list(self.casting.values())

    def defaults_for(self, casting_id: str, mold_type: str) -> Dict[str, Any]:
        """Defaults for a casting material, with printed-shell wall applied when relevant."""
        d = dict(self.casting[casting_id].defaults)
        if mold_type in model.PRINTED_SHELL_TYPES and "wall_printed_mm" in d:
            d["wall_mm"] = d["wall_printed_mm"]
        return d

    def mold_material_choices(self, casting_id: str) -> List[MoldMaterial]:
        """All mold materials, recommended ones first (forbidden ones stay listed; compat reports the error)."""
        cm = self.casting[casting_id]
        rec = [self.mold_materials[i] for i in cm.recommended_mold_materials]
        rest = [m for m in self.mold_materials.values() if m.id not in cm.recommended_mold_materials]
        return rec + rest


def default_path() -> str:
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "presets", "materials.json")


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def validate_presets(raw: Any) -> List[str]:
    """Return a list of schema problems (empty if valid)."""
    problems: List[str] = []
    if not isinstance(raw, dict):
        return ["Top level must be a JSON object."]
    for key in ("base_defaults", "mold_materials", "casting_materials"):
        if key not in raw:
            problems.append(f"Missing top-level key '{key}'.")
    if problems:
        return problems

    base = raw["base_defaults"]
    if not isinstance(base, dict):
        return ["'base_defaults' must be an object."]

    mold_ids: List[str] = []
    for i, m in enumerate(raw["mold_materials"]):
        where = f"mold_materials[{i}]"
        if not isinstance(m, dict) or not isinstance(m.get("id"), str) or not m.get("id"):
            problems.append(f"{where}: needs a string 'id'.")
            continue
        if m["id"] in mold_ids:
            problems.append(f"{where}: duplicate id '{m['id']}'.")
        mold_ids.append(m["id"])
        if not isinstance(m.get("label"), str):
            problems.append(f"{where} ({m['id']}): 'label' must be a string.")
        if not _is_num(m.get("max_service_C")):
            problems.append(f"{where} ({m['id']}): 'max_service_C' must be a number.")

    seen: List[str] = []
    for i, c in enumerate(raw["casting_materials"]):
        cid = c.get("id") if isinstance(c, dict) else None
        where = f"casting_materials[{i}]" + (f" ({cid})" if cid else "")
        if not isinstance(c, dict) or not isinstance(cid, str) or not cid:
            problems.append(f"{where}: needs a string 'id'.")
            continue
        if cid in seen:
            problems.append(f"{where}: duplicate id.")
        seen.append(cid)
        if not isinstance(c.get("label"), str):
            problems.append(f"{where}: 'label' must be a string.")

        allowed = c.get("allowed_mold_types")
        if not isinstance(allowed, list) or not allowed:
            problems.append(f"{where}: 'allowed_mold_types' must be a non-empty list.")
            allowed = []
        for t in allowed:
            if t not in model.MOLD_TYPES:
                problems.append(f"{where}: unknown mold type '{t}'.")
        if c.get("default_mold_type") not in allowed:
            problems.append(f"{where}: 'default_mold_type' must be one of allowed_mold_types.")

        rec, forb = c.get("recommended_mold_materials"), c.get("forbidden_mold_materials")
        for name, lst in (("recommended_mold_materials", rec), ("forbidden_mold_materials", forb)):
            if not isinstance(lst, list):
                problems.append(f"{where}: '{name}' must be a list.")
                continue
            for mid in lst:
                if mid not in mold_ids:
                    problems.append(f"{where}: '{name}' references unknown mold material '{mid}'.")
        if isinstance(rec, list) and isinstance(forb, list) and set(rec) & set(forb):
            problems.append(f"{where}: material both recommended and forbidden: {sorted(set(rec) & set(forb))}.")

        if not isinstance(c.get("warnings", []), list) or not all(isinstance(w, str) for w in c.get("warnings", [])):
            problems.append(f"{where}: 'warnings' must be a list of strings.")
        pt = c.get("process_temp_C")
        if pt is not None and not _is_num(pt):
            problems.append(f"{where}: 'process_temp_C' must be a number.")

        merged = dict(base)
        defaults = c.get("defaults")
        if not isinstance(defaults, dict):
            problems.append(f"{where}: 'defaults' must be an object.")
        else:
            merged.update(defaults)
        for k in _REQUIRED_DEFAULTS:
            if k not in merged:
                problems.append(f"{where}: defaults missing '{k}'.")
        for k in _NUMERIC_DEFAULTS + _OPTIONAL_NUMERIC:
            if k in merged and not _is_num(merged[k]):
                problems.append(f"{where}: defaults.{k} must be a number.")
        if merged.get("key_type") not in model.KEY_TYPES:
            problems.append(f"{where}: defaults.key_type must be one of {model.KEY_TYPES}.")
        if merged.get("bolt_size") not in model.BOLT_SIZES:
            problems.append(f"{where}: defaults.bolt_size must be one of {model.BOLT_SIZES}.")
        if _is_num(merged.get("wall_mm")) and _is_num(merged.get("wall_min_mm")) and merged["wall_min_mm"] > merged["wall_mm"]:
            problems.append(f"{where}: wall_min_mm exceeds wall_mm.")
        for k in ("estimated",):
            if not isinstance(c.get(k, []), list):
                problems.append(f"{where}: '{k}' must be a list.")
    return problems


def parse_presets(raw: Any) -> PresetLibrary:
    problems = validate_presets(raw)
    if problems:
        raise PresetError(problems)
    base = raw["base_defaults"]
    molds = {
        m["id"]: MoldMaterial(m["id"], m["label"], float(m["max_service_C"]), bool(m.get("estimated", False)))
        for m in raw["mold_materials"]
    }
    casting: Dict[str, CastingMaterial] = {}
    for c in raw["casting_materials"]:
        defaults = dict(base)
        defaults.update(c["defaults"])
        casting[c["id"]] = CastingMaterial(
            id=c["id"],
            label=c["label"],
            allowed_mold_types=tuple(c["allowed_mold_types"]),
            default_mold_type=c["default_mold_type"],
            recommended_mold_materials=tuple(c["recommended_mold_materials"]),
            forbidden_mold_materials=tuple(c["forbidden_mold_materials"]),
            defaults=defaults,
            warnings=tuple(c.get("warnings", [])),
            process_temp_C=float(c["process_temp_C"]) if c.get("process_temp_C") is not None else None,
            estimated=tuple(c.get("estimated", [])),
            confidence=c.get("confidence", "normal"),
            mold_type_notes=dict(c.get("mold_type_notes", {})),
        )
    return PresetLibrary(casting=casting, mold_materials=molds)


def load_presets(path: Optional[str] = None) -> PresetLibrary:
    """Load presets from `path` (default: bundled materials.json)."""
    path = path or default_path()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except FileNotFoundError:
        raise PresetError([f"Presets file not found: {path}"]) from None
    except json.JSONDecodeError as exc:
        raise PresetError([f"Presets file is not valid JSON ({path}): {exc}"]) from exc
    return parse_presets(raw)
