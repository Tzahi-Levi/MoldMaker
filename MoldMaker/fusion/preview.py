"""Lightweight dialog preview drawn with custom graphics (never touches the design).

Shows the block outline, the parting plane, key bumps, sprue/vent tools and bolt
holes. Built from the same planner output and adapter primitives as the real
build, but with coarse sampling of the master for speed.
"""
from __future__ import annotations

from typing import Optional

import adsk.core
import adsk.fusion

from ..core.model import BBox, MoldPlan
from ..lib import fusion360utils as futil
from ..strategies import common
from .adapter import FusionAdapter

# RGBA 0-255
BLOCK = (70, 140, 230, 70)
INNER = (70, 140, 230, 50)
PARTING = (240, 165, 58, 120)
KEY = (60, 190, 120, 255)
POUR = (230, 70, 60, 200)
BOLT = (150, 150, 160, 200)


class Preview:
    def __init__(self) -> None:
        self.group: Optional[adsk.fusion.CustomGraphicsGroup] = None

    def clear(self) -> None:
        if self.group is not None:
            try:
                self.group.deleteMe()
            except Exception:
                pass
            self.group = None

    def show(self, app: adsk.core.Application, design: adsk.fusion.Design,
             target: adsk.fusion.BRepBody, plan: MoldPlan) -> None:
        self.clear()
        group = design.rootComponent.customGraphicsGroups.add()
        self.group = group
        ad = FusionAdapter(app, design, target, plan)

        def add(body, rgba) -> None:
            item = group.addBRepBody(body)
            item.color = adsk.fusion.CustomGraphicsSolidColorEffect.create(adsk.core.Color.create(*rgba))

        add(ad.box(plan.block), BLOCK)
        if plan.inner_block is not None:
            add(ad.box(plan.inner_block), INNER)
        if plan.parting_z is not None:
            (x0, y0, _), (x1, y1, _) = plan.block.min, plan.block.max
            pz = plan.parting_z
            add(ad.box(BBox((x0 - 3, y0 - 3, pz - 0.15), (x1 + 3, y1 + 3, pz + 0.15))), PARTING)
            for key in plan.keys:
                add(common.key_bump(ad, key, pz), KEY)
        if plan.sprue:
            for tool in common.sprue_tools(ad, plan.sprue, plan.block):
                add(tool, POUR)
        for vent in plan.vents:
            for tool in common.vent_tools(ad, vent, plan.block):
                add(tool, POUR)
        for bolt in plan.bolts:
            add(ad.cylinder((bolt.x, bolt.y, plan.block.min[2]), (bolt.x, bolt.y, plan.block.max[2]), bolt.hole_d_mm / 2), BOLT)
        futil.log("Preview drawn")
