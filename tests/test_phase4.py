import math
import unittest

from MoldMaker import strategies
from MoldMaker.core import draft, layout, parting, presets
from MoldMaker.core.model import BBox, BodyInfo, PointFootprint, RectFootprint

from . import helpers
from .fake_adapter import FakeAdapter


def plate_with_pit(pit_z=6.0, size=30, spacing=1.0):
    """30x30 plate 10 mm tall with a 3x3 pit in the middle."""
    def spans(x, y):
        in_pit = abs(x - size / 2) <= 1.0 and abs(y - size / 2) <= 1.0
        return [(0.0, pit_z if in_pit else 10.0)]

    rays = helpers.make_rays(spans, (0, size), (0, size), spacing)
    return BodyInfo("plate", BBox((0, 0, 0), (size, size, 10)), size * size * 9.0, rays, spacing)


def build(mold_type, body, **kw):
    p = helpers.params(mold_type=mold_type, wall_mm=15, floor_top_mm=15, **kw)
    s = strategies.get_strategy(mold_type)
    plan = s.plan(p, body)
    fa = FakeAdapter(plan)
    s.build(plan, fa)
    return plan, fa


class LowPointsTest(unittest.TestCase):
    def test_pit_found_once_at_centre(self):
        pts = parting.low_points_from_rays(plate_with_pit().rays)
        self.assertEqual(len(pts), 1)
        self.assertAlmostEqual(pts[0][0], 15, delta=1.0)
        self.assertAlmostEqual(pts[0][2], 6.0)

    def test_convex_and_flat_shapes_have_no_pits(self):
        self.assertEqual(parting.low_points_from_rays(helpers.sphere_info(15).rays), [])
        self.assertEqual(parting.low_points_from_rays(helpers.box_info().rays), [])

    def test_ramp_and_edge_notches_are_not_pits(self):
        ramp = helpers.make_rays(lambda x, y: [(0.0, 5.0 + 0.5 * x)], (0, 20), (0, 20), 1.0)
        self.assertEqual(parting.low_points_from_rays(ramp), [])
        # a dip touching the edge of the sampled area is a notch, not a pit
        notch = helpers.make_rays(lambda x, y: [(0.0, 4.0 if x <= 1 else 10.0)], (0, 20), (0, 20), 1.0)
        self.assertEqual(parting.low_points_from_rays(notch), [])

    def test_lowest_first_and_empty(self):
        def spans(x, y):
            if abs(x - 8) <= 1 and abs(y - 10) <= 1:
                return [(0.0, 7.0)]
            if abs(x - 22) <= 1 and abs(y - 10) <= 1:
                return [(0.0, 4.0)]
            return [(0.0, 10.0)]
        pts = parting.low_points_from_rays(helpers.make_rays(spans, (0, 30), (0, 20), 1.0))
        self.assertEqual([round(p[2]) for p in pts], [4, 7])
        self.assertEqual(parting.low_points_from_rays(()), [])


class BuckDraftTest(unittest.TestCase):
    BASE = (400.0, -1.0, 0.0)

    def lean(self, deg, z=5.0):
        """A wall whose outward normal tilts up by `deg` (a buck that tapers inward as it rises)."""
        return (100.0, math.sin(math.radians(deg)), z)

    def test_tapered_buck_is_clean(self):
        r = draft.analyze([self.BASE, self.lean(5), self.lean(6), (300.0, 1.0, 10.0)], 4.5, buck=True)
        self.assertEqual(draft.warnings_for(r, 4.5), [])

    def test_vertical_walls_insufficient(self):
        r = draft.analyze([self.BASE, self.lean(0.0), (300.0, 1.0, 10.0)], 4.5, buck=True)
        self.assertGreater(r.insufficient_frac, 0.1)

    def test_tuck_under_is_undercut(self):
        r = draft.analyze([self.BASE, self.lean(-8.0), (300.0, 1.0, 10.0)], 4.5, buck=True)
        self.assertGreater(r.undercut_frac, 0.0)

    def test_top_face_is_never_the_open_back_for_a_buck(self):
        r = draft.analyze([self.BASE, (300.0, 1.0, 10.0)], 4.5, buck=True)
        self.assertEqual(r.total_area, 300.0)
        self.assertEqual(r.undercut_area, 0.0)


class FootprintGrownTest(unittest.TestCase):
    def test_rect_and_points(self):
        self.assertEqual(RectFootprint(0, 0, 10, 10).grown(2), RectFootprint(-2, -2, 12, 12))
        fp = PointFootprint([(0.0, 0.0)], 1.0)
        self.assertTrue(fp.is_clear(5.0, 0.0, 2.0))
        self.assertFalse(fp.grown(3.0).is_clear(5.0, 0.0, 2.0))


class PresetDefaultsTest(unittest.TestCase):
    def test_new_defaults(self):
        lib = presets.load_presets()
        d = lib.defaults_for("mold_silicone_platinum", "brush_on_mother")
        self.assertEqual((d["skin_mm"], d["shell_mm"], d["flange_w_mm"]), (4, 4, 15))
        self.assertEqual(lib.defaults_for("vacuum_forming", "vacuum_buck")["shell_mm"], 2)
        self.assertEqual(lib.defaults_for("slip_casting", "slip_cast_case")["plaster_thickness_mm"], 25)
        self.assertEqual(lib.defaults_for("slip_casting", "slip_cast_case")["shrink_pct"], 12)


class ParamValidationTest(unittest.TestCase):
    def test_new_checks(self):
        self.assertTrue(helpers.params(mold_type="brush_on_mother", skin_mm=0).validate())
        self.assertTrue(helpers.params(mold_type="slip_cast_case", case_wall_mm=0).validate())
        self.assertTrue(helpers.params(mold_type="slip_cast_case", slip_well_d_mm=-1).validate())
        self.assertTrue(helpers.params(mold_type="vacuum_buck", vent_hole_d_mm=0).validate())
        self.assertEqual(helpers.params(mold_type="brush_on_mother").validate(), [])


class BrushOnMotherTest(unittest.TestCase):
    def setUp(self):
        self.plan, self.fa = build("brush_on_mother", helpers.sphere_info(15), skin_mm=4, shell_mm=4, flange_w_mm=20)

    def test_plan_geometry(self):
        grow = 8
        sx, sy, _ = self.plan.block.size
        self.assertAlmostEqual(sx, 30 + 2 * grow + 2 * 20)
        self.assertAlmostEqual(sy, sx)
        self.assertEqual([p.id for p in self.plan.parts], ["mother_lower", "mother_upper", "skin"])
        self.assertIsNone(self.plan.sprue)
        self.assertEqual(self.plan.vents, [])
        self.assertAlmostEqual(self.plan.parting_z, 0.0, delta=0.8)

    def test_keys_and_bolts_sit_on_the_flange_clear_of_the_shell(self):
        self.assertGreaterEqual(len(self.plan.keys), 2)
        self.assertGreaterEqual(len(self.plan.bolts), 2)
        fp = layout.footprint_of(parting.complete_info(helpers.sphere_info(15))).grown(8)
        for k in self.plan.keys:
            self.assertTrue(fp.is_clear(k.x, k.y, k.d_mm / 2 + 2 - 1e-6))
        for b in self.plan.bolts:
            self.assertTrue(fp.is_clear(b.x, b.y, b.hole_d_mm / 2 + 2 - 1e-6))

    def test_flange_thick_enough_for_hardware(self):
        hw = layout.HARDWARE["M4"]
        self.assertGreaterEqual(2 * self.plan.extras["flange_t"], hw.cbore_depth + hw.nut_depth)

    def test_build_offsets_then_hollows_then_splits(self):
        self.assertEqual([o.info["distance"] for o in self.fa.offsets], [4, 4])
        names = [n for n, _ in self.fa.committed]
        self.assertEqual(names, ["Mother lower", "Mother upper", "Silicone skin"])
        lower = self.fa.committed[0][1][0][1]
        self.assertIn(("cut", "offset"), lower.ops)           # envelope hollowed out of the shell
        self.assertIn(("union", "box"), lower.ops)            # flange
        self.assertEqual(self.fa.count(lower, "union", "sphere"), len(self.plan.keys))
        skin = self.fa.committed[2][1][0][1]
        self.assertIn(("cut", "master"), skin.ops)
        self.assertEqual(self.fa.warnings, [])

    def test_thin_skin_and_shell_warn(self):
        plan, _ = build("brush_on_mother", helpers.sphere_info(15), skin_mm=1, shell_mm=2, flange_w_mm=20)
        self.assertTrue(any("skin" in w for w in plan.warnings))
        self.assertTrue(any("shell" in w for w in plan.warnings))


class SlipCastTest(unittest.TestCase):
    def setUp(self):
        self.plan, self.fa = build("slip_cast_case", helpers.sphere_info(15), shrink_pct=12.0,
                                   plaster_thickness_mm=25, case_wall_mm=2.4, slip_well_h_mm=25)

    def test_master_scaled_for_clay_shrink(self):
        self.assertAlmostEqual(self.plan.cavity_bbox.size[0], 30 * 1.12)

    def test_plaster_block_and_case(self):
        b, c = self.plan.block, self.plan.extras["case_outer"]
        self.assertAlmostEqual(b.size[0], 30 * 1.12 + 50)
        self.assertAlmostEqual(c.size[0] - b.size[0], 2 * 2.4)
        well = self.plan.posts[0]
        self.assertEqual(b.max[2], well.z_to)                    # well opens at the plaster top
        self.assertAlmostEqual(well.z_to - 15 * 1.12, 25)        # 25 mm of well above the master

    def test_plaster_and_water_split_10_to_7(self):
        m = self.plan.metrics
        self.assertGreater(m["Plaster powder (g)"], 0)
        self.assertAlmostEqual(m["Water (g)"] / m["Plaster powder (g)"], 0.7)
        slurry = m["Plaster volume (cm3)"] * 1.57
        self.assertAlmostEqual(m["Plaster powder (g)"] + m["Water (g)"], slurry)

    def test_parts_and_no_hardware(self):
        self.assertEqual([n for n, _ in self.fa.committed],
                         ["Lower case", "Upper case", "Master with well", "Plaster mold (reference)"])
        self.assertEqual((self.plan.keys, self.plan.bolts, self.plan.vents, self.plan.sprue), ([], [], [], None))

    def test_cases_are_shells_open_on_the_parting_side(self):
        lower = self.fa.committed[0][1][0][1]
        upper = self.fa.committed[1][1][0][1]
        self.assertEqual(self.fa.count(lower, "cut", "box"), 1)
        self.assertEqual(self.fa.count(upper, "cut", "box"), 1)

    def test_master_with_well_and_plaster_halves(self):
        tool = self.fa.committed[2][1][0][1]
        self.assertEqual(self.fa.count(tool, "union", "cyl"), 1)
        names = [n for n, _ in self.fa.committed[3][1]]
        self.assertEqual(names, ["plaster_lower", "plaster_upper"])

    def test_explicit_well_diameter_and_oversize_warning(self):
        plan, _ = build("slip_cast_case", helpers.sphere_info(15), slip_well_d_mm=30.0)
        self.assertEqual(plan.posts[0].d_mm, 30.0)
        self.assertTrue(any("slip well" in w for w in plan.warnings))


class VacuumBuckTest(unittest.TestCase):
    def setUp(self):
        self.plan, self.fa = build("vacuum_buck", plate_with_pit(), shell_mm=2.0, flange_w_mm=10, vent_hole_d_mm=0.8)

    def test_vent_hole_at_the_pit(self):
        self.assertEqual(len(self.plan.vents), 1)
        v = self.plan.vents[0]
        self.assertEqual(v.kind, "buck_hole")
        self.assertEqual(v.d_mm, 0.8)
        self.assertGreater(v.z_from, 6.0)
        self.assertLess(v.z_to, 6.0 - 2.0)  # reaches through the shell into the hollow

    def test_flange_under_the_master(self):
        b = self.plan.block
        self.assertAlmostEqual(b.min[2], -3.0)  # flange_t = max(shell, 3)
        self.assertAlmostEqual(b.size[0], 30 + 20)

    def test_hollow_is_an_inward_offset_with_an_open_stem(self):
        self.assertEqual([o.info["distance"] for o in self.fa.offsets], [-2.0])
        buck = self.fa.committed[0][1][0][1]
        self.assertIn(("union", "box"), buck.ops)       # flange
        self.assertIn(("cut", "offset"), buck.ops)      # hollow
        self.assertEqual(self.fa.count(buck, "cut", "cyl"), 1)  # vent hole
        self.assertEqual([n for n, _ in self.fa.committed], ["Buck"])

    def test_draft_warning_for_vertical_buck_walls(self):
        p = helpers.params(mold_type="vacuum_buck", draft_deg=4.5)
        s = strategies.get_strategy("vacuum_buck")
        plan = s.plan(p, plate_with_pit())
        fa = FakeAdapter(plan)
        fa.draft = [(400.0, -1.0, 0.0), (100.0, 0.0, 5.0), (300.0, 1.0, 10.0)]
        s.build(plan, fa)
        self.assertTrue(any("draft" in w for w in fa.warnings))

    def test_thin_shell_warns(self):
        plan, _ = build("vacuum_buck", plate_with_pit(), shell_mm=1.0)
        self.assertTrue(any("Shell thinner" in w for w in plan.warnings))


if __name__ == "__main__":
    unittest.main()
