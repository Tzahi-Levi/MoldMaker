import unittest

from MoldMaker.core import units


class UnitsTest(unittest.TestCase):
    def test_roundtrip(self):
        for v in (0, 1, 12.345, -3.2):
            self.assertAlmostEqual(units.cm_to_mm(units.mm_to_cm(v)), v)
            self.assertAlmostEqual(units.rad_to_deg(units.deg_to_rad(v)), v)
            self.assertAlmostEqual(units.cm3_to_mm3(units.mm3_to_cm3(v)), v)

    def test_values(self):
        self.assertAlmostEqual(units.mm_to_cm(25), 2.5)
        self.assertAlmostEqual(units.mm3_to_cm3(1000), 1.0)

    def test_expr(self):
        self.assertEqual(units.mm_expr(6), "6 mm")
        self.assertEqual(units.mm_expr(0.3), "0.3 mm")
        self.assertEqual(units.mm_expr(1e-7), "0 mm")
        self.assertEqual(units.mm_expr(12.5), "12.5 mm")
        self.assertEqual(units.deg_expr(1.5), "1.5 deg")


if __name__ == "__main__":
    unittest.main()
