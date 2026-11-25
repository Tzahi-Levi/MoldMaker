"""Pure data model (no adsk). All lengths in mm, angles in degrees.

Coordinate convention: plans live in a *pull frame*: local +w is the pull
direction ("up"), u/v span the plane perpendicular to it. Frames are
right-handed axis permutations of world XYZ, so world<->local is exact.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional, Sequence, Tuple

Vec3 = Tuple[float, float, float]
# One sample ray along the pull axis: (u, v, ((w_enter, w_exit), ...)) solid intervals.
Ray = Tuple[float, float, Tuple[Tuple[float, float], ...]]

MOLD_TYPES = (
    "silicone_box", "two_part", "open_block", "brush_on_mother",
    "slip_cast_case", "vacuum_buck", "core_cavity",
)
MOLD_TYPE_LABELS = {
    "silicone_box": "Silicone mold box",
    "two_part": "Two-part rigid mold",
    "open_block": "Open block mold",
    "brush_on_mother": "Brush-on silicone + mother mold",
    "slip_cast_case": "Slip-cast plaster case",
    "vacuum_buck": "Vacuum-forming buck",
    "core_cavity": "Core/cavity (injection/compression)",
}
# Mold types whose walls are a printed shell (use `wall_printed_mm` preset if present).
PRINTED_SHELL_TYPES = ("two_part", "open_block", "core_cavity")

PULL_DIRECTIONS = ("+Z", "-Z", "+X", "-X", "+Y", "-Y")
KEY_TYPES = ("sphere", "cone", "none")
BOLT_SIZES = ("M3", "M4", "M5")
SPRUE_LOCATIONS = ("top", "edge")
PARTING_MODES = ("auto", "manual")


# ----------------------------------------------------------------- vectors
def vdot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def vcross(a: Vec3, b: Vec3) -> Vec3:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


@dataclass(frozen=True)
class BBox:
    min: Vec3
    max: Vec3

    @property
    def size(self) -> Vec3:
        return tuple(b - a for a, b in zip(self.min, self.max))  # type: ignore[return-value]

    @property
    def center(self) -> Vec3:
        return tuple((a + b) / 2.0 for a, b in zip(self.min, self.max))  # type: ignore[return-value]

    @property
    def volume(self) -> float:
        sx, sy, sz = self.size
        return sx * sy * sz


# ------------------------------------------------------------------ frames
@dataclass(frozen=True)
class PullFrame:
    pull: str
    u: Vec3
    v: Vec3
    w: Vec3

    def to_local(self, p: Vec3) -> Vec3:
        return (vdot(p, self.u), vdot(p, self.v), vdot(p, self.w))

    def to_world(self, q: Vec3) -> Vec3:
        return tuple(  # type: ignore[return-value]
            q[0] * self.u[i] + q[1] * self.v[i] + q[2] * self.w[i] for i in range(3)
        )

    def bbox_to_local(self, mn: Vec3, mx: Vec3) -> BBox:
        corners = [(x, y, z) for x in (mn[0], mx[0]) for y in (mn[1], mx[1]) for z in (mn[2], mx[2])]
        loc = [self.to_local(c) for c in corners]
        lo = tuple(min(c[i] for c in loc) for i in range(3))
        hi = tuple(max(c[i] for c in loc) for i in range(3))
        return BBox(lo, hi)  # type: ignore[arg-type]

    def local_factors(self, world_xyz: Vec3) -> Vec3:
        """Map per-world-axis scale factors onto the local (u, v, w) axes."""
        return tuple(  # type: ignore[return-value]
            sum(abs(axis[i]) * world_xyz[i] for i in range(3)) for axis in (self.u, self.v, self.w)
        )


_FRAMES: Dict[str, PullFrame] = {
    "+Z": PullFrame("+Z", (1, 0, 0), (0, 1, 0), (0, 0, 1)),
    "-Z": PullFrame("-Z", (1, 0, 0), (0, -1, 0), (0, 0, -1)),
    "+X": PullFrame("+X", (0, 1, 0), (0, 0, 1), (1, 0, 0)),
    "-X": PullFrame("-X", (0, 1, 0), (0, 0, -1), (-1, 0, 0)),
    "+Y": PullFrame("+Y", (0, 0, 1), (1, 0, 0), (0, 1, 0)),
    "-Y": PullFrame("-Y", (0, 0, 1), (-1, 0, 0), (0, -1, 0)),
}


def frame_for(pull_dir: str) -> PullFrame:
    try:
        return _FRAMES[pull_dir]
    except KeyError:
        raise ValueError(f"Unknown pull direction {pull_dir!r}; expected one of {PULL_DIRECTIONS}")


# -------------------------------------------------------------- footprints
class Footprint:
    """2D projection of the cavity onto the parting plane (u, v), in mm."""

    def is_clear(self, x: float, y: float, margin: float) -> bool:  # pragma: no cover - interface
        raise NotImplementedError

    def contains(self, x: float, y: float) -> bool:  # pragma: no cover - interface
        raise NotImplementedError

    def nearest_inside(self, x: float, y: float) -> Tuple[float, float]:  # pragma: no cover
        raise NotImplementedError

    def scaled(self, center: Tuple[float, float], fu: float, fv: float) -> "Footprint":  # pragma: no cover
        raise NotImplementedError

    def grown(self, r: float) -> "Footprint":  # pragma: no cover
        """The footprint offset outward by r mm."""
        raise NotImplementedError


@dataclass(frozen=True)
class RectFootprint(Footprint):
    x0: float
    y0: float
    x1: float
    y1: float

    def distance(self, x: float, y: float) -> float:
        dx = max(self.x0 - x, 0.0, x - self.x1)
        dy = max(self.y0 - y, 0.0, y - self.y1)
        return math.hypot(dx, dy)

    def is_clear(self, x: float, y: float, margin: float) -> bool:
        return self.distance(x, y) >= margin - 1e-9

    def contains(self, x: float, y: float) -> bool:
        return self.x0 <= x <= self.x1 and self.y0 <= y <= self.y1

    def nearest_inside(self, x: float, y: float) -> Tuple[float, float]:
        return (min(max(x, self.x0), self.x1), min(max(y, self.y0), self.y1))

    def scaled(self, center, fu, fv) -> "RectFootprint":
        cx, cy = center
        xs = sorted((cx + (self.x0 - cx) * fu, cx + (self.x1 - cx) * fu))
        ys = sorted((cy + (self.y0 - cy) * fv, cy + (self.y1 - cy) * fv))
        return RectFootprint(xs[0], ys[0], xs[1], ys[1])

    def grown(self, r: float) -> "RectFootprint":
        return RectFootprint(self.x0 - r, self.y0 - r, self.x1 + r, self.y1 + r)


class PointFootprint(Footprint):
    """Footprint sampled from rays: each point stands for a disc of `radius`."""

    def __init__(self, points: Sequence[Tuple[float, float]], radius: float):
        self.points = tuple(points)
        self.radius = float(radius)
        self.cell = max(self.radius * 1.4, 0.5)
        self._grid: Dict[Tuple[int, int], List[Tuple[float, float]]] = {}
        for p in self.points:
            self._grid.setdefault(self._key(p[0], p[1]), []).append(p)
        if self.points:
            self._bounds = (
                min(p[0] for p in self.points) - self.radius, min(p[1] for p in self.points) - self.radius,
                max(p[0] for p in self.points) + self.radius, max(p[1] for p in self.points) + self.radius,
            )
        else:
            self._bounds = (0.0, 0.0, 0.0, 0.0)

    def _key(self, x: float, y: float) -> Tuple[int, int]:
        return (math.floor(x / self.cell), math.floor(y / self.cell))

    def is_clear(self, x: float, y: float, margin: float) -> bool:
        if not self.points:
            return True
        x0, y0, x1, y1 = self._bounds
        if x < x0 - margin or x > x1 + margin or y < y0 - margin or y > y1 + margin:
            return True
        reach = margin + self.radius
        n = int(math.ceil(reach / self.cell))
        kx, ky = self._key(x, y)
        for i in range(kx - n, kx + n + 1):
            for j in range(ky - n, ky + n + 1):
                for px, py in self._grid.get((i, j), ()):
                    if math.hypot(px - x, py - y) < reach - 1e-9:
                        return False
        return True

    def contains(self, x: float, y: float) -> bool:
        return not self.is_clear(x, y, 0.0)

    def nearest_inside(self, x: float, y: float) -> Tuple[float, float]:
        if not self.points:
            return (x, y)
        return min(self.points, key=lambda p: (p[0] - x) ** 2 + (p[1] - y) ** 2)

    def scaled(self, center, fu, fv) -> "PointFootprint":
        cx, cy = center
        pts = [(cx + (px - cx) * fu, cy + (py - cy) * fv) for px, py in self.points]
        return PointFootprint(pts, self.radius * max(fu, fv))

    def grown(self, r: float) -> "PointFootprint":
        return PointFootprint(self.points, self.radius + r)


# --------------------------------------------------------------- body info
@dataclass(frozen=True)
class BodyInfo:
    """What the planner needs to know about the (unscaled) master, in the pull frame."""

    name: str
    bbox: BBox
    volume_mm3: float
    rays: Tuple[Ray, ...] = ()
    ray_spacing_mm: float = 0.0
    high_points: Tuple[Vec3, ...] = ()  # local maxima along w, highest first
    footprint: Optional[Footprint] = None
    silhouette_z: Tuple[float, ...] = ()  # heights (w) along the silhouette loop, from a Silhouette Split probe

    def scaled(self, fu: float, fv: float, fw: float) -> "BodyInfo":
        """Scale about the bbox centre (matches the ScaleFeature in the adapter)."""
        cu, cv, cw = self.bbox.center

        def sc(p: Vec3) -> Vec3:
            return (cu + (p[0] - cu) * fu, cv + (p[1] - cv) * fv, cw + (p[2] - cw) * fw)

        lo, hi = sc(self.bbox.min), sc(self.bbox.max)
        bbox = BBox(tuple(min(a, b) for a, b in zip(lo, hi)), tuple(max(a, b) for a, b in zip(lo, hi)))  # type: ignore[arg-type]
        rays = tuple(
            (cu + (x - cu) * fu, cv + (y - cv) * fv,
             tuple((cw + (a - cw) * fw, cw + (b - cw) * fw) for a, b in iv))
            for x, y, iv in self.rays
        )
        return replace(
            self,
            bbox=bbox,
            volume_mm3=self.volume_mm3 * fu * fv * fw,
            rays=rays,
            ray_spacing_mm=self.ray_spacing_mm * max(fu, fv),
            high_points=tuple(sc(p) for p in self.high_points),
            footprint=self.footprint.scaled((cu, cv), fu, fv) if self.footprint else None,
            silhouette_z=tuple(cw + (z - cw) * fw for z in self.silhouette_z),
        )


# ------------------------------------------------------------------ params
@dataclass
class MoldParams:
    casting_id: str
    mold_type: str
    mold_material_id: str
    wall_mm: float = 10.0
    floor_top_mm: float = 10.0
    pull_dir: str = "+Z"
    parting_mode: str = "auto"
    parting_offset_mm: float = 0.0  # manual: offset of the parting plane from bbox mid-height, + toward pull
    draft_deg: float = 0.0
    shrink_pct: float = 0.0
    shrink_xyz_pct: Optional[Tuple[float, float, float]] = None  # world X, Y, Z; overrides shrink_pct
    key_type: str = "sphere"
    key_count: int = 4
    key_d_mm: float = 6.0
    key_clearance_mm: float = 0.3
    key_chamfer_mm: float = 0.5
    sprue_enabled: bool = True
    sprue_location: str = "top"
    sprue_d_mm: float = 6.0
    funnel_d_mm: float = 12.0
    vents_auto: bool = True
    vent_d_mm: float = 1.5
    bolts_enabled: bool = True
    bolt_count: int = 4
    bolt_size: str = "M4"
    bolt_counterbore: bool = True
    bolt_nut_trap: bool = True
    box_wall_mm: float = 2.4          # silicone_box printed wall
    silicone_two_part: bool = False   # silicone_box: add parting bed variant
    silicone_density_g_cc: float = 1.08
    vents_mandatory: bool = False
    skin_mm: float = 4.0              # brush_on_mother: silicone skin thickness
    shell_mm: float = 4.0             # brush_on_mother: mother shell; vacuum_buck: hollow wall
    flange_w_mm: float = 15.0         # brush_on_mother / vacuum_buck flange width
    plaster_thickness_mm: float = 25.0  # slip_cast_case
    case_wall_mm: float = 2.4         # slip_cast_case printed case wall
    slip_well_h_mm: float = 25.0      # slip_cast_case reservoir height above the cavity
    slip_well_d_mm: float = 0.0       # 0 = automatic
    plaster_slurry_density_g_cc: float = 1.57
    plaster_to_water: Tuple[float, float] = (10.0, 7.0)
    vent_hole_d_mm: float = 0.8       # vacuum_buck
    leader_pin_d_mm: float = 6.0      # core_cavity leader pins
    insert_step_mm: float = 5.0       # core_cavity: insert plan size is rounded up to a multiple (0 = off)
    gate_d_mm: float = 1.5            # core_cavity: gate neck between runner and cavity
    vent_slot_depth_mm: float = 0.05  # core_cavity: parting-line vent slot depth
    vent_slot_w_mm: float = 4.0       # core_cavity: parting-line vent slot width
    parting_silhouette: bool = False  # core_cavity: use a Silhouette Split probe to place the parting plane
    apply_draft: bool = False         # core_cavity: try to apply the draft angle to the cavity walls
    lay_flat: bool = True
    create_user_params: bool = True
    export_stl: bool = False
    export_dir: str = ""
    mesh_refinement: str = "medium"

    def shrink_factors_world(self) -> Vec3:
        if self.shrink_xyz_pct is not None:
            return tuple(1.0 + s / 100.0 for s in self.shrink_xyz_pct)  # type: ignore[return-value]
        f = 1.0 + self.shrink_pct / 100.0
        return (f, f, f)

    def validate(self) -> List[str]:
        """Return human-readable problems; empty list means OK."""
        p: List[str] = []
        if self.mold_type not in MOLD_TYPES:
            p.append(f"Unknown mold type {self.mold_type!r}.")
        if self.pull_dir not in PULL_DIRECTIONS:
            p.append(f"Unknown pull direction {self.pull_dir!r}.")
        if self.parting_mode not in PARTING_MODES:
            p.append(f"Unknown parting mode {self.parting_mode!r}.")
        if self.wall_mm <= 0:
            p.append("Wall thickness must be greater than 0.")
        if self.floor_top_mm <= 0:
            p.append("Floor/top thickness must be greater than 0.")
        if any(f <= 0.5 or f >= 2.0 for f in self.shrink_factors_world()):
            p.append("Shrinkage must be between -50 % and +100 %.")
        if self.key_type not in KEY_TYPES:
            p.append(f"Unknown key type {self.key_type!r}.")
        if self.key_type != "none":
            if self.key_count not in (2, 4):
                p.append("Key count must be 2 or 4.")
            if self.key_d_mm <= 0 or self.key_clearance_mm < 0 or self.key_chamfer_mm < 0:
                p.append("Key diameter must be > 0; clearance and chamfer must be >= 0.")
        if self.sprue_enabled:
            if self.sprue_location not in SPRUE_LOCATIONS:
                p.append(f"Unknown sprue location {self.sprue_location!r}.")
            if self.sprue_d_mm <= 0 or self.funnel_d_mm < self.sprue_d_mm:
                p.append("Sprue diameter must be > 0 and the funnel diameter must be >= sprue diameter.")
        if self.vents_auto and self.vent_d_mm <= 0:
            p.append("Vent diameter must be greater than 0.")
        if self.vents_mandatory and not self.vents_auto and self.mold_type in ("two_part", "silicone_box", "core_cavity"):
            p.append("This casting material requires vents; turn vents on.")
        if self.mold_type == "brush_on_mother" and min(self.skin_mm, self.shell_mm, self.flange_w_mm) <= 0:
            p.append("Skin, shell and flange width must be greater than 0.")
        if self.mold_type == "slip_cast_case" and min(self.plaster_thickness_mm, self.case_wall_mm, self.slip_well_h_mm) <= 0:
            p.append("Plaster thickness, case wall and slip well height must be greater than 0.")
        if self.mold_type == "slip_cast_case" and self.slip_well_d_mm < 0:
            p.append("Slip well diameter cannot be negative (use 0 for automatic).")
        if self.mold_type == "core_cavity":
            if min(self.leader_pin_d_mm, self.gate_d_mm, self.vent_slot_w_mm) <= 0 or self.vent_slot_depth_mm <= 0:
                p.append("Leader pin, gate and vent slot sizes must be greater than 0.")
            if self.insert_step_mm < 0:
                p.append("Insert size step cannot be negative (use 0 for no rounding).")
            if self.draft_deg < 0 or self.draft_deg > 15:
                p.append("Draft angle must be between 0 and 15 degrees.")
        if self.mold_type == "vacuum_buck" and (self.shell_mm <= 0 or self.flange_w_mm < 0 or self.vent_hole_d_mm <= 0):
            p.append("Buck shell and vent hole diameter must be greater than 0; flange width cannot be negative.")
        if self.bolts_enabled:
            if self.bolt_size not in BOLT_SIZES:
                p.append(f"Unknown bolt size {self.bolt_size!r}.")
            if self.bolt_count < 2:
                p.append("Bolt count must be at least 2.")
        return p


# -------------------------------------------------------------- plan specs
@dataclass(frozen=True)
class KeySpec:
    x: float
    y: float
    d_mm: float
    kind: str  # sphere | cone


@dataclass(frozen=True)
class SprueSpec:
    location: str  # top | edge
    x: float
    y: float
    z_from: float  # cavity-side end (a little inside the cavity)
    z_to: float    # outer end
    d_mm: float
    funnel_d_mm: float
    funnel_h_mm: float
    # edge location only: the channel runs in the parting plane from the outer face to (x, y)
    edge_from: Optional[Tuple[float, float]] = None


@dataclass(frozen=True)
class VentSpec:
    kind: str  # riser | parting_channel | buck_hole | slot (flat parting-line slot, d_mm = width)
    x: float
    y: float
    z_from: float
    z_to: float
    d_mm: float
    edge_to: Optional[Tuple[float, float]] = None  # parting_channel: outer-face end


@dataclass(frozen=True)
class BoltSpec:
    x: float
    y: float
    hole_d_mm: float
    cbore_d_mm: float
    cbore_depth_mm: float
    nut_af_mm: float
    nut_depth_mm: float


@dataclass(frozen=True)
class PostSpec:
    x: float
    y: float
    d_mm: float
    z_from: float
    z_to: float


@dataclass(frozen=True)
class PartSpec:
    id: str
    name: str
    role: str
    z_range: Tuple[float, float]


@dataclass
class MoldPlan:
    mold_type: str
    params: MoldParams
    body_name: str
    frame: PullFrame
    cavity_bbox: BBox
    block: BBox
    parting_z: Optional[float] = None
    parts: List[PartSpec] = field(default_factory=list)
    keys: List[KeySpec] = field(default_factory=list)
    sprue: Optional[SprueSpec] = None
    vents: List[VentSpec] = field(default_factory=list)
    bolts: List[BoltSpec] = field(default_factory=list)
    posts: List[PostSpec] = field(default_factory=list)
    inner_block: Optional[BBox] = None  # silicone_box: silicone volume bounds
    metrics: Dict[str, float] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    extras: Dict[str, Any] = field(default_factory=dict)  # strategy-specific numbers (offsets, flange, well...)

    @property
    def group_name(self) -> str:
        return f"MoldMaker - {MOLD_TYPE_LABELS.get(self.mold_type, self.mold_type)}"

    @property
    def component_name(self) -> str:
        return f"Mold - {self.body_name}"

    def summary(self) -> str:
        sx, sy, sz = self.block.size
        lines = [
            f"{self.group_name}",
            f"Output component: {self.component_name}",
            f"Block: {sx:.1f} x {sy:.1f} x {sz:.1f} mm (pull {self.params.pull_dir})",
        ]
        if self.parting_z is not None:
            lines.append(f"Parting height: {self.parting_z:.2f} mm (local w)")
        lines.append("Parts: " + (", ".join(p.name for p in self.parts) or "-"))
        lines.append(f"Keys: {len(self.keys)}   Vents: {len(self.vents)}   Bolts: {len(self.bolts)}   "
                     f"Sprue: {'yes (' + self.sprue.location + ')' if self.sprue else 'no'}")
        for k, v in self.metrics.items():
            lines.append(f"{k}: {v:.1f}")
        if self.warnings:
            lines.append("")
            lines.append("Warnings:")
            lines.extend(f"  - {w}" for w in self.warnings)
        return "\n".join(lines)
