"""The user parameters MoldMaker publishes for a plan (pure; the adapter creates them).

They document the settings used. Geometry is built from temporary bodies, so
editing a parameter does not regenerate the mold.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .model import MoldPlan

PREFIX = "MM_"
NOTE = "MoldMaker setting (informational; the mold does not update when this changes)"


@dataclass(frozen=True)
class UserParam:
    name: str
    value: float
    unit: str  # "mm", "deg" or "" (unitless)
    comment: str


def from_plan(plan: MoldPlan) -> List[UserParam]:
    p = plan.params
    out = [
        UserParam(PREFIX + "wall", p.wall_mm, "mm", "Wall thickness. " + NOTE),
        UserParam(PREFIX + "floor_top", p.floor_top_mm, "mm", "Floor / top thickness. " + NOTE),
        UserParam(PREFIX + "shrink_pct", p.shrink_pct, "", "Uniform shrinkage in percent. " + NOTE),
        UserParam(PREFIX + "draft", p.draft_deg, "deg", "Draft angle. " + NOTE),
    ]
    if plan.keys:
        out += [UserParam(PREFIX + "key_d", p.key_d_mm, "mm", "Registration key diameter. " + NOTE),
                UserParam(PREFIX + "key_clearance", p.key_clearance_mm, "mm", "Registration key clearance. " + NOTE)]
    if plan.sprue:
        out += [UserParam(PREFIX + "sprue_d", p.sprue_d_mm, "mm", "Sprue diameter. " + NOTE),
                UserParam(PREFIX + "funnel_d", p.funnel_d_mm, "mm", "Funnel diameter. " + NOTE)]
    if plan.vents:
        out.append(UserParam(PREFIX + "vent_d", p.vent_d_mm, "mm", "Vent diameter. " + NOTE))
    return out
