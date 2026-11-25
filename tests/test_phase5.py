import dataclasses
import math
import unittest

from MoldMaker import strategies
from MoldMaker.core import draft, parting
from MoldMaker.core.model import BBox
from MoldMaker.strategies import core_cavity

from . import helpers
from .fake_adapter import FakeAdapter


def plan_for(body, **kw):
    kw.setdefault("wall_mm", 15)
    kw.setdefault("floor_top_mm", 15)
    kw.setdefault("draft_deg", 1.5)
    p = helpers.params(mold_type="core_cavity", mold_material_id="aluminum", casting_id="injection_ABS", **kw)
    return strategies.get_strategy("core_cavity").plan(p, body)


def run_build(body, **kw):
    plan = plan_for(body, **kw)
    fa = FakeAdapter(plan)
    strategies.get_strategy("core_cavity").build(plan, fa)
    return plan, fa


class RoundingTest(unittest.TestCase):
    def test_round_up_symmetric(self):
        b = core_cavity.round_up_block(BBox((0, 0, 0), (52, 61, 30)), 5)
        self.assertEqual(b.size, (55.0, 65.0, 30.0))
        self.assertAlmostEqual(b.center[0], 26.0)
        self.assertAlmostEqual(b.center[1], 30.5)

    def test_exact_multiple_and_off(self):
        blk = BBox((0, 0, 0), (50, 60, 30))
        self.assertEqual(core_cavity.round_up_block(blk, 5), blk)
        self.assertEqual(core_cavity.round_up_block(blk, 0), blk)


class PlanTest(unittest.TestCase):
    def test_parts_named_core_and_cavity(self):
        plan = plan_for(helpers.box_info())
        self.assertEqual([p.name for p in plan.parts], ["Core insert", "Cavity insert"])
        for s in plan.block.size[:2]:
            self.assertAlmostEqual(s % 5, 0, places=6)

    def test_leader_pins_are_pin_kind_and_sized(self):
        plan = plan_for(helpers.box_info(), leader_pin_d_mm=8)
        self.assertGreaterEqual(len(plan.keys), 2)
        self.assertTrue(all(k.kind == "pin" and k.d_mm == 8 for k in plan.keys))

    def test_zero_draft_warns(self):
        self.assertTrue(any("Draft angle is 0" in w for w in plan_for(helpers.box_info(), draft_deg=0).warnings))
        self.assertFalse(any("Draft angle is 0" in w for w in plan_for(helpers.box_info()).warnings))

    def test_top_sprue_has_no_gate(self):
        plan = plan_for(helpers.sphere_info(15), sprue_location="top")
        self.assertNotIn("gate", plan.extras)

    def test_edge_sprue_gets_runner_and_gate(self):
        plan = plan_for(helpers.box_info(), sprue_location="edge", gate_d_mm=1.2)
        self.assertEqual(plan.sprue.location, "edge")
        x0, y0, x1, y1, d = plan.extras["gate"]
        self.assertEqual(d, 1.2)
        # the runner end sits outside the cavity box, the gate end inside it
        cav = plan.cavity_bbox
        outside = not (cav.min[0] <= plan.sprue.x <= cav.max[0] and cav.min[1] <= plan.sprue.y <= cav.max[1])
        inside = cav.min[0] - 1e-6 <= x1 <= cav.max[0] + 1e-6 and cav.min[1] - 1e-6 <= y1 <= cav.max[1] + 1e-6
        self.assertTrue(outside)
        self.assertTrue(inside)
        self.assertAlmostEqual(plan.sprue.z_from, plan.parting_z)
        self.assertGreater(math.hypot(plan.sprue.x - x1, plan.sprue.y - y1), core_cavity.GATE_LAND_MM - 1e-6)

    def test_parting_vents_become_slots(self):
        plan = plan_for(helpers.box_info(), vent_slot_w_mm=3.0, vent_slot_depth_mm=0.05)
        slots = [v for v in plan.vents if v.kind == "slot"]
        for v in slots:
            self.assertEqual(v.d_mm, 3.0)
            self.assertAlmostEqual(v.z_to - v.z_from, 0.05)
            self.assertAlmostEqual(v.z_to, plan.parting_z)

    def test_validate(self):
        self.assertTrue(helpers.params(mold_type="core_cavity", leader_pin_d_mm=0).validate())
        self.assertTrue(helpers.params(mold_type="core_cavity", draft_deg=20).validate())
        self.assertFalse(helpers.params(mold_type="core_cavity", draft_deg=2).validate())


class SilhouetteTest(unittest.TestCase):
    def test_height_helper(self):
        z, dev = parting.height_from_silhouette([4.9, 5.0, 5.1, 5.0], 0, 10)
        self.assertAlmostEqual(z, 5.0, delta=0.1)
        self.assertLess(dev, 0.2)
        self.assertEqual(parting.height_from_silhouette([], 0, 10), (None, 0.0))
        self.assertEqual(parting.height_from_silhouette([50.0], 0, 10), (None, 0.0))

    def test_uses_silhouette_height_in_auto_mode(self):
        info = dataclasses.replace(helpers.box_info(), silhouette_z=(5.0, 5.0, 5.2))
        plan = plan_for(info, parting_silhouette=True)
        self.assertAlmostEqual(plan.parting_z, 5.0, delta=0.15)
        self.assertFalse(any("silhouette" in w.lower() for w in plan.warnings))

    def test_wandering_loop_warns(self):
        info = dataclasses.replace(helpers.box_info(), silhouette_z=(2.0, 5.0, 8.0))
        plan = plan_for(info, parting_silhouette=True)
        self.assertTrue(any("wanders" in w for w in plan.warnings))

    def test_failure_falls_back_to_planar(self):
        plain = plan_for(helpers.box_info())
        plan = plan_for(helpers.box_info(), parting_silhouette=True)
        self.assertEqual(plan.parting_z, plain.parting_z)
        self.assertTrue(any("could not find a silhouette" in w for w in plan.warnings))

    def test_manual_mode_ignores_silhouette(self):
        info = dataclasses.replace(helpers.box_info(), silhouette_z=(9.0,))
        plan = plan_for(info, parting_silhouette=True, parting_mode="manual")
        self.assertTrue(any("manually" in w for w in plan.warnings))
        self.assertAlmostEqual(plan.parting_z, 10.0, delta=0.01)

    def test_scaled_info_scales_silhouette(self):
        info = dataclasses.replace(helpers.box_info(sz=20), silhouette_z=(10.0, 20.0))
        scaled = info.scaled(1.0, 1.0, 1.1)
        self.assertAlmostEqual(scaled.silhouette_z[0], 10.0)
        self.assertAlmostEqual(scaled.silhouette_z[1], 21.0)


class TwoSidedDraftTest(unittest.TestCase):
    def test_walls_leaning_toward_parting_plane_pass(self):
        # lower wall: normal slightly downward-outward => asin(-n.w) > 0; upper: mirrored
        n = math.sin(math.radians(2.0))
        samples = [(10.0, n, 2.0), (10.0, -n, 8.0)]  # (area, n.w, z); pz = 5
        # lower wall n.w=+sin(2deg) means tilting up => undercut; so use the opposite sign for a pass
        bad = draft.analyze_two_sided(samples, 5.0, 1.0)
        self.assertGreater(bad.undercut_frac, 0.9)
        good = draft.analyze_two_sided([(10.0, -n, 2.0), (10.0, n, 8.0)], 5.0, 1.0)
        self.assertEqual(good.undercut_area, 0.0)
        self.assertEqual(good.insufficient_area, 0.0)

    def test_insufficient_draft_reported(self):
        n = math.sin(math.radians(0.5))
        rep = draft.analyze_two_sided([(10.0, -n, 2.0), (10.0, n, 8.0)], 5.0, 2.0)
        self.assertAlmostEqual(rep.insufficient_frac, 1.0)

    def test_faces_on_the_parting_plane_are_ignored(self):
        rep = draft.analyze_two_sided([(10.0, 1.0, 4.95), (10.0, -1.0, 5.05)], 5.0, 1.0)
        self.assertEqual(rep.total_area, 0.0)


class BuildTest(unittest.TestCase):
    def test_build_cuts_pin_holes_in_both_halves_and_commits(self):
        plan, fa = run_build(helpers.box_info())
        self.assertEqual([name for name, _ in fa.committed], ["Core insert", "Cavity insert"])
        lower = dict(fa.committed[0][1])["lower"]
        upper = dict(fa.committed[1][1])["upper"]
        n = len(plan.keys)
        self.assertGreaterEqual(n, 2)
        block = next(b for b in fa.bodies if b.kind == "box" and ("cut", "master") in b.ops)
        base = FakeAdapter.count(block, "cut", "cyl")  # sprue, bolts... shared by both halves
        self.assertEqual(FakeAdapter.count(lower, "cut", "cyl"), base + n)
        self.assertEqual(FakeAdapter.count(upper, "cut", "cyl"), base + n)
        self.assertEqual(FakeAdapter.count(lower, "union", "cyl"), 0)  # holes, not printed bumps

    def test_slots_are_cut_before_the_split(self):
        plan, fa = run_build(helpers.box_info())
        if any(v.kind == "slot" for v in plan.vents):
            self.assertTrue(any(b.kind == "slot" for b in fa.bodies))

    def test_gate_is_cut_from_the_block(self):
        plan, fa = run_build(helpers.box_info(), sprue_location="edge")
        self.assertIn("gate", plan.extras)
        block = next(b for b in fa.bodies if b.kind == "box" and ("cut", "master") in b.ops)
        cylinders = FakeAdapter.count(block, "cut", "cyl")
        self.assertGreaterEqual(cylinders, 3)  # runner + gate + bolts at least

    def test_draft_applied_only_when_asked(self):
        _, fa = run_build(helpers.box_info())
        self.assertFalse(getattr(fa, "draft_applied", False))
        _, fa = run_build(helpers.box_info(), apply_draft=True)
        self.assertTrue(fa.draft_applied)
        _, fa = run_build(helpers.box_info(), apply_draft=True, draft_deg=0)
        self.assertFalse(getattr(fa, "draft_applied", False))

    def test_draft_report_becomes_warning(self):
        plan = plan_for(helpers.box_info())
        fa = FakeAdapter(plan)
        fa.draft = [(100.0, 0.0, 2.0), (100.0, 0.0, 8.0)]  # vertical walls: no draft
        strategies.get_strategy("core_cavity").build(plan, fa)
        self.assertTrue(any("draft" in w.lower() for w in fa.warnings))

    def test_lay_flat_flips_upper(self):
        _, fa = run_build(helpers.box_info())
        self.assertEqual(len(fa.flat), 1)


if __name__ == "__main__":
    unittest.main()
