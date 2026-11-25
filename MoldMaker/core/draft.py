"""Draft-angle analysis for an open (single-pull) mold (pure).

The adapter samples the master's faces and reports, per sample, the face area,
the outward unit normal's component along the pull direction (n.w) and the
sample's height along w. A face releases when it leans outward as it rises:

    draft angle = asin(-n.w)    >= 0 releases, < 0 is an undercut

Faces pointing up at the top plane are the open back of the part: they are
ignored. An upward face lower than the top has mold material above it, so it
counts as an undercut (the part needs a flat back for an open block).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Sequence, Tuple

Sample = Tuple[float, float, float]  # (area_mm2, normal_dot_pull, height_w_mm)

FLOOR_LIKE_DEG = 80.0  # faces steeper than this are floors, not walls (excluded from "min draft")


@dataclass(frozen=True)
class DraftReport:
    total_area: float
    undercut_area: float
    insufficient_area: float
    min_wall_draft_deg: float  # smallest draft among wall-like, non-undercut faces (nan if none)

    @property
    def undercut_frac(self) -> float:
        return self.undercut_area / self.total_area if self.total_area else 0.0

    @property
    def insufficient_frac(self) -> float:
        return self.insufficient_area / self.total_area if self.total_area else 0.0


def draft_angle_deg(n_dot_w: float) -> float:
    return math.degrees(math.asin(max(-1.0, min(1.0, -n_dot_w))))


def analyze(samples: Sequence[Sample], required_deg: float, tol_deg: float = 0.1, top_tol_mm: float = 0.2,
            buck: bool = False) -> DraftReport:
    """Draft analysis for a cavity (default) or a male buck (buck=True).

    A buck is formed over from above and released upward, so its faces must lean the other way:
    the draft angle is asin(+n.w) and the flat base (looking down, at the bottom) is ignored.
    """
    if not samples:
        return DraftReport(0.0, 0.0, 0.0, math.nan)
    if buck:
        z_bot = min(s[2] for s in samples)
        # flip the normal so the cavity maths applies; drop the base; nothing is an "open back"
        samples = [(a, -n, -1e9) for a, n, z in samples if not (n < -0.99 and z <= z_bot + top_tol_mm)]
        if not samples:
            return DraftReport(0.0, 0.0, 0.0, math.nan)
        z_top = 1e9
    else:
        z_top = max(s[2] for s in samples)
    total = under = insufficient = 0.0
    min_wall = math.inf
    for area, ndw, z in samples:
        if ndw > 0.99 and z >= z_top - top_tol_mm:
            continue  # the open back
        total += area
        angle = draft_angle_deg(ndw)
        if angle < -tol_deg:
            under += area
            continue
        if angle < required_deg - tol_deg:
            insufficient += area
        if angle < FLOOR_LIKE_DEG:
            min_wall = min(min_wall, angle)
    return DraftReport(total, under, insufficient, min_wall if min_wall is not math.inf else math.nan)


def analyze_two_sided(samples: Sequence[Sample], parting_z: float, required_deg: float,
                      tol_deg: float = 0.1, top_tol_mm: float = 0.2) -> DraftReport:
    """Draft analysis for a core/cavity mold split at parting_z.

    Faces at or below the parting plane release by pulling the lower half down, faces above by pulling
    the upper half up. Mirroring the upper samples about the plane (normal and height) lets the
    single-pull analysis handle both; faces lying in the parting plane are ignored.
    """
    mirrored: List[Sample] = []
    for area, ndw, z in samples:
        if z >= parting_z:
            mirrored.append((area, -ndw, 2.0 * parting_z - z))
        else:
            mirrored.append((area, ndw, z))
    if not mirrored:
        return DraftReport(0.0, 0.0, 0.0, math.nan)
    # a flat face on the plane would count as an undercut: lift the "open back" to the plane
    return analyze([(a, n, z if abs(z - parting_z) > top_tol_mm else parting_z) for a, n, z in mirrored],
                   required_deg, tol_deg, top_tol_mm)


def warnings_for(report: DraftReport, required_deg: float) -> List[str]:
    out: List[str] = []
    if report.total_area <= 0:
        return out
    if report.undercut_frac > 0.005:
        out.append(f"{report.undercut_frac:.0%} of the part surface is an undercut for this pull direction "
                   "(faces looking away from the opening, or a back that is not flat). The casting may lock in the mold.")
    if report.insufficient_frac > 0.005 and required_deg > 0:
        worst = "" if math.isnan(report.min_wall_draft_deg) else f" (smallest {report.min_wall_draft_deg:.1f} deg)"
        out.append(f"{report.insufficient_frac:.0%} of the surface has less than the requested {required_deg:g} deg draft{worst}.")
    return out
