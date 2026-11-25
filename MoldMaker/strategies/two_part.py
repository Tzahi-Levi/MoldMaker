"""Two-part rigid mold: block - cavity, split at a planar parting height."""
from __future__ import annotations

from typing import List, Optional, Tuple

from ..core import layout, parting
from . import common
from ..core.model import BodyInfo, BBox, MoldParams, MoldPlan, PartSpec
from .base import MoldStrategy

UNDERCUT_WARN_BELOW = 0.98


def resolve_parting_height(params: MoldParams, info: BodyInfo) -> Tuple[float, List[str]]:
    """Parting height (local w) for the shrink-scaled info, plus warnings."""
    z0, z1 = info.bbox.min[2], info.bbox.max[2]
    warnings: List[str] = []
    if params.parting_mode == "manual":
        z = (z0 + z1) / 2.0 + params.parting_offset_mm
        lo, hi = z0 + 0.1, z1 - 0.1
        if not lo <= z <= hi:
            warnings.append("Manual parting offset places the plane outside the part; clamped to the part's extent.")
            z = min(max(z, lo), hi)
        return z, warnings
    if info.rays:
        z, score = parting.choose_parting_height(info.rays, z0, z1)
        if score < UNDERCUT_WARN_BELOW:
            warnings.append(
                f"Best planar parting plane only spans {score:.0%} of the part silhouette: expect undercuts. "
                "Try another pull direction or a manual parting height."
            )
        return z, warnings
    warnings.append("No section data for the part; parting plane set at mid-height. Use Manual mode to adjust.")
    return (z0 + z1) / 2.0, warnings


class TwoPartStrategy(MoldStrategy):
    mold_type = "two_part"
    builds = True

    def plan(self, params: MoldParams, body: BodyInfo) -> MoldPlan:
        frame, info, cavity_vol = self.prepare(params, body)
        block = layout.block_from_cavity(info.bbox, params.wall_mm, params.floor_top_mm)
        z, warnings = resolve_parting_height(params, info)
        feats = layout.plan_features(info, block, params, params.wall_mm, z)
        plan = MoldPlan(
            mold_type=self.mold_type, params=params, body_name=body.name, frame=frame,
            cavity_bbox=info.bbox, block=block, parting_z=z,
            parts=[
                PartSpec("lower", "Lower half", "half", (block.min[2], z)),
                PartSpec("upper", "Upper half", "half", (z, block.max[2])),
            ],
            keys=feats.keys, sprue=feats.sprue, vents=feats.vents, bolts=feats.bolts,
            warnings=warnings + feats.warnings,
        )
        plan.metrics["Expected cavity volume (cm3)"] = cavity_vol / 1000.0
        return plan

    def build(self, plan: MoldPlan, adapter) -> None:
        block = adapter.box(plan.block)
        before = adapter.volume(block)
        adapter.cut(block, adapter.master())
        for w in common.check_removed_volume(plan, before - adapter.volume(block)):
            adapter.warn(w)
        common.cut_pour_features(adapter, block, plan)
        common.cut_bolts(adapter, block, plan)
        lower, upper = common.split_at(adapter, block, plan)
        common.add_keys(adapter, lower, upper, plan)
        if plan.params.lay_flat:
            adapter.lay_flat(upper, plan)
        adapter.commit([("Lower half", [("lower", lower)]), ("Upper half", [("upper", upper)])])
