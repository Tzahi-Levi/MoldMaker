"""Build steps shared by several strategies. Talks only to the adapter interface (pure; no adsk).

Adapter interface used here (all coordinates are local pull-frame mm):
  box(BBox) cylinder(p0, p1, r0, r1=None) sphere(c, r) hex_prism(x, y, z0, z1, af)
  copy(body) union(target, tool) cut(target, tool) intersect(target, tool)
"""
from __future__ import annotations

import math
from typing import Any, List, Tuple

from ..core.model import BBox, MoldPlan, SprueSpec

EXT = 1.0  # tools overshoot faces by this much so cuts are never coplanar


def _unit2(ax: float, ay: float, bx: float, by: float) -> Tuple[float, float, float]:
    dx, dy = bx - ax, by - ay
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return 1.0, 0.0, 0.0
    return dx / length, dy / length, length


def sprue_tools(adapter: Any, sprue: SprueSpec, block: BBox) -> List[Any]:
    """Bodies whose removal (or addition, for a pin) forms the sprue and its funnel."""
    r, fr = sprue.d_mm / 2.0, sprue.funnel_d_mm / 2.0
    h = (fr - r)  # 45 degree funnel
    if sprue.location == "top":
        top = block.max[2]
        tools = [adapter.cylinder((sprue.x, sprue.y, sprue.z_from), (sprue.x, sprue.y, top + EXT), r)]
        if sprue.funnel_h_mm > 0:
            fh = sprue.funnel_h_mm
            tools.append(adapter.cylinder((sprue.x, sprue.y, top - fh), (sprue.x, sprue.y, top + EXT), r, r + fh + EXT))
        return tools
    # edge: channel in the parting plane from the outer face to (x, y)
    ex, ey = sprue.edge_from  # type: ignore[misc]
    ux, uy, length = _unit2(sprue.x, sprue.y, ex, ey)
    z = sprue.z_from
    tools = [adapter.cylinder((sprue.x, sprue.y, z), (ex + ux * EXT, ey + uy * EXT, z), r)]
    if h > 0 and length > h:
        tools.append(adapter.cylinder((ex - ux * h, ey - uy * h, z), (ex + ux * EXT, ey + uy * EXT, z), r, fr + EXT))
    return tools


def vent_tools(adapter: Any, vent: Any, block: BBox) -> List[Any]:
    r = vent.d_mm / 2.0
    if vent.kind == "buck_hole":
        return [adapter.cylinder((vent.x, vent.y, vent.z_from), (vent.x, vent.y, vent.z_to), r)]
    if vent.kind == "slot":
        ex, ey = vent.edge_to
        ux, uy, _ = _unit2(vent.x, vent.y, ex, ey)
        return [adapter.slot((vent.x, vent.y), (ex + ux * EXT, ey + uy * EXT), vent.d_mm, vent.z_from, vent.z_to)]
    if vent.kind == "riser":
        return [adapter.cylinder((vent.x, vent.y, vent.z_from), (vent.x, vent.y, block.max[2] + EXT), r)]
    ex, ey = vent.edge_to
    ux, uy, _ = _unit2(vent.x, vent.y, ex, ey)
    return [adapter.cylinder((vent.x, vent.y, vent.z_from), (ex + ux * EXT, ey + uy * EXT, vent.z_from), r)]


def cut_pour_features(adapter: Any, block_body: Any, plan: MoldPlan) -> None:
    """Cut sprue + vents from the (unsplit) block so they pass through both halves."""
    if plan.sprue:
        for tool in sprue_tools(adapter, plan.sprue, plan.block):
            adapter.cut(block_body, tool)
    for vent in plan.vents:
        for tool in vent_tools(adapter, vent, plan.block):
            adapter.cut(block_body, tool)


def cut_bolts(adapter: Any, block_body: Any, plan: MoldPlan, z_range: Any = None) -> None:
    """Through holes, counterbore on top (+w), hex nut trap on the bottom.

    z_range=(z0, z1) restricts the hardware to a slab (e.g. a flange) instead of the whole block.
    """
    b = plan.block if z_range is None else BBox((plan.block.min[0], plan.block.min[1], z_range[0]),
                                                 (plan.block.max[0], plan.block.max[1], z_range[1]))
    for bolt in plan.bolts:
        adapter.cut(block_body, adapter.cylinder((bolt.x, bolt.y, b.min[2] - EXT), (bolt.x, bolt.y, b.max[2] + EXT), bolt.hole_d_mm / 2))
        if bolt.cbore_d_mm > 0:
            adapter.cut(block_body, adapter.cylinder((bolt.x, bolt.y, b.max[2] - bolt.cbore_depth_mm),
                                                     (bolt.x, bolt.y, b.max[2] + EXT), bolt.cbore_d_mm / 2))
        if bolt.nut_af_mm > 0:
            adapter.cut(block_body, adapter.hex_prism(bolt.x, bolt.y, b.min[2] - EXT, b.min[2] + bolt.nut_depth_mm, bolt.nut_af_mm))


def split_at(adapter: Any, block_body: Any, plan: MoldPlan) -> Tuple[Any, Any]:
    """Split a block body at the parting plane using half-space boxes; returns (lower, upper)."""
    pz = plan.parting_z
    (x0, y0, z0), (x1, y1, z1) = plan.block.min, plan.block.max
    pad = 2 * EXT
    lower = adapter.copy(block_body)
    adapter.intersect(lower, adapter.box(BBox((x0 - pad, y0 - pad, z0 - pad), (x1 + pad, y1 + pad, pz))))
    upper = adapter.copy(block_body)
    adapter.intersect(upper, adapter.box(BBox((x0 - pad, y0 - pad, pz), (x1 + pad, y1 + pad, z1 + pad))))
    return lower, upper


def key_bump(adapter: Any, key: Any, pz: float) -> Any:
    r = key.d_mm / 2.0
    if key.kind == "sphere":
        return adapter.sphere((key.x, key.y, pz), r)
    return adapter.cylinder((key.x, key.y, pz - EXT / 2), (key.x, key.y, pz + r), r, r / 2.0)


def key_socket(adapter: Any, key: Any, pz: float, clearance: float) -> Any:
    r = key.d_mm / 2.0 + clearance
    if key.kind == "sphere":
        return adapter.sphere((key.x, key.y, pz), r)
    return adapter.cylinder((key.x, key.y, pz - EXT), (key.x, key.y, pz + key.d_mm / 2.0 + clearance), r, key.d_mm / 4.0 + clearance)


def pin_hole_depth(plan: MoldPlan, d_mm: float) -> float:
    """Leader-pin hole depth: 2 diameters, kept clear of the plate's far face."""
    pz = plan.parting_z
    room = min(pz - plan.block.min[2], plan.block.max[2] - pz) - 2.0
    return max(min(2.0 * d_mm, room), 1.0)


def add_keys(adapter: Any, lower: Any, upper: Any, plan: MoldPlan) -> None:
    """Bumps joined to the lower half; clearance-enlarged sockets cut from the upper half.

    "pin" keys are leader-pin holes instead: a snug hole in the lower half, a clearance hole in the upper.
    """
    pz = plan.parting_z
    for key in plan.keys:
        if key.kind == "pin":
            depth = pin_hole_depth(plan, key.d_mm)
            adapter.cut(lower, adapter.cylinder((key.x, key.y, pz - depth), (key.x, key.y, pz + EXT), key.d_mm / 2.0))
            adapter.cut(upper, adapter.cylinder((key.x, key.y, pz - EXT), (key.x, key.y, pz + depth),
                                                key.d_mm / 2.0 + plan.params.key_clearance_mm))
            continue
        adapter.union(lower, key_bump(adapter, key, pz))
        adapter.cut(upper, key_socket(adapter, key, pz, plan.params.key_clearance_mm))


def check_removed_volume(plan: MoldPlan, removed_mm3: float, tolerance: float = 0.02) -> List[str]:
    """Compare the volume removed by the cavity cut with the expected (shrink-scaled) master volume."""
    expected = plan.metrics.get("Expected cavity volume (cm3)", 0.0) * 1000.0
    if expected <= 0:
        return []
    err = abs(removed_mm3 - expected) / expected
    if err > tolerance:
        return [f"Cavity volume check: removed {removed_mm3 / 1000:.2f} cm3 but expected {expected / 1000:.2f} cm3 "
                f"({err:.1%} off). The master may have voids, be non-manifold, or poke out of the block."]
    return []
