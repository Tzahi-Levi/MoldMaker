import unittest

from MoldMaker import strategies

from . import helpers
from .fake_adapter import FakeAdapter


def run(mold_type, body, removed_fraction=1.0, **kw):
    p = helpers.params(mold_type=mold_type, wall_mm=20, floor_top_mm=20, **kw)
    s = strategies.get_strategy(mold_type)
    plan = s.plan(p, body)
    fa = FakeAdapter(plan, removed_fraction)
    s.build(plan, fa)
    return plan, fa


class TwoPartBuildTest(unittest.TestCase):
    def setUp(self):
        self.plan, self.fa = run("two_part", helpers.sphere_info(15))
        (_, lo), (_, up) = self.fa.committed
        self.lower, self.upper = lo[0][1], up[0][1]

    def test_two_parts_committed_with_names(self):
        self.assertEqual([n for n, _ in self.fa.committed], ["Lower half", "Upper half"])
        self.assertEqual([b[0][0] for _, b in self.fa.committed], ["lower", "upper"])

    def test_keys_bump_on_lower_socket_in_upper(self):
        n = len(self.plan.keys)
        self.assertEqual(n, 4)
        self.assertEqual(self.fa.count(self.lower, "union", "sphere"), n)
        self.assertEqual(self.fa.count(self.upper, "cut", "sphere"), n)
        self.assertEqual(self.fa.count(self.lower, "cut", "sphere"), 0)

    def test_socket_larger_than_bump_by_clearance(self):
        radii = sorted({round(b.info["r"], 6) for b in self.fa.bodies if b.kind == "sphere"})
        self.assertEqual(radii, [3.0, 3.3])

    def test_cavity_cut_first_and_split_after(self):
        self.assertEqual(self.lower.ops[0], ("cut", "master"))
        self.assertEqual(self.upper.ops[0], ("cut", "master"))
        self.assertEqual(self.fa.count(self.lower, "intersect", "box"), 1)
        self.assertEqual(self.fa.count(self.upper, "intersect", "box"), 1)

    def test_pour_and_bolt_cuts_reach_both_halves(self):
        n = len(self.plan.bolts)
        self.assertEqual(n, 4)
        self.assertEqual(self.fa.count(self.lower, "cut", "hex"), n)
        self.assertEqual(self.fa.count(self.upper, "cut", "hex"), n)
        self.assertGreaterEqual(self.fa.count(self.lower, "cut", "cyl"), 1 + 2 * n)

    def test_sprue_cylinder_spans_cavity_top_to_block_top(self):
        s, b = self.plan.sprue, self.plan.block
        cyls = [x for x in self.fa.bodies if x.kind == "cyl" and abs(x.info["p0"][2] - s.z_from) < 1e-9]
        self.assertTrue(cyls)
        self.assertGreater(cyls[0].info["p1"][2], b.max[2])

    def test_lay_flat_moves_only_upper(self):
        self.assertEqual(self.fa.flat, [self.upper])
        _, fa = run("two_part", helpers.sphere_info(15), lay_flat=False)
        self.assertEqual(fa.flat, [])

    def test_no_warning_when_volume_matches(self):
        self.assertEqual(self.fa.warnings, [])

    def test_volume_mismatch_warns(self):
        _, fa = run("two_part", helpers.sphere_info(15), removed_fraction=0.9)
        self.assertTrue(any("Cavity volume check" in w for w in fa.warnings))

    def test_within_two_percent_is_silent(self):
        _, fa = run("two_part", helpers.sphere_info(15), removed_fraction=0.99)
        self.assertEqual(fa.warnings, [])

    def test_edge_sprue_and_no_keys_build(self):
        plan, fa = run("two_part", helpers.box_info(), sprue_location="edge", key_type="none", bolts_enabled=False)
        self.assertEqual(plan.keys, [])
        self.assertEqual(len(fa.committed), 2)


class SiliconeBuildTest(unittest.TestCase):
    def test_one_piece_box(self):
        plan, fa = run("silicone_box", helpers.box_info())
        self.assertEqual([n for n, _ in fa.committed], ["Box"])
        box = fa.committed[0][1][0][1]
        self.assertEqual(fa.count(box, "cut", "box"), 1)
        self.assertEqual(fa.count(box, "union", "cyl"), 1)  # locating post

    def test_two_part_variant_has_bed_keys_and_pin(self):
        plan, fa = run("silicone_box", helpers.sphere_info(15), silicone_two_part=True)
        self.assertEqual([n for n, _ in fa.committed], ["Box", "Parting bed"])
        names = [n for n, _ in fa.committed[1][1]]
        self.assertEqual(names[0], "bed")
        self.assertIn("spout_pin", names)
        bed = fa.committed[1][1][0][1]
        self.assertEqual(fa.count(bed, "cut", "master"), 1)
        self.assertEqual(fa.count(bed, "union", "sphere"), len(plan.keys))

    def test_edge_sprue_falls_back_to_top_pin(self):
        plan, fa = run("silicone_box", helpers.sphere_info(15), silicone_two_part=True, sprue_location="edge")
        self.assertEqual(plan.sprue.location, "top")
        self.assertTrue(any("Edge sprue" in w for w in plan.warnings))


class OpenBlockBuildTest(unittest.TestCase):
    def test_cavity_cut_with_extended_tool_and_single_part(self):
        plan, fa = run("open_block", helpers.box_info(), draft_deg=0.0)
        self.assertEqual([n for n, _ in fa.committed], ["Block"])
        block = fa.committed[0][1][0][1]
        self.assertEqual(fa.count(block, "cut", "master"), 1)
        tool = [b for b in fa.bodies if b.kind == "master"][0]
        self.assertEqual(fa.count(tool, "union", "box"), 1)  # slab above the flat back
        slab = [b for b in fa.bodies if b.kind == "box" and b.info["bbox"].min[2] == plan.cavity_bbox.max[2]][0]
        self.assertGreater(slab.info["bbox"].max[2], plan.block.max[2])

    def test_draft_warnings_surface(self):
        import math
        plan, fa = (None, None)
        p = helpers.params(mold_type="open_block", wall_mm=10, floor_top_mm=10, draft_deg=2.0)
        s = strategies.get_strategy("open_block")
        plan = s.plan(p, helpers.box_info())
        fa = FakeAdapter(plan)
        fa.draft = [(500.0, -1.0, 0.0), (500.0, 1.0, 20.0), (300.0, 0.0, 10.0)]  # vertical wall, 2 deg required
        s.build(plan, fa)
        self.assertTrue(any("draft" in w for w in fa.warnings))

    def test_clean_draft_has_no_warnings(self):
        import math
        p = helpers.params(mold_type="open_block", wall_mm=10, floor_top_mm=10, draft_deg=2.0)
        s = strategies.get_strategy("open_block")
        plan = s.plan(p, helpers.box_info())
        fa = FakeAdapter(plan)
        fa.draft = [(500.0, -1.0, 0.0), (500.0, 1.0, 20.0), (300.0, -math.sin(math.radians(3)), 10.0)]
        s.build(plan, fa)
        self.assertEqual(fa.warnings, [])


if __name__ == "__main__":
    unittest.main()
