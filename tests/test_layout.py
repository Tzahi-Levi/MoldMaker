import math
import unittest

from MoldMaker.core import layout, parting
from MoldMaker.core.model import BBox

from . import helpers

BODIES = {
    "sphere": helpers.sphere_info,
    "box": helpers.box_info,
    "L": helpers.l_bracket_info,
    "mushroom": helpers.mushroom_info,
}


def scaled_complete(info):
    return parting.complete_info(info)


class BlockTest(unittest.TestCase):
    def test_block_from_cavity(self):
        cav = BBox((0, 0, 0), (40, 30, 20))
        b = layout.block_from_cavity(cav, 10, 8)
        self.assertEqual(b.min, (-10, -10, -8))
        self.assertEqual(b.max, (50, 40, 28))
        o = layout.block_from_cavity(cav, 10, 8, open_top=True)
        self.assertEqual(o.max[2], 20)

    def test_obstacle_clearance(self):
        o = layout.Obstacle(0, 0, 10, 0, 1)
        self.assertAlmostEqual(o.clearance(5, 3), 2.0)
        self.assertAlmostEqual(o.clearance(-3, 0), 2.0)
        self.assertAlmostEqual(layout.Obstacle(0, 0, 0, 0, 2).clearance(3, 4), 3.0)


class FeatureInvariantsTest(unittest.TestCase):
    def run_case(self, name, wall, **kw):
        info = scaled_complete(BODIES[name]())
        p = helpers.params(wall_mm=wall, floor_top_mm=wall, **kw)
        block = layout.block_from_cavity(info.bbox, wall, wall)
        z = (info.bbox.min[2] + info.bbox.max[2]) / 2
        feats = layout.plan_features(info, block, p, wall, z)
        return info, p, block, feats

    def assert_invariants(self, info, p, block, feats):
        fp = layout.footprint_of(info)
        (x0, y0, _), (x1, y1, _) = block.min, block.max

        circles = []  # (x, y, r, label) of every placed round feature
        if feats.sprue and feats.sprue.location == "top":
            circles.append((feats.sprue.x, feats.sprue.y, feats.sprue.funnel_d_mm / 2, "sprue"))
        for v in feats.vents:
            if v.edge_to is None:
                circles.append((v.x, v.y, v.d_mm / 2, "vent"))
        for k in feats.keys:
            circles.append((k.x, k.y, k.d_mm / 2, "key"))
            self.assertTrue(fp.is_clear(k.x, k.y, k.d_mm / 2 + 2 - 1e-6), "key too close to cavity")
            self.assertTrue(x0 + k.d_mm / 2 <= k.x <= x1 - k.d_mm / 2 and y0 + k.d_mm / 2 <= k.y <= y1 - k.d_mm / 2,
                            "key outside block")
        for b in feats.bolts:
            r_out = max(b.cbore_d_mm, b.hole_d_mm) / 2
            circles.append((b.x, b.y, r_out, "bolt"))
            self.assertTrue(fp.is_clear(b.x, b.y, b.hole_d_mm / 2 + 2 - 1e-6), "bolt hole too close to cavity")
            self.assertTrue(x0 + r_out <= b.x <= x1 - r_out and y0 + r_out <= b.y <= y1 - r_out, "bolt outside block")
        # pairwise: no overlap, except the sprue/vent circles which live in the cavity
        movable = [c for c in circles if c[3] in ("key", "bolt")]
        for c in movable:
            for d in circles:
                if d is c:
                    continue
                self.assertGreaterEqual(math.hypot(c[0] - d[0], c[1] - d[1]), c[2] + d[2] - 1e-6,
                                        f"{c[3]} overlaps {d[3]}")

    def test_invariants_across_bodies_and_walls(self):
        for name in BODIES:
            for wall in (10, 15, 25):
                for kc in (2, 4):
                    with self.subTest(body=name, wall=wall, keys=kc):
                        self.assert_invariants(*self.run_case(name, wall, key_count=kc))

    def test_edge_sprue_invariants(self):
        for name in BODIES:
            with self.subTest(body=name):
                self.assert_invariants(*self.run_case(name, 15, sprue_location="edge"))

    def test_generous_wall_places_everything(self):
        for name in ("sphere", "mushroom", "box"):
            with self.subTest(body=name):
                _, p, _, f = self.run_case(name, 25, key_count=4, bolt_count=4)
                self.assertEqual(len(f.keys), 4)
                self.assertEqual(len(f.bolts), 4)
                self.assertEqual([w for w in f.warnings if "Could not" in w], [])

    def test_default_wall_places_keys_on_box(self):
        _, _, _, f = self.run_case("box", 10, key_count=4)
        self.assertGreaterEqual(len(f.keys), 2)

    def test_thin_wall_warns_instead_of_overlapping(self):
        _, p, _, f = self.run_case("box", 4, key_d_mm=6)
        self.assertTrue(f.warnings)

    def test_sprue_reaches_highest_point_and_vents_skip_it(self):
        info = scaled_complete(helpers.sphere_info(15))
        p = helpers.params(wall_mm=15, floor_top_mm=15)
        block = layout.block_from_cavity(info.bbox, 15, 15)
        s, _ = layout.place_sprue(info, block, p, 0.0)
        self.assertEqual(s.location, "top")
        self.assertAlmostEqual(s.z_from, info.high_points[0][2] - 0.5)
        self.assertEqual(s.z_to, block.max[2])
        vents, _ = layout.place_vents(info, block, p, s, 0.0)
        self.assertEqual(vents, [])

    def test_vents_for_secondary_peaks(self):
        def spans(x, y):
            if x <= 10:
                return [(0.0, 20.0 - 0.5 * abs(x - 5))]
            if x >= 30:
                return [(0.0, 15.0 - 0.5 * abs(x - 35))]
            return [(0.0, 5.0)]

        from MoldMaker.core.model import BodyInfo
        rays = helpers.make_rays(spans, (0, 40), (0, 10), 1.0)
        info = parting.complete_info(BodyInfo("two peaks", BBox((0, 0, 0), (40, 10, 20)), 1000.0, rays, 1.0))
        p = helpers.params(wall_mm=15, floor_top_mm=15)
        block = layout.block_from_cavity(info.bbox, 15, 15)
        s, _ = layout.place_sprue(info, block, p, 5.0)
        vents, _ = layout.place_vents(info, block, p, s, 5.0)
        self.assertGreaterEqual(len(vents), 1)
        self.assertGreater(vents[0].x, 20)
        self.assertEqual(vents[0].z_to, block.max[2])

    def test_vents_off_and_sprue_off(self):
        info = scaled_complete(helpers.box_info())
        block = layout.block_from_cavity(info.bbox, 10, 10)
        p = helpers.params(sprue_enabled=False, vents_auto=False)
        self.assertEqual(layout.place_sprue(info, block, p, 10.0)[0], None)
        self.assertEqual(layout.place_vents(info, block, p, None, 10.0)[0], [])

    def test_no_keys_when_none(self):
        _, _, _, f = self.run_case("sphere", 20, key_type="none")
        self.assertEqual(f.keys, [])

    def test_bolts_sit_along_long_edges(self):
        info, p, block, f = self.run_case("box", 25, bolt_count=4)
        sx, sy, _ = block.size
        self.assertGreater(sx, sy)  # long axis is x
        ys = {round(b.y, 6) for b in f.bolts}
        self.assertEqual(len(ys), 2)  # one band along each long edge

    def test_bolt_hardware_flags(self):
        _, _, _, f = self.run_case("sphere", 25, bolt_counterbore=False, bolt_nut_trap=False)
        for b in f.bolts:
            self.assertEqual(b.cbore_d_mm, 0.0)
            self.assertEqual(b.nut_af_mm, 0.0)

    def test_deterministic(self):
        a = self.run_case("mushroom", 20)[3]
        b = self.run_case("mushroom", 20)[3]
        self.assertEqual(a.keys, b.keys)
        self.assertEqual(a.bolts, b.bolts)


if __name__ == "__main__":
    unittest.main()
