"""Synthetic bodies for tests: ray grids along local w (no Fusion)."""
import math

from MoldMaker.core.model import BBox, BodyInfo, MoldParams


def make_rays(span_fn, x_range, y_range, spacing):
    """span_fn(x, y) -> list[(w0, w1)] solid intervals."""
    rays = []
    nx = int(round((x_range[1] - x_range[0]) / spacing))
    ny = int(round((y_range[1] - y_range[0]) / spacing))
    for i in range(nx + 1):
        for j in range(ny + 1):
            x, y = x_range[0] + i * spacing, y_range[0] + j * spacing
            rays.append((x, y, tuple(span_fn(x, y))))
    return tuple(rays)


def sphere_info(r=15.0, spacing=1.0, name="sphere"):
    def spans(x, y):
        h2 = r * r - x * x - y * y
        return [(-math.sqrt(h2), math.sqrt(h2))] if h2 > 0 else []

    rays = make_rays(spans, (-r, r), (-r, r), spacing)
    return BodyInfo(name, BBox((-r, -r, -r), (r, r, r)), 4 / 3 * math.pi * r ** 3, rays, spacing)


def box_info(sx=40.0, sy=30.0, sz=20.0, spacing=1.0, name="box"):
    rays = make_rays(lambda x, y: [(0.0, sz)], (0, sx), (0, sy), spacing)
    return BodyInfo(name, BBox((0, 0, 0), (sx, sy, sz)), sx * sy * sz, rays, spacing)


def l_bracket_info(spacing=1.0, name="L"):
    """Footprint 40x20; 5 mm foot over the full footprint, upright at x<=5 rising to 40."""
    def spans(x, y):
        return [(0.0, 40.0)] if x <= 5 else [(0.0, 5.0)]

    rays = make_rays(spans, (0, 40), (0, 20), spacing)
    vol = 40 * 20 * 5 + 5 * 20 * 35
    return BodyInfo(name, BBox((0, 0, 0), (40, 20, 40)), vol, rays, spacing)


def mushroom_info(spacing=1.0):
    """Wide cap above a narrow stem: the cap holds the full silhouette."""
    def spans(x, y):
        r = math.hypot(x, y)
        if r <= 5:
            return [(0.0, 40.0)]
        if r <= 15:
            return [(30.0, 40.0)]
        return []

    rays = make_rays(spans, (-15, 15), (-15, 15), spacing)
    return BodyInfo("mushroom", BBox((-15, -15, 0), (15, 15, 40)),
                    math.pi * 25 * 30 + math.pi * 225 * 10, rays, spacing)


def params(**kw):
    base = dict(casting_id="cast_platinum_silicone", mold_type="two_part", mold_material_id="PLA")
    base.update(kw)
    return MoldParams(**base)
