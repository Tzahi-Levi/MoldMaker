"""Vacuum-forming buck: the master hollowed to a thin shell on a base flange.

Air is pulled through small holes at pits (concave low points) of the top surface into the
hollow interior, which opens downward through the flange onto the vacuum bed.
Only male bucks (formed over from above, released upward) are built.
"""
from __future__ import annotations

from typing import Any

from ..core import draft, layout, parting
from ..core.model import BBox, BodyInfo, MoldParams, MoldPlan, PartSpec, PostSpec, VentSpec
from . import common
from .base import MoldStrategy

MIN_SHELL_MM = 2.0
MAX_HOLES = 12


class VacuumBuckStrategy(MoldStrategy):
    mold_type = "vacuum_buck"
    builds = True

    def plan(self, params: MoldParams, body: BodyInfo) -> MoldPlan:
        frame, info, cavity_vol = self.prepare(params, body)
        cav = info.bbox
        shell, fw = params.shell_mm, params.flange_w_mm
        flange_t = max(shell, 3.0)
        block = BBox((cav.min[0] - fw, cav.min[1] - fw, cav.min[2] - flange_t),
                     (cav.max[0] + fw, cav.max[1] + fw, cav.max[2]))

        plan = MoldPlan(
            mold_type=self.mold_type, params=params, body_name=body.name, frame=frame,
            cavity_bbox=cav, block=block, parting_z=None,
            parts=[PartSpec("buck", "Buck", "buck", (block.min[2], block.max[2]))],
        )
        if shell < MIN_SHELL_MM:
            plan.warnings.append(f"Shell thinner than {MIN_SHELL_MM:g} mm will not survive the heat and vacuum.")

        # vent holes at pits of the top surface, through the shell into the hollow
        for x, y, z in parting.low_points_from_rays(info.rays, MAX_HOLES):
            plan.vents.append(VentSpec("buck_hole", x, y, z + common.EXT, z - shell - 2 * common.EXT, params.vent_hole_d_mm))
        if not info.rays:
            plan.warnings.append("No section data: vent holes could not be placed at recesses.")

        # hollow opens downward through the flange via a stem under the master's centre
        sx, sy, _ = cav.size
        px, py = layout.footprint_of(info).nearest_inside(*cav.center[:2])
        plan.posts.append(PostSpec(px, py, 0.5 * min(sx, sy), block.min[2] - common.EXT, cav.min[2] + shell + common.EXT))
        plan.extras.update(shell=shell, flange_t=flange_t)
        plan.metrics["Expected master volume (cm3)"] = cavity_vol / 1000.0
        return plan

    def build(self, plan: MoldPlan, adapter: Any) -> None:
        shell, ft = plan.extras["shell"], plan.extras["flange_t"]
        cav = plan.cavity_bbox
        master = adapter.master()
        (x0, y0, z0), (x1, y1, _) = plan.block.min, plan.block.max

        buck = adapter.copy(master)
        adapter.union(buck, adapter.box(BBox((x0, y0, cav.min[2] - ft), (x1, y1, cav.min[2]))))

        interior = adapter.offset(master, -shell)
        if adapter.volume(interior) >= adapter.volume(master):
            adapter.warn("The hollow is not smaller than the master; the inward offset may have failed. Check wall thickness.")
        stem = plan.posts[0]
        adapter.union(interior, adapter.cylinder((stem.x, stem.y, stem.z_from), (stem.x, stem.y, stem.z_to), stem.d_mm / 2))
        adapter.cut(buck, interior)

        for hole in plan.vents:
            for tool in common.vent_tools(adapter, hole, plan.block):
                adapter.cut(buck, tool)

        report = draft.analyze(adapter.draft_samples(), plan.params.draft_deg, buck=True)
        for w in draft.warnings_for(report, plan.params.draft_deg):
            adapter.warn(w.replace("(faces looking away from the opening, or a back that is not flat)",
                                   "(faces that tuck under, which the formed sheet cannot release from)"))
        adapter.commit([("Buck", [("buck", buck)])])
