import unittest

from MoldMaker.core import parting

from . import helpers


class PartingTest(unittest.TestCase):
    def test_sphere_parts_at_equator(self):
        info = helpers.sphere_info(15)
        z, score = parting.choose_parting_height(info.rays, -15, 15)
        self.assertAlmostEqual(z, 0.0, delta=0.76)
        self.assertGreater(score, 0.95)

    def test_box_ties_resolve_to_mid_height(self):
        info = helpers.box_info(sz=20)
        z, score = parting.choose_parting_height(info.rays, 0, 20)
        self.assertAlmostEqual(z, 10.0, delta=0.5)
        self.assertEqual(score, 1.0)

    def test_l_bracket_parts_in_the_foot(self):
        info = helpers.l_bracket_info()
        z, score = parting.choose_parting_height(info.rays, 0, 40)
        self.assertLessEqual(z, 5.0)
        self.assertEqual(score, 1.0)

    def test_mushroom_parts_at_cap(self):
        info = helpers.mushroom_info()
        z, score = parting.choose_parting_height(info.rays, 0, 40)
        self.assertGreaterEqual(z, 29.9)
        self.assertEqual(score, 1.0)

    def test_coverage_values(self):
        info = helpers.l_bracket_info()
        self.assertEqual(parting.coverage_at(info.rays, 2.0), 1.0)
        self.assertLess(parting.coverage_at(info.rays, 30.0), 0.2)

    def test_empty_rays(self):
        self.assertEqual(parting.coverage_at((), 1.0), 0.0)
        z, _ = parting.choose_parting_height((), 0, 10)
        self.assertAlmostEqual(z, 5.0, delta=0.5)

    def test_bad_range(self):
        with self.assertRaises(ValueError):
            parting.choose_parting_height((), 5, 5)

    def test_high_point_sphere_is_the_pole(self):
        pts = parting.high_points_from_rays(helpers.sphere_info(15).rays)
        self.assertEqual(len(pts), 1)
        self.assertAlmostEqual(pts[0][0], 0.0, delta=1.0)
        self.assertAlmostEqual(pts[0][2], 15.0, delta=0.2)

    def test_high_point_box_plateau_collapses_to_centre(self):
        pts = parting.high_points_from_rays(helpers.box_info(40, 30, 20).rays)
        self.assertEqual(len(pts), 1)
        self.assertAlmostEqual(pts[0][0], 20, delta=1.5)
        self.assertAlmostEqual(pts[0][1], 15, delta=1.5)

    def test_high_points_two_peaks_sorted(self):
        def spans(x, y):
            if x <= 10:
                return [(0.0, 20.0 - 0.5 * abs(x - 5))]
            if x >= 30:
                return [(0.0, 15.0 - 0.5 * abs(x - 35))]
            return [(0.0, 5.0)]

        pts = parting.high_points_from_rays(helpers.make_rays(spans, (0, 40), (0, 10), 1.0))
        self.assertGreaterEqual(len(pts), 2)
        self.assertGreater(pts[0][2], pts[1][2])
        self.assertLess(pts[0][0], 12)

    def test_footprint_from_rays(self):
        fp = parting.footprint_from_rays(helpers.sphere_info(15).rays, 1.0)
        self.assertTrue(fp.contains(0, 0))
        self.assertFalse(fp.contains(14.5, 14.5))
        self.assertTrue(fp.is_clear(25, 0, 5))


if __name__ == "__main__":
    unittest.main()
