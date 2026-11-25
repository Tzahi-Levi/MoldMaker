"""All Fusion (adsk) calls for geometry live here.

Geometry is built as temporary B-Rep bodies (TemporaryBRepManager) in the pull
frame, then committed into new components. The user's body is never modified.
Strategies call the primitives below with local pull-frame millimetres; this
module converts through core/units.py and the plan's PullFrame.
"""
from __future__ import annotations

import math
import os
import re
from typing import Any, List, Optional, Sequence, Tuple

import adsk.core
import adsk.fusion

from ..core import units, userparams
from ..core.model import BBox, BodyInfo, MoldPlan, PullFrame
from ..lib import fusion360utils as futil

LAY_FLAT_GAP_MM = 10.0


# --------------------------------------------------------------- body sampling
def sample_body(body: adsk.fusion.BRepBody, frame: PullFrame, n_levels: int = 40, ray_budget: int = 24000) -> BodyInfo:
    """Sample the master with rays along the pull axis (BRepBody.pointContainment).

    Returns solid intervals per ray (unscaled, local mm). The planner derives the
    parting height, footprint and high points from them.
    """
    bb = body.boundingBox
    lo = tuple(units.cm_to_mm(c) for c in (bb.minPoint.x, bb.minPoint.y, bb.minPoint.z))
    hi = tuple(units.cm_to_mm(c) for c in (bb.maxPoint.x, bb.maxPoint.y, bb.maxPoint.z))
    local = frame.bbox_to_local(lo, hi)
    (u0, v0, w0), (u1, v1, w1) = local.min, local.max
    su, sv, sw = u1 - u0, v1 - v0, w1 - w0

    inside_values = (adsk.fusion.PointContainment.PointInsidePointContainment,
                     adsk.fusion.PointContainment.PointOnPointContainment)

    def inside(u: float, v: float, w: float) -> bool:
        x, y, z = (units.mm_to_cm(c) for c in frame.to_world((u, v, w)))
        return body.pointContainment(adsk.core.Point3D.create(x, y, z)) in inside_values

    def edge(u: float, v: float, w_out: float, w_in: float, iterations: int = 7) -> float:
        """Bisect the surface between an outside and an inside sample."""
        for _ in range(iterations):
            mid = (w_out + w_in) / 2.0
            if inside(u, v, mid):
                w_in = mid
            else:
                w_out = mid
        return (w_out + w_in) / 2.0

    def lower_edge(u: float, v: float, a: int, levels: List[float]) -> float:
        if a == 0:
            return w0 if inside(u, v, w0) else edge(u, v, w0, levels[0])
        return edge(u, v, levels[a - 1], levels[a])

    def upper_edge(u: float, v: float, b: int, levels: List[float]) -> float:
        if b == len(levels) - 1:
            return w1 if inside(u, v, w1) else edge(u, v, w1, levels[b])
        return edge(u, v, levels[b + 1], levels[b])

    n_xy = max(8, min(30, int(math.sqrt(ray_budget / n_levels))))
    spacing = max(su, sv) / n_xy
    nu, nv = max(1, math.ceil(su / spacing)), max(1, math.ceil(sv / spacing))
    dw = sw / n_levels
    levels = [w0 + (k + 0.5) * dw for k in range(n_levels)]

    rays = []
    for i in range(nu):
        u = u0 + (i + 0.5) * spacing
        for j in range(nv):
            v = v0 + (j + 0.5) * spacing
            flags = [inside(u, v, w) for w in levels]
            intervals: List[Tuple[float, float]] = []
            k = 0
            while k < n_levels:
                if not flags[k]:
                    k += 1
                    continue
                a = k
                while k + 1 < n_levels and flags[k + 1]:
                    k += 1
                b = k
                start = lower_edge(u, v, a, levels)
                end = upper_edge(u, v, b, levels)
                intervals.append((start, end))
                k += 1
            rays.append((u, v, tuple(intervals)))
    return BodyInfo(body.name, local, units.cm3_to_mm3(body.volume), tuple(rays), spacing)


# ------------------------------------------------------------------ export
_REFINEMENT = {
    "low": "MeshRefinementLow", "medium": "MeshRefinementMedium", "high": "MeshRefinementHigh",
}


def is_single_component(design) -> bool:
    """True in a Part Design document, which can hold only one component (no sub-components)."""
    try:
        return design.designIntent == adsk.fusion.DesignIntentTypes.PartDesignIntentType
    except Exception:
        return False


def _safe(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*\s]+', "_", name).strip("_") or "part"


def export_bodies(design, bodies, folder: str, refinement: str = "medium") -> List[str]:
    """Export each body as <body name>.stl (Part Design: no occurrences to walk)."""
    os.makedirs(folder, exist_ok=True)
    em = design.exportManager
    written: List[str] = []
    for body in bodies:
        path = os.path.join(folder, _safe(body.name) + ".stl")
        opts = em.createSTLExportOptions(body, path)
        opts.meshRefinement = getattr(adsk.fusion.MeshRefinementSettings, _REFINEMENT.get(refinement, "MeshRefinementMedium"))
        em.execute(opts)
        written.append(path)
    return written


def export_occurrence_tree(design: adsk.fusion.Design, occurrence: adsk.fusion.Occurrence, folder: str,
                           refinement: str = "medium", step: bool = False) -> List[str]:
    """Export every body below `occurrence` as <body name>.stl (and .step when requested)."""
    os.makedirs(folder, exist_ok=True)
    em = design.exportManager
    written: List[str] = []

    def visit(occ: adsk.fusion.Occurrence) -> None:
        for body in occ.bRepBodies:  # proxies in the occurrence's assembly context
            path = os.path.join(folder, _safe(body.name) + ".stl")
            opts = em.createSTLExportOptions(body, path)
            opts.meshRefinement = getattr(adsk.fusion.MeshRefinementSettings, _REFINEMENT.get(refinement, "MeshRefinementMedium"))
            em.execute(opts)
            written.append(path)
            if step:
                spath = os.path.join(folder, _safe(body.name) + ".step")
                em.execute(em.createSTEPExportOptions(spath, body.parentComponent))
                written.append(spath)
        for child in occ.childOccurrences:
            visit(child)

    visit(occurrence)
    return written


def silhouette_heights(design: adsk.fusion.Design, body: adsk.fusion.BRepBody, frame, samples_per_edge: int = 5):
    """Heights (local w, mm) of points along the body's silhouette loop, or None if Fusion cannot split it.

    Runs a Silhouette Split on a throw-away copy and reads the edges whose two faces both stand
    (almost) parallel to the pull direction. Experimental: any failure returns None and the caller
    falls back to the planar parting height; the reason is logged.
    """
    if is_single_component(design):
        futil.log("Silhouette probe skipped: Part Design documents cannot hold scratch components.")
        return None
    tbm = adsk.fusion.TemporaryBRepManager.get()
    root = design.rootComponent
    occ = root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
    try:
        comp = occ.component
        comp.name = "MoldMaker scratch"
        parametric = design.designType == adsk.fusion.DesignTypes.ParametricDesignType
        base = comp.features.baseFeatures.add() if parametric else None
        if base:
            base.startEdit()
        try:
            temp = tbm.copy(body)
            real = comp.bRepBodies.add(temp, base) if base else comp.bRepBodies.add(temp)
        finally:
            if base:
                base.finishEdit()
        origin = adsk.core.Point3D.create(0, 0, 0)
        axis_in = comp.constructionAxes.createInput()
        axis_in.setByLine(adsk.core.InfiniteLine3D.create(origin, adsk.core.Vector3D.create(*frame.w)))
        axis = comp.constructionAxes.add(axis_in)
        bodies = adsk.core.ObjectCollection.create()
        bodies.add(real)
        feats = comp.features.silhouetteSplitFeatures
        feats.add(feats.createInput(bodies, axis, False))
        zs = []
        w = frame.w
        for edge in comp.bRepBodies.item(0).edges:
            if edge.faces.count != 2:
                continue
            ev_e = edge.evaluator
            ok, p0, p1 = ev_e.getParameterExtents()
            if not ok:
                continue
            ok, pt = ev_e.getPointAtParameter((p0 + p1) / 2.0)
            if not ok:
                continue
            flat = True
            for face in (edge.faces.item(0), edge.faces.item(1)):
                ev_f = face.evaluator
                ok, uv = ev_f.getParameterAtPoint(pt)
                ok2, n = ev_f.getNormalAtParameter(uv) if ok else (False, None)
                if not (ok and ok2) or abs(n.x * w[0] + n.y * w[1] + n.z * w[2]) > 0.25:
                    flat = False
                    break
            if not flat:
                continue
            for i in range(samples_per_edge):
                ok, pt_i = ev_e.getPointAtParameter(p0 + (p1 - p0) * (i + 0.5) / samples_per_edge)
                if ok:
                    zs.append(units.cm_to_mm(pt_i.x * w[0] + pt_i.y * w[1] + pt_i.z * w[2]))
        return zs or None
    except Exception as exc:
        futil.log(f"Silhouette Split probe failed: {exc}")
        return None
    finally:
        try:
            occ.deleteMe()
        except Exception:
            pass


# ----------------------------------------------------------------- adapter
class FusionAdapter:
    """Primitive geometry operations for strategies (local pull-frame mm in, temp bodies out)."""

    def __init__(self, app: adsk.core.Application, design: adsk.fusion.Design,
                 target: adsk.fusion.BRepBody, plan: MoldPlan):
        self.app, self.design, self.target, self.plan = app, design, target, plan
        self.frame = plan.frame
        self.tbm = adsk.fusion.TemporaryBRepManager.get()
        self.parametric = design.designType == adsk.fusion.DesignTypes.ParametricDesignType
        self.warnings: List[str] = []
        self.main_occurrence: Optional[adsk.fusion.Occurrence] = None
        self.exported: List[str] = []
        self.single_component = is_single_component(design)
        self.flat_bodies: list = []
        self.real: dict = {}  # part id -> (component, real body) after commit

    # ---- conversions -------------------------------------------------------
    def _pt(self, p: Sequence[float]) -> adsk.core.Point3D:
        x, y, z = (units.mm_to_cm(c) for c in self.frame.to_world((p[0], p[1], p[2])))
        return adsk.core.Point3D.create(x, y, z)

    def _dir(self, d: Sequence[float]) -> adsk.core.Vector3D:
        return adsk.core.Vector3D.create(*self.frame.to_world((d[0], d[1], d[2])))

    # ---- primitives --------------------------------------------------------
    def box(self, bb: BBox):
        sx, sy, sz = bb.size
        obb = adsk.core.OrientedBoundingBox3D.create(
            self._pt(bb.center), self._dir((1, 0, 0)), self._dir((0, 1, 0)),
            units.mm_to_cm(sx), units.mm_to_cm(sy), units.mm_to_cm(sz))
        return self.tbm.createBox(obb)

    def cylinder(self, p0, p1, r0, r1=None):
        return self.tbm.createCylinderOrCone(self._pt(p0), units.mm_to_cm(r0), self._pt(p1),
                                             units.mm_to_cm(r0 if r1 is None else r1))

    def sphere(self, c, r):
        return self.tbm.createSphere(self._pt(c), units.mm_to_cm(r))

    def hex_prism(self, x, y, z0, z1, af):
        """Hexagonal prism (across flats = af) as the intersection of three slabs 60 degrees apart."""
        body = None
        for deg in (0, 60, 120):
            a = math.radians(deg)
            length_dir = (math.cos(a), math.sin(a), 0.0)
            width_dir = (-math.sin(a), math.cos(a), 0.0)
            obb = adsk.core.OrientedBoundingBox3D.create(
                self._pt((x, y, (z0 + z1) / 2.0)), self._dir(length_dir), self._dir(width_dir),
                units.mm_to_cm(af * 3.0), units.mm_to_cm(af), units.mm_to_cm(z1 - z0))
            slab = self.tbm.createBox(obb)
            if body is None:
                body = slab
            else:
                self.intersect(body, slab)
        return body

    def slot(self, p0, p1, width, z0, z1):
        """Flat rectangular slot from p0 to p1 (local xy), width wide, between heights z0 and z1."""
        dx, dy = p1[0] - p0[0], p1[1] - p0[1]
        length = math.hypot(dx, dy)
        if length < 1e-9:
            raise RuntimeError("Zero-length vent slot.")
        ux, uy = dx / length, dy / length
        obb = adsk.core.OrientedBoundingBox3D.create(
            self._pt(((p0[0] + p1[0]) / 2.0, (p0[1] + p1[1]) / 2.0, (z0 + z1) / 2.0)),
            self._dir((ux, uy, 0.0)), self._dir((-uy, ux, 0.0)),
            units.mm_to_cm(length), units.mm_to_cm(width), units.mm_to_cm(abs(z1 - z0)))
        return self.tbm.createBox(obb)

    def copy(self, body):
        return self.tbm.copy(body)

    def _boolean(self, target, tool, op, label: str):
        if not self.tbm.booleanOperation(target, self.tbm.copy(tool), op):
            raise RuntimeError(f"Boolean {label} failed. The master may be non-manifold or self-intersecting.")

    def union(self, target, tool):
        self._boolean(target, tool, adsk.fusion.BooleanTypes.UnionBooleanType, "union")

    def cut(self, target, tool):
        self._boolean(target, tool, adsk.fusion.BooleanTypes.DifferenceBooleanType, "cut")

    def intersect(self, target, tool):
        self._boolean(target, tool, adsk.fusion.BooleanTypes.IntersectionBooleanType, "intersect")

    def volume(self, body) -> float:
        return units.cm3_to_mm3(body.volume)

    def _warn_once(self, message: str) -> None:
        if message not in self.warnings:
            self.warn(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)
        futil.log("Warning: " + message)

    # ---- master copy (shrink-scaled) --------------------------------------
    def master(self):
        """A temporary copy of the target, scaled about its bbox centre by the shrink factors."""
        body = self.tbm.copy(self.target)
        factors = self.plan.params.shrink_factors_world()
        if any(abs(f - 1.0) > 1e-12 for f in factors):
            bb = self.target.boundingBox  # API-internal cm: used as-is, no unit conversion
            centre = ((bb.minPoint.x + bb.maxPoint.x) / 2, (bb.minPoint.y + bb.maxPoint.y) / 2, (bb.minPoint.z + bb.maxPoint.z) / 2)
            m = adsk.core.Matrix3D.create()
            for i in range(3):
                m.setCell(i, i, factors[i])
                m.setCell(i, 3, centre[i] * (1.0 - factors[i]))
            if not self.tbm.transform(body, m):
                raise RuntimeError("Could not apply the shrink scale to the master copy "
                                   "(non-uniform shrink may not be supported here; try uniform shrink).")
        return body

    # ---- offset (needs real features; done in a throw-away component) ---------
    def offset(self, temp_body, distance_mm: float):
        """Offset every face of a temporary body by distance_mm (+ outward, - inward); returns a temp body.

        Uses an Offset Faces feature on a scratch copy, then discards the scratch component.
        If Fusion cannot offset the shape, falls back to an anisotropic scale about the bounding-box
        centre (exact thickness only along the axes) and reports a warning.
        """
        if self.single_component:
            self._warn_once("Part Design documents cannot hold scratch components, so offsets use an approximate scaled shape "
                            "(thickness exact only along the bounding-box axes). Use a Design document for exact offsets.")
            return self._scaled_offset(temp_body, distance_mm)
        root = self.design.rootComponent
        occ = root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
        comp = occ.component
        comp.name = "MoldMaker scratch"
        try:
            real = self._add_real_body(comp, self.tbm.copy(temp_body))
            volume_before = real.volume
            feats = comp.features.offsetFacesFeatures
            result = None
            for sign in (1.0, -1.0):  # Fusion's sign convention is verified by volume, not assumed
                faces = adsk.core.ObjectCollection.create()
                for face in real.faces:
                    faces.add(face)
                feat = feats.add(feats.createInput(faces, adsk.core.ValueInput.createByString(units.mm_expr(sign * distance_mm))))
                grew = comp.bRepBodies.item(0).volume > volume_before
                if grew == (distance_mm > 0):
                    result = self.tbm.copy(comp.bRepBodies.item(0))
                    break
                feat.deleteMe()
            if result is None:
                raise RuntimeError("offset direction could not be determined")
            return result
        except Exception as exc:
            self.warn(f"Offset of {distance_mm:+g} mm failed ({exc}); using an approximate scaled shape instead. "
                      "Thickness is exact only along the bounding-box axes.")
            return self._scaled_offset(temp_body, distance_mm)
        finally:
            try:
                occ.deleteMe()
            except Exception:
                pass

    def _add_real_body(self, comp, temp):
        base = comp.features.baseFeatures.add() if self.parametric else None
        if base:
            base.startEdit()
        try:
            return comp.bRepBodies.add(temp, base) if base else comp.bRepBodies.add(temp)
        finally:
            if base:
                base.finishEdit()

    def _scaled_offset(self, temp_body, distance_mm: float):
        body = self.tbm.copy(temp_body)
        bb = body.boundingBox  # API-internal cm, used as-is
        d = units.mm_to_cm(distance_mm)
        lo = (bb.minPoint.x, bb.minPoint.y, bb.minPoint.z)
        hi = (bb.maxPoint.x, bb.maxPoint.y, bb.maxPoint.z)
        m = adsk.core.Matrix3D.create()
        for i in range(3):
            size = hi[i] - lo[i]
            f = max((size + 2.0 * d) / size, 0.05) if size > 1e-9 else 1.0
            centre = (lo[i] + hi[i]) / 2.0
            m.setCell(i, i, f)
            m.setCell(i, 3, centre * (1.0 - f))
        if not self.tbm.transform(body, m):
            raise RuntimeError("Could not scale the body for the fallback offset.")
        return body

    # ---- layout ------------------------------------------------------------
    def lay_flat(self, body, plan: MoldPlan) -> None:
        """Flip the body 180 deg about the u axis through the parting plane and shift it along +v."""
        cu, cv, _ = plan.block.center
        shift = plan.block.size[1] + LAY_FLAT_GAP_MM
        origin = self._pt((cu, cv + shift / 2.0, plan.parting_z))
        m = adsk.core.Matrix3D.create()
        m.setToRotation(math.pi, self._dir((1, 0, 0)), origin)
        if not self.tbm.transform(body, m):
            raise RuntimeError("Could not lay the upper half flat.")

    # ---- draft analysis ------------------------------------------------------
    def draft_samples(self, grid: int = 3) -> List[Tuple[float, float, float]]:
        """Sample the target's faces: (area mm2, outward normal . pull, height along pull in mm)."""
        w_axis = self.frame.w
        out: List[Tuple[float, float, float]] = []
        for face in self.target.faces:
            area = face.area * 100.0  # cm2 -> mm2 (area scale is the square of the length scale)
            ev = face.evaluator
            points = []
            rng = ev.parametricRange()
            if rng is not None:
                for i in range(grid):
                    for j in range(grid):
                        uv = adsk.core.Point2D.create(
                            rng.minPoint.x + (i + 0.5) * (rng.maxPoint.x - rng.minPoint.x) / grid,
                            rng.minPoint.y + (j + 0.5) * (rng.maxPoint.y - rng.minPoint.y) / grid)
                        if ev.isParameterOnFace(uv):
                            points.append(uv)
            samples = []
            for uv in points:
                ok_n, n = ev.getNormalAtParameter(uv)
                ok_p, pt = ev.getPointAtParameter(uv)
                if ok_n and ok_p:
                    samples.append((n, pt))
            if not samples:  # tiny or oddly trimmed face: fall back to an interior point
                pt = face.pointOnFace
                ok_p, uv = ev.getParameterAtPoint(pt)
                ok_n, n = ev.getNormalAtParameter(uv) if ok_p else (False, None)
                if ok_n:
                    samples.append((n, pt))
            for n, pt in samples:
                sign = -1.0 if face.isParamReversed else 1.0  # outward = surface normal unless reversed
                n_dot_w = sign * (n.x * w_axis[0] + n.y * w_axis[1] + n.z * w_axis[2])
                z = units.cm_to_mm(pt.x * w_axis[0] + pt.y * w_axis[1] + pt.z * w_axis[2])
                out.append((area / len(samples), n_dot_w, z))
        return out

    # ---- draft application (core/cavity, opt-in; needs the committed real bodies) --------------
    def apply_draft(self, plan: MoldPlan) -> None:
        """Try to add the draft angle to each insert's cavity walls with a Draft feature.

        Best effort: the feature's direction is verified by volume (a draft that opens the cavity
        toward the parting plane removes material), and every failure becomes a warning.
        """
        p, pz, cav = plan.params, plan.parting_z, plan.cavity_bbox
        w_axis = self.frame.w
        cu, cv, _ = plan.block.center
        shift_v = plan.block.size[1] + LAY_FLAT_GAP_MM
        tol = 0.1
        for name, (comp, body) in self.real.items():
            flipped = name == "upper" and p.lay_flat

            def local(pt):
                x, y, z = self.frame.to_local(tuple(units.cm_to_mm(c) for c in (pt.x, pt.y, pt.z)))
                if flipped:  # undo the lay-flat rotation (180 deg about u through the parting plane)
                    y, z = 2.0 * (cv + shift_v / 2.0) - y, 2.0 * pz - z
                return x, y, z

            parting_face, walls = None, []
            for face in body.faces:
                bb = face.boundingBox
                lo, hi = local(bb.minPoint), local(bb.maxPoint)
                lo, hi = tuple(min(a, b) for a, b in zip(lo, hi)), tuple(max(a, b) for a, b in zip(lo, hi))
                plane = adsk.core.Plane.cast(face.geometry)
                n_dot_w = abs(plane.normal.x * w_axis[0] + plane.normal.y * w_axis[1] + plane.normal.z * w_axis[2]) if plane else 0.0
                if plane and n_dot_w > 0.999 and abs(hi[2] - pz) < tol and abs(lo[2] - pz) < tol:
                    if parting_face is None or face.area > parting_face.area:
                        parting_face = face
                    continue
                inside = all(cav.min[i] - tol <= lo[i] and hi[i] <= cav.max[i] + tol for i in range(3))
                if inside and not (plane and n_dot_w > 0.999):
                    walls.append(face)
            if parting_face is None or not walls:
                self.warn(f"Draft not applied to the {name} insert: could not identify its parting face or cavity walls.")
                continue
            self._draft_faces(comp, body, parting_face, walls[:60], name, p.draft_deg)

    def _draft_faces(self, comp, body, parting_face, walls, name: str, angle_deg: float) -> None:
        feats = comp.features.draftFeatures
        volume_before = body.volume
        errors = []
        for flip in (False, True):
            try:
                faces = adsk.core.ObjectCollection.create()
                for f in walls:
                    faces.add(f)
                inp = feats.createInput(faces, parting_face, True)
                inp.setSingleAngle(False, adsk.core.ValueInput.createByString(units.deg_expr(angle_deg)))
                inp.isDirectionFlipped = flip
                feat = feats.add(inp)
            except Exception as exc:
                errors.append(str(exc).splitlines()[0] if str(exc) else repr(exc))
                continue
            if body.volume < volume_before:  # cavity opened toward the parting plane
                return
            try:
                feat.deleteMe()
            except Exception:
                pass
        self.warn(f"Draft could not be applied to the {name} insert ({'; '.join(errors) or 'direction check failed'}). "
                  "Add the draft to the master before running MoldMaker instead.")

    # ---- user parameters -----------------------------------------------------
    def create_user_parameters(self) -> None:
        """Create (or update) MM_* user parameters documenting the settings."""
        table = self.design.userParameters
        for up in userparams.from_plan(self.plan):
            if up.unit == "mm":
                expr = units.mm_expr(up.value)
            elif up.unit == "deg":
                expr = units.deg_expr(up.value)
            else:
                expr = None
            existing = table.itemByName(up.name)
            if existing:
                if expr:
                    existing.expression = expr
                else:
                    existing.value = up.value
                existing.comment = up.comment
            else:
                value_input = adsk.core.ValueInput.createByString(expr) if expr else adsk.core.ValueInput.createByReal(up.value)
                table.add(up.name, value_input, up.unit, up.comment)

    # ---- commit ------------------------------------------------------------
    def commit(self, parts: List[Tuple[str, List[Tuple[str, Any]]]]) -> None:
        """Create 'Mold - <body>' with one component per part and add the bodies (one base feature each)."""
        root = self.design.rootComponent
        if self.single_component:
            self._commit_flat(parts)
            return
        identity = adsk.core.Matrix3D.create()
        self.main_occurrence = root.occurrences.addNewComponent(identity)
        self.main_occurrence.component.name = self.plan.component_name
        main_comp = self.main_occurrence.component
        for part_name, bodies in parts:
            occ = main_comp.occurrences.addNewComponent(adsk.core.Matrix3D.create())
            comp = occ.component
            comp.name = part_name
            base = comp.features.baseFeatures.add() if self.parametric else None
            if base:
                base.startEdit()
            try:
                for body_name, temp in bodies:
                    lumps = temp.lumps.count
                    new_body = comp.bRepBodies.add(temp, base) if base else comp.bRepBodies.add(temp)
                    new_body.name = f"{self.plan.body_name}_{body_name}"
                    self.real[body_name] = (comp, new_body)
                    if lumps != 1:
                        self.warn(f"{new_body.name} has {lumps} separate lumps; check for floating islands.")
            finally:
                if base:
                    base.finishEdit()

    def _commit_flat(self, parts) -> None:
        """Part Design: one component only, so every part becomes a body of the root component."""
        comp = self.design.rootComponent
        self.warn("This is a Part Design document, which holds a single component: the mold parts were added as bodies "
                  f"named '{self.plan.component_name} - <part>' instead of separate components.")
        base = comp.features.baseFeatures.add() if self.parametric else None
        if base:
            base.startEdit()
        try:
            for part_name, bodies in parts:
                for body_name, temp in bodies:
                    lumps = temp.lumps.count
                    new_body = comp.bRepBodies.add(temp, base) if base else comp.bRepBodies.add(temp)
                    new_body.name = f"{self.plan.component_name} - {part_name}" if len(bodies) == 1 else f"{self.plan.component_name} - {part_name} - {body_name}"
                    self.real[body_name] = (comp, new_body)
                    self.flat_bodies.append(new_body)
                    if lumps != 1:
                        self.warn(f"{new_body.name} has {lumps} separate lumps; check for floating islands.")
        finally:
            if base:
                base.finishEdit()

    # ---- orchestration -----------------------------------------------------
    def run(self, strategy) -> List[str]:
        """Build, group the timeline items, export. Returns warnings."""
        timeline = self.design.timeline if self.parametric else None
        start = timeline.markerPosition if timeline else 0
        try:
            strategy.build(self.plan, self)
        except Exception:
            self._rollback()
            raise
        if timeline:
            end = timeline.markerPosition - 1
            if end >= start:
                try:
                    group = timeline.timelineGroups.add(start, end)
                    group.name = self.plan.group_name
                except Exception as exc:  # grouping is cosmetic; never lose the mold over it
                    self.warn(f"Could not group timeline items: {exc}")
        params = self.plan.params
        if params.create_user_params:
            try:
                self.create_user_parameters()
            except Exception as exc:  # informational only
                self.warn(f"Could not create user parameters: {exc}")
        if params.export_stl and params.export_dir and self.single_component and self.flat_bodies:
            try:
                self.exported = export_bodies(self.design, self.flat_bodies, params.export_dir, params.mesh_refinement)
            except Exception as exc:
                self.warn(f"STL export failed: {exc}")
        elif params.export_stl and params.export_dir and self.main_occurrence is not None:
            try:
                self.exported = export_occurrence_tree(self.design, self.main_occurrence, params.export_dir,
                                                       params.mesh_refinement)
            except Exception as exc:
                self.warn(f"STL export failed: {exc}")
        return self.warnings

    def _rollback(self) -> None:
        for body in self.flat_bodies:
            try:
                body.deleteMe()
            except Exception:
                pass
        self.flat_bodies = []
        if self.main_occurrence is not None:
            try:
                self.main_occurrence.deleteMe()
            except Exception:
                pass
            self.main_occurrence = None
