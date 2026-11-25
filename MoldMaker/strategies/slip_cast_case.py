"""Slip-casting plaster mold: printed cases to cast the two plaster halves around the master.

The master is scaled up by the clay shrinkage and given a slip-well plug on its highest point.
Plaster block = cavity (master + well) plus the plaster thickness on every side, open at the
top of the well. The printed case is a shell around each plaster half, open on the parting
side: that open side is the pour opening when the case is filled with plaster.
"""
from __future__ import annotations

import math
from typing import Any

from ..core import layout
from ..core.model import BBox, BodyInfo, MoldParams, MoldPlan, PartSpec, PostSpec
from . import common
from .base import MoldStrategy
from .two_part import resolve_parting_height

WELL_MIN_D, WELL_MAX_D = 10.0, 60.0


class SlipCastCaseStrategy(MoldStrategy):
    mold_type = "slip_cast_case"
    builds = True

    def plan(self, params: MoldParams, body: BodyInfo) -> MoldPlan:
        frame, info, cavity_vol = self.prepare(params, body)
        cav = info.bbox
        t, cw, well_h = params.plaster_thickness_mm, params.case_wall_mm, params.slip_well_h_mm
        sx, sy, _ = cav.size
        hx, hy, hz = info.high_points[0] if info.high_points else (cav.center[0], cav.center[1], cav.max[2])
        well_d = params.slip_well_d_mm or min(max(0.4 * min(sx, sy), WELL_MIN_D), WELL_MAX_D)
        well_top = max(hz, cav.max[2]) + well_h

        plaster = BBox((cav.min[0] - t, cav.min[1] - t, cav.min[2] - t), (cav.max[0] + t, cav.max[1] + t, well_top))
        case = BBox((plaster.min[0] - cw, plaster.min[1] - cw, plaster.min[2] - cw),
                    (plaster.max[0] + cw, plaster.max[1] + cw, plaster.max[2] + cw))
        z, warnings = resolve_parting_height(params, info)

        plan = MoldPlan(
            mold_type=self.mold_type, params=params, body_name=body.name, frame=frame,
            cavity_bbox=cav, block=plaster, parting_z=z,
            parts=[PartSpec("case_lower", "Lower case", "case", (case.min[2], z)),
                   PartSpec("case_upper", "Upper case", "case", (z, case.max[2])),
                   PartSpec("master_well", "Master with well", "reference", (cav.min[2], well_top)),
                   PartSpec("plaster", "Plaster mold (reference)", "reference", (plaster.min[2], plaster.max[2]))],
            posts=[PostSpec(hx, hy, well_d, hz - 1.0, well_top)],  # the slip-well plug
            warnings=warnings,
        )
        plan.extras["case_outer"] = case
        if well_d > 0.9 * min(sx, sy):
            plan.warnings.append("The slip well is nearly as wide as the part; reduce the well diameter.")

        # plaster / water estimate (cavity = scaled master + well cylinder above the master's top)
        well_vol = math.pi * (well_d / 2) ** 2 * max(well_top - hz, 0.0)
        self._estimate(plan, plaster.volume - cavity_vol - well_vol)
        return plan

    @staticmethod
    def _estimate(plan: MoldPlan, plaster_vol_mm3: float) -> None:
        """Mass of plaster powder and water for a 10:7 by-weight mix filling `plaster_vol_mm3`."""
        p = plan.params
        a, b = p.plaster_to_water
        slurry_g = plaster_vol_mm3 / 1000.0 * p.plaster_slurry_density_g_cc
        plan.metrics["Plaster volume (cm3)"] = plaster_vol_mm3 / 1000.0
        plan.metrics["Plaster powder (g)"] = slurry_g * a / (a + b)
        plan.metrics["Water (g)"] = slurry_g * b / (a + b)

    def build(self, plan: MoldPlan, adapter: Any) -> None:
        well = plan.posts[0]
        top = plan.block.max[2]
        tool = adapter.master()
        adapter.union(tool, adapter.cylinder((well.x, well.y, well.z_from), (well.x, well.y, top + common.EXT), well.d_mm / 2))

        plaster = adapter.box(plan.block)
        before = adapter.volume(plaster)
        adapter.cut(plaster, tool)
        self._estimate(plan, adapter.volume(plaster))  # measured, replaces the estimate
        if adapter.volume(plaster) >= before:
            adapter.warn("The plaster block lost no volume: the cavity cut may have failed.")
        lower, upper = common.split_at(adapter, plaster, plan)

        pz, c, b = plan.parting_z, plan.extras["case_outer"], plan.block
        e = common.EXT
        case_lower = adapter.box(BBox(c.min, (c.max[0], c.max[1], pz)))
        adapter.cut(case_lower, adapter.box(BBox((b.min[0], b.min[1], b.min[2]), (b.max[0], b.max[1], pz + e))))
        case_upper = adapter.box(BBox((c.min[0], c.min[1], pz), c.max))
        adapter.cut(case_upper, adapter.box(BBox((b.min[0], b.min[1], pz - e), b.max)))

        adapter.commit([
            ("Lower case", [("case_lower", case_lower)]),
            ("Upper case", [("case_upper", case_upper)]),
            ("Master with well", [("master_well", tool)]),
            ("Plaster mold (reference)", [("plaster_lower", lower), ("plaster_upper", upper)]),
        ])
