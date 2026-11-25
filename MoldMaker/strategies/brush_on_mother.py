"""Brush-on silicone skin + rigid mother mold.

skin envelope = master offset by the skin thickness
mother mold   = envelope offset by the shell thickness, minus the envelope, split at the parting
                plane, with a flange (keys and bolts) around the parting plane.
"""
from __future__ import annotations

from dataclasses import replace

from ..core import layout
from ..core.model import BBox, BodyInfo, MoldParams, MoldPlan, PartSpec
from . import common
from .base import MoldStrategy
from .two_part import resolve_parting_height


class BrushOnMotherStrategy(MoldStrategy):
    mold_type = "brush_on_mother"
    builds = True

    def plan(self, params: MoldParams, body: BodyInfo) -> MoldPlan:
        frame, info, cavity_vol = self.prepare(params, body)
        skin, shell, fw = params.skin_mm, params.shell_mm, params.flange_w_mm
        grow = skin + shell
        cav = info.bbox
        outer = BBox((cav.min[0] - grow, cav.min[1] - grow, cav.min[2] - grow),
                     (cav.max[0] + grow, cav.max[1] + grow, cav.max[2] + grow))
        hw = layout.HARDWARE[params.bolt_size]
        stack = (hw.cbore_depth if params.bolt_counterbore else 0.0) + (hw.nut_depth if params.bolt_nut_trap else 0.0)
        flange_t = max(shell, 3.0, stack / 2.0 + 0.5) if params.bolts_enabled else max(shell, 3.0)
        block = layout.block_from_cavity(outer, fw, flange_t)  # flange extent; z padded so the flange always fits

        z, warnings = resolve_parting_height(params, info)
        # keys and bolts live on the flange, clear of the grown (skin + shell) silhouette
        grown = replace(info, bbox=outer, footprint=layout.footprint_of(info).grown(grow))
        feats = layout.plan_features(grown, block, params, fw, z, with_pour=False)

        plan = MoldPlan(
            mold_type=self.mold_type, params=params, body_name=body.name, frame=frame,
            cavity_bbox=cav, block=block, parting_z=z,
            parts=[PartSpec("mother_lower", "Mother lower", "half", (block.min[2], z)),
                   PartSpec("mother_upper", "Mother upper", "half", (z, block.max[2])),
                   PartSpec("skin", "Silicone skin", "reference", (cav.min[2] - skin, cav.max[2] + skin))],
            keys=feats.keys, bolts=feats.bolts, warnings=warnings + feats.warnings,
        )
        plan.extras.update(skin=skin, shell=shell, flange_t=flange_t, flange_z=(z - flange_t, z + flange_t))
        plan.metrics["Expected cavity volume (cm3)"] = cavity_vol / 1000.0
        if skin < 2.0:
            plan.warnings.append("Silicone skin under 2 mm tears easily; 3-5 mm is typical.")
        if shell < 3.0:
            plan.warnings.append("Mother-mold shell under 3 mm may flex; 4 mm or more is advised.")
        return plan

    def build(self, plan: MoldPlan, adapter) -> None:
        p = plan.params
        skin, shell = plan.extras["skin"], plan.extras["shell"]
        z0, z1 = plan.extras["flange_z"]
        master = adapter.master()
        envelope = adapter.offset(master, skin)
        if adapter.volume(envelope) <= adapter.volume(master):
            adapter.warn("The silicone envelope is not larger than the master; the offset may have failed.")
        skin_body = adapter.copy(envelope)
        adapter.cut(skin_body, master)

        mother = adapter.offset(envelope, shell)
        adapter.cut(mother, envelope)

        (x0, y0, _), (x1, y1, _) = plan.block.min, plan.block.max
        flange = adapter.box(BBox((x0, y0, z0), (x1, y1, z1)))
        adapter.cut(flange, envelope)
        adapter.union(mother, flange)
        common.cut_bolts(adapter, mother, plan, z_range=(z0, z1))

        lower, upper = common.split_at(adapter, mother, plan)
        common.add_keys(adapter, lower, upper, plan)
        if p.lay_flat:
            adapter.lay_flat(upper, plan)
        adapter.commit([
            ("Mother lower", [("mother_lower", lower)]),
            ("Mother upper", [("mother_upper", upper)]),
            ("Silicone skin", [("skin", skin_body)]),
        ])
