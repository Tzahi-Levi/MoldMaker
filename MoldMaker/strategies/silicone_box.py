"""Silicone mold box: printed open-top box around the master; silicone is poured around it."""
from __future__ import annotations


from dataclasses import replace

from ..core import layout
from . import common
from ..core.model import BBox, BodyInfo, MoldParams, MoldPlan, PartSpec, PostSpec
from .base import MoldStrategy
from .two_part import resolve_parting_height

POST_MIN_D, POST_MAX_D = 4.0, 12.0


class SiliconeBoxStrategy(MoldStrategy):
    mold_type = "silicone_box"
    builds = True

    def plan(self, params: MoldParams, body: BodyInfo) -> MoldPlan:
        edge_note = params.silicone_two_part and params.sprue_enabled and params.sprue_location == "edge"
        if edge_note:  # a horizontal pin cannot leave through the printed box wall
            params = replace(params, sprue_location="top")
        frame, info, cavity_vol = self.prepare(params, body)
        cav = info.bbox
        wall, ft, bw = params.wall_mm, params.floor_top_mm, params.box_wall_mm
        inner = BBox((cav.min[0] - wall, cav.min[1] - wall, cav.min[2] - ft),
                     (cav.max[0] + wall, cav.max[1] + wall, cav.max[2] + ft))
        outer = BBox((inner.min[0] - bw, inner.min[1] - bw, inner.min[2] - bw),
                     (inner.max[0] + bw, inner.max[1] + bw, inner.max[2]))  # open top
        plan = MoldPlan(
            mold_type=self.mold_type, params=params, body_name=body.name, frame=frame,
            cavity_bbox=cav, block=outer, inner_block=inner,
            parts=[PartSpec("box", "Box", "box", (outer.min[2], outer.max[2]))],
        )

        # Locating post under the master (floor gap spans the full wall thickness).
        sx, sy, _ = cav.size
        d = min(max(0.25 * min(sx, sy), POST_MIN_D), POST_MAX_D)
        px, py = layout.footprint_of(info).nearest_inside(*cav.center[:2])
        plan.posts.append(PostSpec(px, py, d, inner.min[2], cav.min[2] + 1.0))

        if params.silicone_two_part:
            z, w = resolve_parting_height(params, info)
            feats = layout.plan_features(info, inner, params, wall, z, with_bolts=False)
            plan.parting_z = z
            plan.parts.append(PartSpec("bed", "Parting bed", "bed", (inner.min[2], z)))
            plan.keys, plan.sprue, plan.vents = feats.keys, feats.sprue, feats.vents
            plan.warnings += w + feats.warnings

        if edge_note:
            plan.warnings.append("Edge sprue is not supported for silicone boxes; a top spout pin is used.")
        inner_vol = inner.volume
        silicone_vol = inner_vol - cavity_vol
        plan.metrics["Silicone volume (cm3)"] = silicone_vol / 1000.0
        plan.metrics["Silicone mass (g)"] = silicone_vol / 1000.0 * params.silicone_density_g_cc
        if wall < 6:
            plan.warnings.append("Silicone wall under 6 mm tears easily; consider 8-10 mm.")
        return plan

    def build(self, plan: MoldPlan, adapter) -> None:
        p = plan.params
        inner, outer = plan.inner_block, plan.block
        # Printed box: outer block minus the inner volume (open top) plus the locating post.
        box = adapter.box(outer)
        adapter.cut(box, adapter.box(BBox(inner.min, (inner.max[0], inner.max[1], outer.max[2] + common.EXT))))
        for post in plan.posts:
            adapter.union(box, adapter.cylinder((post.x, post.y, post.z_from - 0.5), (post.x, post.y, post.z_to), post.d_mm / 2))
        parts = [("Box", [("box", box)])]

        if p.silicone_two_part:
            pz = plan.parting_z
            bed = adapter.box(BBox(inner.min, (inner.max[0], inner.max[1], pz)))
            adapter.cut(bed, adapter.master())
            for key in plan.keys:
                adapter.union(bed, common.key_bump(adapter, key, pz))
            bodies = [("bed", bed)]
            pins = []
            if plan.sprue:
                pins.append(("spout_pin", common.sprue_tools(adapter, plan.sprue, inner)))
            for i, vent in enumerate(plan.vents):
                pins.append((f"vent_pin_{i + 1}", common.vent_tools(adapter, vent, inner)))
            for name, tools in pins:
                pin = tools[0]
                for extra in tools[1:]:
                    adapter.union(pin, extra)
                bodies.append((name, pin))
            parts.append(("Parting bed", bodies))
        adapter.commit(parts)
