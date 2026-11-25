"""Block sizing and feature placement with collision tests (pure, mm, pull frame).

Placement order matters: sprue -> vents -> keys -> bolts. Each later feature
treats the earlier ones as obstacles. Every placement that cannot be satisfied
produces a warning instead of a silent overlap.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence, Tuple

from .model import (
    BBox, BodyInfo, BoltSpec, Footprint, KeySpec, MoldParams, RectFootprint, SprueSpec, VentSpec,
)


# --------------------------------------------------------------- hardware
@dataclass(frozen=True)
class Hardware:
    hole_d: float      # through hole (clearance)
    cbore_d: float     # counterbore diameter
    cbore_depth: float
    nut_af: float      # hex nut across-flats incl. clearance
    nut_depth: float   # nut trap depth incl. clearance

    @property
    def nut_corner_d(self) -> float:
        return self.nut_af / math.cos(math.radians(30))


# Engineering defaults for ISO metric socket-head screws and standard nuts.
HARDWARE = {
    "M3": Hardware(3.4, 6.5, 3.2, 5.8, 2.6),
    "M4": Hardware(4.5, 8.0, 4.2, 7.3, 3.4),
    "M5": Hardware(5.5, 10.0, 5.2, 8.3, 4.2),
}

BOLT_EDGE_MARGIN = 0.5      # bolt counterbore/nut trap keep this much material to the outer face
KEY_EDGE_MARGIN = 1.0       # keys keep this much material to the block's outer face
CAVITY_KEY_EXTRA = 2.0      # material kept between a key's edge and the cavity (centre distance >= key_d/2 + 2)
CAVITY_BOLT_EXTRA = 2.0     # bolt holes keep this much material to the cavity
FEATURE_GAP = 1.0           # minimum material between features


@dataclass(frozen=True)
class Obstacle:
    """A thick line segment (zero-length == circle) in the parting plane."""
    x0: float
    y0: float
    x1: float
    y1: float
    r: float

    def clearance(self, x: float, y: float) -> float:
        dx, dy = self.x1 - self.x0, self.y1 - self.y0
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((x - self.x0) * dx + (y - self.y0) * dy) / L2))
        return math.hypot(x - (self.x0 + t * dx), y - (self.y0 + t * dy)) - self.r


@dataclass
class Features:
    sprue: Optional[SprueSpec] = None
    vents: List[VentSpec] = field(default_factory=list)
    keys: List[KeySpec] = field(default_factory=list)
    bolts: List[BoltSpec] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


# ------------------------------------------------------------------ blocks
def block_from_cavity(cavity: BBox, wall: float, floor_top: float, open_top: bool = False) -> BBox:
    """Outer block: wall on u/v, floor_top below and above (open_top: flush with the cavity top)."""
    (x0, y0, z0), (x1, y1, z1) = cavity.min, cavity.max
    return BBox((x0 - wall, y0 - wall, z0 - floor_top),
                (x1 + wall, y1 + wall, z1 if open_top else z1 + floor_top))


def footprint_of(info: BodyInfo) -> Footprint:
    if info.footprint is not None:
        return info.footprint
    (x0, y0, _), (x1, y1, _) = info.bbox.min, info.bbox.max
    return RectFootprint(x0, y0, x1, y1)


# ---------------------------------------------------------------- search
def _nearest_valid(
    target: Tuple[float, float],
    bounds: Tuple[float, float, float, float],
    accept: Callable[[float, float], bool],
    step: float = 1.0,
    max_candidates: int = 40000,
) -> Optional[Tuple[float, float]]:
    """Closest accepted grid point to `target` inside `bounds` (None if none)."""
    x0, y0, x1, y1 = bounds
    if x1 < x0 or y1 < y0:
        return None
    if accept(*target) and x0 <= target[0] <= x1 and y0 <= target[1] <= y1:
        return target
    nx, ny = int((x1 - x0) / step) + 1, int((y1 - y0) / step) + 1
    while nx * ny > max_candidates:
        step *= 1.5
        nx, ny = int((x1 - x0) / step) + 1, int((y1 - y0) / step) + 1
    cands = [(math.hypot(x0 + i * step - target[0], y0 + j * step - target[1]), x0 + i * step, y0 + j * step)
             for i in range(nx) for j in range(ny)]
    cands.sort()
    for _, x, y in cands:
        if accept(x, y):
            return (x, y)
    return None


def _nearest_face_point(block: BBox, x: float, y: float) -> Tuple[float, float]:
    """Point on the block's outer side face closest to (x, y)."""
    d = {"x0": x - block.min[0], "x1": block.max[0] - x, "y0": y - block.min[1], "y1": block.max[1] - y}
    side = min(d, key=d.get)  # type: ignore[arg-type]
    return {"x0": (block.min[0], y), "x1": (block.max[0], y),
            "y0": (x, block.min[1]), "y1": (x, block.max[1])}[side]


# ------------------------------------------------------------------ sprue
def place_sprue(info: BodyInfo, block: BBox, params: MoldParams, parting_z: Optional[float]) -> Tuple[Optional[SprueSpec], List[str]]:
    if not params.sprue_enabled:
        return None, []
    warnings: List[str] = []
    if info.high_points:
        hx, hy, hz = info.high_points[0]
    else:
        cx, cy, _ = info.bbox.center
        hx, hy, hz = cx, cy, info.bbox.max[2]
        warnings.append("No cavity high point available; sprue assumed at the bbox centre/top.")
    d, fd = params.sprue_d_mm, max(params.funnel_d_mm, params.sprue_d_mm)

    if params.sprue_location == "edge":
        z = parting_z if parting_z is not None else hz
        fx, fy = _nearest_face_point(block, hx, hy)
        return SprueSpec("edge", hx, hy, z, z, d, fd, 0.0, edge_from=(fx, fy)), warnings

    top = block.max[2]
    funnel_h = min((fd - d) / 2.0, max(top - hz - 1.0, 0.0))
    if top - hz < d / 2:
        warnings.append("Material above the cavity is very thin at the sprue; increase floor/top thickness.")
    return SprueSpec("top", hx, hy, hz - 0.5, top, d, fd, funnel_h), warnings


# ------------------------------------------------------------------ vents
def place_vents(
    info: BodyInfo, block: BBox, params: MoldParams, sprue: Optional[SprueSpec],
    parting_z: Optional[float], max_vents: int = 8,
) -> Tuple[List[VentSpec], List[str]]:
    if not params.vents_auto:
        return [], []
    vd = params.vent_d_mm
    vents: List[VentSpec] = []
    warnings: List[str] = []
    top_sprue = sprue is not None and sprue.location == "top"
    for hx, hy, hz in info.high_points:
        if len(vents) >= max_vents:
            warnings.append(f"More than {max_vents} air traps found; only the highest {max_vents} are vented.")
            break
        if top_sprue and math.hypot(hx - sprue.x, hy - sprue.y) <= sprue.d_mm / 2 + vd / 2:  # type: ignore[union-attr]
            continue  # the sprue reaches this high point
        if any(math.hypot(hx - v.x, hy - v.y) < max(3 * vd, 2.0) for v in vents):
            continue
        if parting_z is not None and abs(hz - parting_z) <= vd:
            fx, fy = _nearest_face_point(block, hx, hy)
            vents.append(VentSpec("parting_channel", hx, hy, parting_z, parting_z, vd, edge_to=(fx, fy)))
        else:
            vents.append(VentSpec("riser", hx, hy, hz - 0.5, block.max[2], vd))
    return vents, warnings


# ------------------------------------------------------------------- keys
def place_keys(
    block: BBox, fp: Footprint, params: MoldParams, wall: float, obstacles: Sequence[Obstacle]
) -> Tuple[List[KeySpec], List[str]]:
    if params.key_type == "none":
        return [], []
    d = params.key_d_mm
    r = d / 2.0
    edge = r + KEY_EDGE_MARGIN
    inset = max(wall / 2.0, d)
    (x0, y0, _), (x1, y1, _) = block.min, block.max
    bounds = (x0 + edge, y0 + edge, x1 - edge, y1 - edge)
    targets = [(x0 + inset, y0 + inset), (x1 - inset, y1 - inset)]
    if params.key_count == 4:
        targets += [(x1 - inset, y0 + inset), (x0 + inset, y1 - inset)]
    warnings: List[str] = []
    placed: List[KeySpec] = []

    def accept(x: float, y: float) -> bool:
        if not fp.is_clear(x, y, r + CAVITY_KEY_EXTRA):
            return False
        if any(o.clearance(x, y) < r + FEATURE_GAP for o in obstacles):
            return False
        return all(math.hypot(x - k.x, y - k.y) >= 2 * d for k in placed)

    for t in targets:
        t = (min(max(t[0], bounds[0]), bounds[2]), min(max(t[1], bounds[1]), bounds[3]))
        spot = _nearest_valid(t, bounds, accept, step=max(1.0, d / 4.0))
        if spot is None:
            warnings.append(f"Could not place a {d:g} mm registration key near ({t[0]:.0f}, {t[1]:.0f}); "
                            "increase wall thickness or reduce key diameter.")
        else:
            placed.append(KeySpec(spot[0], spot[1], d, params.key_type))
    if len(placed) < 2:
        warnings.append("Fewer than 2 registration keys fit: the mold halves will NOT be reliably aligned.")
    return placed, warnings


# ------------------------------------------------------------------ bolts
def place_bolts(
    block: BBox, fp: Footprint, params: MoldParams, wall: float, obstacles: Sequence[Obstacle]
) -> Tuple[List[BoltSpec], List[str]]:
    if not params.bolts_enabled:
        return [], []
    hw = HARDWARE[params.bolt_size]
    r_hole = hw.hole_d / 2.0
    r_big = max(hw.cbore_d if params.bolt_counterbore else hw.hole_d,
                hw.nut_corner_d if params.bolt_nut_trap else hw.hole_d) / 2.0
    (x0, y0, _), (x1, y1, _) = block.min, block.max
    long_is_u = (x1 - x0) >= (y1 - y0)
    band = max(wall / 2.0, r_big + BOLT_EDGE_MARGIN)
    warnings: List[str] = []
    if band + r_hole + CAVITY_BOLT_EXTRA > wall + 1e-9:
        warnings.append(f"Wall ({wall:g} mm) is thin for {params.bolt_size} bolts; "
                        f"{band + r_hole + CAVITY_BOLT_EXTRA:.1f} mm or more is advised.")

    n_total = params.bolt_count
    per_line = [n_total - n_total // 2, n_total // 2]  # odd counts: extra bolt on the first line
    lo, hi = ((x0, x1) if long_is_u else (y0, y1))
    lo, hi = lo + r_big + BOLT_EDGE_MARGIN, hi - r_big - BOLT_EDGE_MARGIN
    lines = ((y0 + band, y1 - band) if long_is_u else (x0 + band, x1 - band))
    placed: List[BoltSpec] = []

    def xy(s: float, line: float) -> Tuple[float, float]:
        return (s, line) if long_is_u else (line, s)

    for line, n in zip(lines, per_line):
        for i in range(n):
            t = lo + (hi - lo) * (i + 0.5) / n

            def ok(s: float) -> bool:
                x, y = xy(s, line)
                if not fp.is_clear(x, y, r_hole + CAVITY_BOLT_EXTRA):
                    return False
                if any(o.clearance(x, y) < r_big + FEATURE_GAP for o in obstacles):
                    return False
                return all(math.hypot(x - b.x, y - b.y) >= 2 * r_big + FEATURE_GAP for b in placed)

            if hi < lo:
                s = None
            else:
                steps = int((hi - lo) / 1.0) + 1
                order = sorted((lo + k for k in range(steps + 1) if lo + k <= hi), key=lambda v: abs(v - t))
                s = next((v for v in order if ok(v)), None)
            if s is None:
                warnings.append(f"Could not place bolt {len(placed) + 1} ({params.bolt_size}) clear of the cavity/keys.")
                continue
            x, y = xy(s, line)
            placed.append(BoltSpec(x, y, hw.hole_d, hw.cbore_d if params.bolt_counterbore else 0.0,
                                   hw.cbore_depth if params.bolt_counterbore else 0.0,
                                   hw.nut_af if params.bolt_nut_trap else 0.0,
                                   hw.nut_depth if params.bolt_nut_trap else 0.0))
    if len(placed) < 2:
        warnings.append("Fewer than 2 bolts fit: clamping will be unreliable. Increase wall thickness.")
    return placed, warnings


# ----------------------------------------------------------------- driver
def obstacles_for(sprue: Optional[SprueSpec], vents: Sequence[VentSpec]) -> List[Obstacle]:
    obs: List[Obstacle] = []
    if sprue is not None:
        if sprue.location == "top":
            obs.append(Obstacle(sprue.x, sprue.y, sprue.x, sprue.y, sprue.funnel_d_mm / 2 + FEATURE_GAP))
        elif sprue.edge_from is not None:
            obs.append(Obstacle(sprue.edge_from[0], sprue.edge_from[1], sprue.x, sprue.y, sprue.d_mm / 2 + FEATURE_GAP))
    for v in vents:
        if v.edge_to is not None:
            obs.append(Obstacle(v.edge_to[0], v.edge_to[1], v.x, v.y, v.d_mm / 2 + FEATURE_GAP))
        else:
            obs.append(Obstacle(v.x, v.y, v.x, v.y, v.d_mm / 2 + FEATURE_GAP))
    return obs


def plan_features(
    info: BodyInfo, block: BBox, params: MoldParams, wall: float, parting_z: Optional[float],
    with_keys: bool = True, with_bolts: bool = True, with_pour: bool = True,
) -> Features:
    """Place sprue, vents, keys and bolts for a split mold. `info` must already be shrink-scaled."""
    out = Features()
    fp = footprint_of(info)
    if with_pour:
        out.sprue, w = place_sprue(info, block, params, parting_z)
        out.warnings += w
        out.vents, w = place_vents(info, block, params, out.sprue, parting_z)
        out.warnings += w
        if params.vents_mandatory and not out.vents and not params.vents_auto:
            out.warnings.append("This material needs vents but vents are off.")
    obs = obstacles_for(out.sprue, out.vents)
    if with_keys:
        out.keys, w = place_keys(block, fp, params, wall, obs)
        out.warnings += w
        obs += [Obstacle(k.x, k.y, k.x, k.y, k.d_mm / 2 + FEATURE_GAP) for k in out.keys]
    if with_bolts:
        out.bolts, w = place_bolts(block, fp, params, wall, obs)
        out.warnings += w
    return out
