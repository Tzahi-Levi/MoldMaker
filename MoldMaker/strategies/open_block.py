"""Open block: a block with the cavity cut from the top face (the part's flat back). No split."""
from __future__ import annotations

from ..core import draft, layout
from . import common
from ..core.model import BBox, BodyInfo, MoldParams, MoldPlan, PartSpec
from .base import MoldStrategy


class OpenBlockStrategy(MoldStrategy):
    mold_type = "open_block"
    builds = True

    def plan(self, params: MoldParams, body: BodyInfo) -> MoldPlan:
        frame, info, cavity_vol = self.prepare(params, body)
        block = layout.block_from_cavity(info.bbox, params.wall_mm, params.floor_top_mm, open_top=True)
        plan = MoldPlan(
            mold_type=self.mold_type, params=params, body_name=body.name, frame=frame,
            cavity_bbox=info.bbox, block=block, parting_z=None,
            parts=[PartSpec("block", "Block", "block", (block.min[2], block.max[2]))],
        )
        plan.metrics["Expected cavity volume (cm3)"] = cavity_vol / 1000.0
        if params.draft_deg <= 0:
            plan.warnings.append("Draft angle is 0: a straight-sided open mold can lock the casting in. Consider >= 1 deg.")
        return plan

    def build(self, plan: MoldPlan, adapter) -> None:
        block = adapter.box(plan.block)
        before = adapter.volume(block)
        # The flat back is coplanar with the block's top face. Extending the tool above it makes
        # the boolean cut straight through that plane instead of sliding along it.
        tool = adapter.master()
        (x0, y0, _), (x1, y1, z1) = plan.cavity_bbox.min, plan.cavity_bbox.max
        adapter.union(tool, adapter.box(BBox((x0, y0, z1), (x1, y1, z1 + common.EXT))))
        adapter.cut(block, tool)
        for w in common.check_removed_volume(plan, before - adapter.volume(block)):
            adapter.warn(w)
        report = draft.analyze(adapter.draft_samples(), plan.params.draft_deg)
        for w in draft.warnings_for(report, plan.params.draft_deg):
            adapter.warn(w)
        adapter.commit([("Block", [("block", block)])])
