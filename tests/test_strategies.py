import math
import unittest

from MoldMaker import strategies
from MoldMaker.core import model

from . import helpers


class FramesTest(unittest.TestCase):
    def test_frames_right_handed_and_orthonormal(self):
        for d in model.PULL_DIRECTIONS:
            f = model.frame_for(d)
            self.assertEqual(model.vcross(f.u, f.v), f.w, d)
            self.assertEqual(model.vdot(f.u, f.v), 0)
            self.assertEqual(sum(abs(c) for c in f.w), 1)

    def test_roundtrip(self):
        for d in model.PULL_DIRECTIONS:
            f = model.frame_for(d)
            p = (1.0, 2.0, 3.0)
            self.assertEqual(f.to_world(f.to_local(p)), p)

    def test_pull_axis_maps_to_w(self):
        self.assertEqual(model.frame_for("+X").to_local((5, 0, 0))[2], 5)
        self.assertEqual(model.frame_for("-Z").to_local((0, 0, 5))[2], -5)

    def test_bbox_to_local(self):
        bb = model.frame_for("-Z").bbox_to_local((0, 0, 0), (10, 20, 30))
        self.assertEqual(bb.min[2], -30)
        self.assertEqual(bb.max[2], 0)

    def test_nonuniform_factor_mapping(self):
        f = model.frame_for("+X")  # u=Y, v=Z, w=X
        self.assertEqual(f.local_factors((1.1, 1.2, 1.3)), (1.2, 1.3, 1.1))


class ParamsValidationTest(unittest.TestCase):
    def test_defaults_valid(self):
        self.assertEqual(helpers.params().validate(), [])

    def test_bad_values(self):
        self.assertTrue(helpers.params(wall_mm=0).validate())
        self.assertTrue(helpers.params(key_count=3).validate())
        self.assertTrue(helpers.params(shrink_pct=-80).validate())
        self.assertTrue(helpers.params(funnel_d_mm=2, sprue_d_mm=6).validate())
        self.assertTrue(helpers.params(vents_mandatory=True, vents_auto=False).validate())


class StrategyPlanTest(unittest.TestCase):
    def test_registry(self):
        self.assertEqual(set(strategies.implemented_types()), {"silicone_box", "two_part", "open_block", "brush_on_mother", "slip_cast_case", "vacuum_buck", "core_cavity"})
        self.assertIsNone(strategies.get_strategy("nonexistent"))

    def test_two_part_plan_sphere(self):
        p = helpers.params(wall_mm=20, floor_top_mm=20, shrink_pct=0)
        plan = strategies.get_strategy("two_part").plan(p, helpers.sphere_info(15))
        self.assertAlmostEqual(plan.parting_z, 0.0, delta=0.8)
        self.assertEqual([x.id for x in plan.parts], ["lower", "upper"])
        self.assertEqual(plan.block.size, (70.0, 70.0, 70.0))
        self.assertEqual(len(plan.keys), 4)
        self.assertIsNotNone(plan.sprue)
        self.assertEqual(plan.group_name, "MoldMaker - Two-part rigid mold")
        self.assertEqual(plan.component_name, "Mold - sphere")
        self.assertAlmostEqual(plan.metrics["Expected cavity volume (cm3)"], 4 / 3 * math.pi * 15 ** 3 / 1000)

    def test_two_part_shrink_scales_cavity_and_volume(self):
        p = helpers.params(wall_mm=10, floor_top_mm=10, shrink_pct=10)
        plan = strategies.get_strategy("two_part").plan(p, helpers.box_info(40, 30, 20))
        self.assertAlmostEqual(plan.cavity_bbox.size[0], 44.0)
        self.assertAlmostEqual(plan.cavity_bbox.size[2], 22.0)
        self.assertAlmostEqual(plan.metrics["Expected cavity volume (cm3)"], 40 * 30 * 20 * 1.331 / 1000)

    def test_two_part_nonuniform_shrink_respects_pull_frame(self):
        # pull along +X: world X shrink must scale the local w axis
        p = helpers.params(pull_dir="+X", shrink_xyz_pct=(10.0, 0.0, 0.0))
        plan = strategies.get_strategy("two_part").plan(p, helpers.box_info(40, 30, 20))
        self.assertAlmostEqual(plan.cavity_bbox.size[2], 22.0)
        self.assertAlmostEqual(plan.cavity_bbox.size[0], 40.0)

    def test_manual_parting_offset_and_clamp(self):
        s = strategies.get_strategy("two_part")
        plan = s.plan(helpers.params(parting_mode="manual", parting_offset_mm=3), helpers.box_info(sz=20))
        self.assertAlmostEqual(plan.parting_z, 13.0)
        plan = s.plan(helpers.params(parting_mode="manual", parting_offset_mm=99), helpers.box_info(sz=20))
        self.assertLess(plan.parting_z, 20)
        self.assertTrue(any("clamped" in w for w in plan.warnings))

    def test_mushroom_undercut_free_parting(self):
        plan = strategies.get_strategy("two_part").plan(helpers.params(), helpers.mushroom_info())
        self.assertFalse(any("undercut" in w for w in plan.warnings))

    def test_undercut_warning(self):
        # two lobes at different heights: no single plane crosses both
        from MoldMaker.core.model import BBox, BodyInfo

        def spans(x, y):
            return [(0.0, 10.0)] if x < 0 else [(20.0, 30.0)]

        rays = helpers.make_rays(spans, (-10, 10), (-10, 10), 1.0)
        info = BodyInfo("lobes", BBox((-10, -10, 0), (10, 10, 30)), 4000.0, rays, 1.0)
        plan = strategies.get_strategy("two_part").plan(helpers.params(wall_mm=20, floor_top_mm=20), info)
        self.assertTrue(any("undercut" in w for w in plan.warnings))

    def test_open_block_plan(self):
        p = helpers.params(mold_type="open_block", wall_mm=8, floor_top_mm=8, draft_deg=2)
        plan = strategies.get_strategy("open_block").plan(p, helpers.box_info(40, 30, 20))
        self.assertIsNone(plan.parting_z)
        self.assertEqual(len(plan.parts), 1)
        self.assertEqual(plan.block.max[2], 20)  # open top flush with the cavity top
        self.assertEqual(plan.block.min[2], -8)
        self.assertEqual((plan.keys, plan.bolts, plan.vents, plan.sprue), ([], [], [], None))

    def test_open_block_zero_draft_warns(self):
        plan = strategies.get_strategy("open_block").plan(helpers.params(mold_type="open_block"), helpers.box_info())
        self.assertTrue(any("Draft" in w for w in plan.warnings))

    def test_silicone_box_plan_volumes(self):
        p = helpers.params(mold_type="silicone_box", wall_mm=10, floor_top_mm=10, box_wall_mm=2.4,
                           silicone_density_g_cc=1.08)
        plan = strategies.get_strategy("silicone_box").plan(p, helpers.box_info(40, 30, 20))
        self.assertEqual(plan.inner_block.size, (60.0, 50.0, 40.0))
        self.assertAlmostEqual(plan.block.size[0], 64.8)
        self.assertAlmostEqual(plan.block.size[2], 40 + 2.4)  # floor plate only, top open
        vol = (60 * 50 * 40 - 40 * 30 * 20) / 1000
        self.assertAlmostEqual(plan.metrics["Silicone volume (cm3)"], vol)
        self.assertAlmostEqual(plan.metrics["Silicone mass (g)"], vol * 1.08)
        self.assertEqual(len(plan.posts), 1)
        self.assertEqual([x.id for x in plan.parts], ["box"])
        self.assertIsNone(plan.parting_z)

    def test_silicone_box_two_part_variant(self):
        p = helpers.params(mold_type="silicone_box", wall_mm=20, floor_top_mm=20, silicone_two_part=True)
        plan = strategies.get_strategy("silicone_box").plan(p, helpers.sphere_info(15))
        self.assertEqual([x.id for x in plan.parts], ["box", "bed"])
        self.assertAlmostEqual(plan.parting_z, 0.0, delta=0.8)
        self.assertGreaterEqual(len(plan.keys), 2)
        self.assertIsNotNone(plan.sprue)
        self.assertEqual(plan.bolts, [])

    def test_summary_runs(self):
        plan = strategies.get_strategy("two_part").plan(helpers.params(), helpers.box_info())
        self.assertIn("Parting height", plan.summary())

    def test_invalid_params_raise(self):
        with self.assertRaises(ValueError):
            strategies.get_strategy("two_part").plan(helpers.params(wall_mm=-1), helpers.box_info())


if __name__ == "__main__":
    unittest.main()
