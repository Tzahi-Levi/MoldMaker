"""Parting-height scoring and ray-sample analysis (pure).

The adapter samples a grid of rays along the pull axis (BRepBody.pointContainment
or face intersections) and hands us, per ray, the solid intervals along w.
"""
from __future__ import annotations

import math
from dataclasses import replace
from typing import Dict, List, Optional, Sequence, Tuple

from .model import BodyInfo, Footprint, PointFootprint, Ray, Vec3


def hit_rays(rays: Sequence[Ray]) -> List[Ray]:
    return [r for r in rays if r[2]]


def coverage_at(rays: Sequence[Ray], z: float) -> float:
    """Fraction of rays that hit the body whose solid contains height z.

    1.0 means the section at z equals the full silhouette: no undercut when the
    mold is split there. 'Widest section' == maximum coverage.
    """
    hits = hit_rays(rays)
    if not hits:
        return 0.0
    covered = sum(1 for _, _, iv in hits if any(a - 1e-9 <= z <= b + 1e-9 for a, b in iv))
    return covered / len(hits)


def score_heights(rays: Sequence[Ray], levels: Sequence[float]) -> List[float]:
    return [coverage_at(rays, z) for z in levels]


def choose_parting_height(
    rays: Sequence[Ray], z_lo: float, z_hi: float, samples: int = 41, edge_margin_frac: float = 0.02
) -> Tuple[float, float]:
    """Pick the parting height; returns (z, coverage score).

    Maximises silhouette coverage; among (near-)ties picks the height closest to
    the middle of the part so both mold halves stay balanced.
    """
    if z_hi <= z_lo:
        raise ValueError("Part has no height along the pull axis.")
    span = z_hi - z_lo
    lo, hi = z_lo + span * edge_margin_frac, z_hi - span * edge_margin_frac
    n = max(samples, 3)
    levels = [lo + (hi - lo) * i / (n - 1) for i in range(n)]
    scores = score_heights(rays, levels)
    best = max(scores)
    mid = (z_lo + z_hi) / 2.0
    cands = [z for z, s in zip(levels, scores) if s >= best - 1e-9]
    z = min(cands, key=lambda c: abs(c - mid))
    return z, best


def height_from_silhouette(zs: Sequence[float], z0: float, z1: float, tol_mm: float = 0.5) -> Tuple[Optional[float], float]:
    """Planar parting height from the silhouette loop's heights: (median clamped inside the part, max deviation).

    Returns (None, 0) when there is no usable loop.
    """
    pts = sorted(z for z in zs if z0 - 1e-6 <= z <= z1 + 1e-6)
    if not pts:
        return None, 0.0
    mid = pts[len(pts) // 2] if len(pts) % 2 else 0.5 * (pts[len(pts) // 2 - 1] + pts[len(pts) // 2])
    mid = min(max(mid, z0 + 0.1), z1 - 0.1)
    return mid, max(abs(z - mid) for z in pts)


def footprint_from_rays(rays: Sequence[Ray], spacing: float) -> Optional[Footprint]:
    pts = [(x, y) for x, y, iv in rays if iv]
    if not pts:
        return None
    return PointFootprint(pts, spacing * 0.6)


def high_points_from_rays(rays: Sequence[Ray], max_points: int = 8) -> List[Vec3]:
    """Local maxima of the top-surface height field, highest first.

    Equal-height plateaus collapse to one point (their member nearest the centroid).
    """
    top: Dict[Tuple[float, float], float] = {(x, y): max(b for _, b in iv) for x, y, iv in rays if iv}
    if not top:
        return []
    xs = sorted({k[0] for k in top})
    ys = sorted({k[1] for k in top})
    xi = {x: i for i, x in enumerate(xs)}
    yi = {y: j for j, y in enumerate(ys)}
    cell = {(xi[x], yi[y]): z for (x, y), z in top.items()}
    pos = {(xi[x], yi[y]): (x, y) for (x, y) in top}
    tol = 1e-6

    maxima = set()
    for (i, j), z in cell.items():
        ok = True
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                if (di or dj) and cell.get((i + di, j + dj), -math.inf) > z + tol:
                    ok = False
        if ok:
            maxima.add((i, j))

    comps: List[List[Tuple[int, int]]] = []
    unseen = set(maxima)
    while unseen:
        stack = [unseen.pop()]
        comp = []
        while stack:
            c = stack.pop()
            comp.append(c)
            for di in (-1, 0, 1):
                for dj in (-1, 0, 1):
                    n = (c[0] + di, c[1] + dj)
                    if n in unseen and abs(cell[n] - cell[c]) <= tol:
                        unseen.remove(n)
                        stack.append(n)
        comps.append(comp)

    out: List[Vec3] = []
    for comp in comps:
        cx = sum(pos[c][0] for c in comp) / len(comp)
        cy = sum(pos[c][1] for c in comp) / len(comp)
        rep = min(comp, key=lambda c: (pos[c][0] - cx) ** 2 + (pos[c][1] - cy) ** 2)
        out.append((pos[rep][0], pos[rep][1], cell[rep]))
    out.sort(key=lambda p: -p[2])
    return out[:max_points]


def low_points_from_rays(rays: Sequence[Ray], max_points: int = 8) -> List[Vec3]:
    """Pits in the top-surface height field (recesses where a vacuum-formed sheet traps air), lowest first.

    A pit is a connected plateau of equal height whose whole boundary is higher and fully inside
    the sampled footprint. Edges of the part and ramps never count.
    """
    tol = 1e-6
    top: Dict[Tuple[float, float], float] = {(x, y): max(b for _, b in iv) for x, y, iv in rays if iv}
    if not top:
        return []
    xi = {x: i for i, x in enumerate(sorted({k[0] for k in top}))}
    yi = {y: j for j, y in enumerate(sorted({k[1] for k in top}))}
    cell = {(xi[x], yi[y]): z for (x, y), z in top.items()}
    pos = {(xi[x], yi[y]): (x, y) for (x, y) in top}
    seen = set()
    out: List[Vec3] = []
    for start in sorted(cell):
        if start in seen:
            continue
        comp, stack = [], [start]
        seen.add(start)
        while stack:
            c = stack.pop()
            comp.append(c)
            for di in (-1, 0, 1):
                for dj in (-1, 0, 1):
                    n = (c[0] + di, c[1] + dj)
                    if n in cell and n not in seen and abs(cell[n] - cell[start]) <= tol:
                        seen.add(n)
                        stack.append(n)
        z = cell[start]
        members = set(comp)
        boundary_higher = False
        is_pit = True
        for c in comp:
            for di in (-1, 0, 1):
                for dj in (-1, 0, 1):
                    n = (c[0] + di, c[1] + dj)
                    if n in members:
                        continue
                    if n not in cell or cell[n] < z - tol:
                        is_pit = False
                    else:
                        boundary_higher = True
        if is_pit and boundary_higher:
            cx = sum(pos[c][0] for c in comp) / len(comp)
            cy = sum(pos[c][1] for c in comp) / len(comp)
            rep = min(comp, key=lambda c: (pos[c][0] - cx) ** 2 + (pos[c][1] - cy) ** 2)
            out.append((pos[rep][0], pos[rep][1], z))
    out.sort(key=lambda p: p[2])
    return out[:max_points]


def complete_info(info: BodyInfo) -> BodyInfo:
    """Fill footprint / high points from rays when the adapter did not supply them."""
    footprint = info.footprint
    high = info.high_points
    if info.rays:
        if footprint is None:
            footprint = footprint_from_rays(info.rays, info.ray_spacing_mm or 1.0)
        if not high:
            high = tuple(high_points_from_rays(info.rays))
    return replace(info, footprint=footprint, high_points=tuple(high))
