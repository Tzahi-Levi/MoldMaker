"""Core/cavity mold for injection or compression: two inserts split at a planar parting height.

Differences from the plain two-part mold:
  * the insert footprint is rounded up to a multiple of `insert_step_mm` so it fits a standard frame,
  * registration is by leader-pin holes (the pins themselves are bought dowels), not printed keys,
  * vents are flat parting-line slots (0.05 mm deep by default) instead of drilled holes,
  * an edge sprue becomes sprue + runner + a narrow gate into the cavity,
  * the parting height can optionally come from a Silhouette Split probe,
  * the draft is analysed per half and can optionally be applied to the cavity walls.
"""
from __future__ import annotations

import math
from dataclasses import replace
from typing import List, Optional, Tuple

from ..core import draft, layout, parting
from ..core.model import BBox, BodyInfo, KeySpec, MoldParams, MoldPlan, PartSpec, SprueSpec, VentSpec
from . import common
from .base import MoldStrategy
from .two_part import resolve_parting_height

GATE_LAND_MM = 2.0          # runner stops this far outside the cavity; the gate bridges the gap
SILHOUETTE_TOL_MM = 0.5     # planar parting is "good" if the silhouette loop stays within this of the plane
PIN_DEPTH_FACTOR = 2.0      # leader-pin hole depth = factor * pin diameter
MIN_PLATE_MM = 2.0          # material kept beyond the bottom of a pin hole


def round_up_block(block: BBox, step: float) -> BBox:
    """Grow the block symmetrically in u and v so each size is a multiple of `step`."""
    if step <= 0:
        return block
    lo, hi = list(block.min), list(block.max)
    for i in (0, 1):
        size = hi[i] - lo[i]
        target = math.ceil(size / step - 1e-9) * step
        grow = (target - size) / 2.0
        lo[i] -= grow
        hi[i] += grow
    return BBox(tuple(lo), tuple(hi))  # type: ignore[arg-type]


def _section_points(info: BodyInfo, z: float) -> List[Tuple[float, float]]:
    return [(x, y) for x, y, iv in info.rays if any(a - 1e-6 <= z <= b + 1e-6 for a, b in iv)]


def runner_and_gate(info: BodyInfo, block: BBox, sprue: SprueSpec, params: MoldParams, z: float):
    """Move an edge sprue back to a runner end outside the cavity and design the gate between them.

    Returns (new_sprue, gate) with gate = (x0, y0, x1, y1, d_mm), or (sprue, None) with a warning list
    when the cavity has no cross-section at the parting plane.
    """
    pts = _section_points(info, z)
    if not pts:
        return sprue, None, ["The cavity has no cross-section at the parting plane; the runner could not be gated."]
    ex, ey = layout._nearest_face_point(block, sprue.x, sprue.y)
    tx, ty = min(pts, key=lambda p: math.hypot(p[0] - ex, p[1] - ey))
    dx, dy = ex - tx, ey - ty
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return sprue, None, ["The cavity reaches the block edge at the parting plane; increase the wall thickness."]
    ux, uy = dx / length, dy / length
    reach = max(info.ray_spacing_mm, 0.5) * 0.75

    def covered(t: float) -> bool:
        px, py = tx + ux * t, ty + uy * t
        return any(math.hypot(px - x, py - y) <= reach for x, y in pts)

    t = 0.0
    while t < length and covered(t + 0.25):
        t += 0.25
    runner_t = t + GATE_LAND_MM
    if runner_t >= length - params.sprue_d_mm / 2:
        return sprue, None, ["Not enough wall between the cavity and the block edge for a runner and gate; "
                             "increase the wall thickness."]
    rx, ry = tx + ux * runner_t, ty + uy * runner_t
    new = SprueSpec("edge", rx, ry, z, z, sprue.d_mm, sprue.funnel_d_mm, 0.0, edge_from=layout._nearest_face_point(block, rx, ry))
    gate = (rx, ry, tx + ux * max(t - 1.0, 0.0), ty + uy * max(t - 1.0, 0.0), params.gate_d_mm)
    return new, gate, []


class CoreCavityStrategy(MoldStrategy):
    mold_type = "core_cavity"
    builds = True

    def plan(self, params: MoldParams, body: BodyInfo) -> MoldPlan:
        frame, info, cavity_vol = self.prepare(params, body)
        block = round_up_block(layout.block_from_cavity(info.bbox, params.wall_mm, params.floor_top_mm), params.insert_step_mm)
        z, warnings = resolve_parting_height(params, info)
        warnings += self._silhouette(params, info, z)
        if params.parting_silhouette and params.parting_mode == "auto":
            z_sil, _ = parting.height_from_silhouette(info.silhouette_z, info.bbox.min[2], info.bbox.max[2])
            if z_sil is not None:
                z = z_sil
        if params.draft_deg <= 0:
            warnings.append("Draft angle is 0: injection-moulded parts usually need 1-2 deg to eject. Set a draft angle.")

        # layout works with the pin size and the slot width in place of key and vent diameters
        lp = replace(params, key_type="cone", key_d_mm=params.leader_pin_d_mm,
                     vent_d_mm=max(params.vent_d_mm, params.vent_slot_w_mm))
        feats = layout.plan_features(info, block, lp, params.wall_mm, z, with_keys=False, with_bolts=False)
        warnings += feats.warnings
        sprue, gate = feats.sprue, None
        if sprue is not None and sprue.location == "edge":
            sprue, gate, w = runner_and_gate(info, block, sprue, params, z)
            warnings += w
        vents = [self._as_slot(v, params, z) for v in feats.vents]

        fp = layout.footprint_of(info)
        obstacles = layout.obstacles_for(sprue, vents)
        keys, w = layout.place_keys(block, fp, lp, params.wall_mm, obstacles)
        warnings += [x.replace("registration key", "leader pin").replace("registration keys", "leader pins") for x in w]
        keys = [KeySpec(k.x, k.y, k.d_mm, "pin") for k in keys]
        obstacles += [layout.Obstacle(k.x, k.y, k.x, k.y, k.d_mm / 2 + layout.FEATURE_GAP) for k in keys]
        bolts, w = layout.place_bolts(block, fp, lp, params.wall_mm, obstacles)
        warnings += w

        depth_ok = PIN_DEPTH_FACTOR * params.leader_pin_d_mm + MIN_PLATE_MM
        if keys and min(z - block.min[2], block.max[2] - z) < depth_ok:
            warnings.append(f"Leader-pin holes need about {depth_ok:.0f} mm of plate on both sides of the parting plane; "
                            "they will be shortened. Increase the floor/top thickness.")

        plan = MoldPlan(
            mold_type=self.mold_type, params=params, body_name=body.name, frame=frame,
            cavity_bbox=info.bbox, block=block, parting_z=z,
            parts=[PartSpec("lower", "Core insert", "half", (block.min[2], z)),
                   PartSpec("upper", "Cavity insert", "half", (z, block.max[2]))],
            keys=keys, sprue=sprue, vents=vents, bolts=bolts, warnings=warnings,
        )
        if gate:
            plan.extras["gate"] = gate
        plan.metrics["Expected cavity volume (cm3)"] = cavity_vol / 1000.0
        return plan

    @staticmethod
    def _silhouette(params: MoldParams, info: BodyInfo, z: float) -> List[str]:
        if not params.parting_silhouette:
            return []
        if params.parting_mode != "auto":
            return ["Silhouette parting ignored: the parting height is set manually."]
        z_sil, dev = parting.height_from_silhouette(info.silhouette_z, info.bbox.min[2], info.bbox.max[2])
        if z_sil is None:
            return ["Silhouette Split could not find a silhouette loop; the planar parting height from the section scan was used."]
        if dev > SILHOUETTE_TOL_MM:
            return [f"The silhouette loop wanders {dev:.1f} mm from the planar parting plane at {z_sil:.1f} mm: "
                    "a flat parting plane leaves that much of the part in undercut. Check the draft report, or change the pull direction."]
        return []

    @staticmethod
    def _as_slot(v: VentSpec, params: MoldParams, z: float) -> VentSpec:
        if v.kind != "parting_channel":
            return replace(v, d_mm=params.vent_d_mm)  # risers keep the drilled diameter
        return VentSpec("slot", v.x, v.y, z - params.vent_slot_depth_mm, z, params.vent_slot_w_mm, edge_to=v.edge_to)

    def build(self, plan: MoldPlan, adapter) -> None:
        block = adapter.box(plan.block)
        before = adapter.volume(block)
        adapter.cut(block, adapter.master())
        for w in common.check_removed_volume(plan, before - adapter.volume(block)):
            adapter.warn(w)
        common.cut_pour_features(adapter, block, plan)
        gate = plan.extras.get("gate")
        if gate:
            x0, y0, x1, y1, d = gate
            z = plan.parting_z
            adapter.cut(block, adapter.cylinder((x0, y0, z), (x1, y1, z), d / 2.0))
        common.cut_bolts(adapter, block, plan)
        lower, upper = common.split_at(adapter, block, plan)
        common.add_keys(adapter, lower, upper, plan)

        pz = plan.parting_z
        report = draft.analyze_two_sided(adapter.draft_samples(), pz, plan.params.draft_deg)
        for w in draft.warnings_for(report, plan.params.draft_deg):
            adapter.warn(w)
        if plan.params.lay_flat:
            adapter.lay_flat(upper, plan)
        adapter.commit([("Core insert", [("lower", lower)]), ("Cavity insert", [("upper", upper)])])
        if plan.params.apply_draft and plan.params.draft_deg > 0:
            adapter.apply_draft(plan)
