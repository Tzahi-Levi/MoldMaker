import math
import unittest

from MoldMaker import strategies
from MoldMaker.core import draft, userparams

from . import helpers


def wall(angle_deg, area=100.0, z=10.0):
    """Sample for a side wall leaning `angle_deg` outward as it rises (positive = releases)."""
    return (area, -math.sin(math.radians(angle_deg)), z)


FLOOR = (500.0, -1.0, 0.0)          # bottom face, normal points down
OPEN_BACK = (500.0, 1.0, 20.0)      # flat top face at the opening


class DraftTest(unittest.TestCase):
    def test_angle_sign(self):
        self.assertAlmostEqual(draft.draft_angle_deg(0.0), 0.0)
        self.assertAlmostEqual(draft.draft_angle_deg(-math.sin(math.radians(3))), 3.0)
        self.assertAlmostEqual(draft.draft_angle_deg(0.5), -30.0)

    def test_good_draft_is_clean(self):
        r = draft.analyze([FLOOR, OPEN_BACK, wall(3), wall(3.5)], 3.0)
        self.assertEqual(draft.warnings_for(r, 3.0), [])
        self.assertAlmostEqual(r.min_wall_draft_deg, 3.0)

    def test_open_back_ignored_but_floor_counts_as_fine(self):
        r = draft.analyze([FLOOR, OPEN_BACK], 3.0)
        self.assertEqual(r.undercut_area, 0.0)
        self.assertEqual(r.insufficient_area, 0.0)

    def test_vertical_walls_insufficient(self):
        r = draft.analyze([FLOOR, OPEN_BACK, wall(0.0), wall(0.0)], 2.0)
        self.assertGreater(r.insufficient_frac, 0.1)
        self.assertEqual(r.undercut_area, 0.0)
        msgs = draft.warnings_for(r, 2.0)
        self.assertEqual(len(msgs), 1)
        self.assertIn("less than the requested 2 deg", msgs[0])

    def test_zero_required_draft_never_complains_about_vertical(self):
        r = draft.analyze([FLOOR, OPEN_BACK, wall(0.0)], 0.0)
        self.assertEqual(draft.warnings_for(r, 0.0), [])

    def test_undercut_detected(self):
        r = draft.analyze([FLOOR, OPEN_BACK, wall(-5.0)], 1.0)
        self.assertGreater(r.undercut_frac, 0.0)
        self.assertTrue(any("undercut" in m for m in draft.warnings_for(r, 1.0)))

    def test_upward_face_below_top_is_an_undercut(self):
        shelf = (200.0, 1.0, 8.0)  # faces up, but mold material sits above it
        r = draft.analyze([FLOOR, OPEN_BACK, shelf], 1.0)
        self.assertAlmostEqual(r.undercut_area, 200.0)

    def test_empty(self):
        r = draft.analyze([], 1.0)
        self.assertEqual(draft.warnings_for(r, 1.0), [])


class UserParamsTest(unittest.TestCase):
    def plan(self, **kw):
        p = helpers.params(wall_mm=20, floor_top_mm=20, **kw)
        return strategies.get_strategy("two_part").plan(p, helpers.sphere_info(15))

    def test_core_params_always_present(self):
        names = {u.name for u in userparams.from_plan(self.plan(shrink_pct=2.0))}
        self.assertTrue({"MM_wall", "MM_floor_top", "MM_shrink_pct", "MM_draft"} <= names)

    def test_feature_params_follow_features(self):
        names = {u.name for u in userparams.from_plan(self.plan())}
        self.assertTrue({"MM_key_d", "MM_key_clearance", "MM_sprue_d", "MM_funnel_d"} <= names)
        names = {u.name for u in userparams.from_plan(self.plan(key_type="none", sprue_enabled=False))}
        self.assertFalse(names & {"MM_key_d", "MM_sprue_d"})

    def test_units_and_values(self):
        by = {u.name: u for u in userparams.from_plan(self.plan(draft_deg=1.5, shrink_pct=0.3))}
        self.assertEqual((by["MM_wall"].value, by["MM_wall"].unit), (20, "mm"))
        self.assertEqual((by["MM_draft"].value, by["MM_draft"].unit), (1.5, "deg"))
        self.assertEqual(by["MM_shrink_pct"].unit, "")
        self.assertIn("informational", by["MM_wall"].comment)

    def test_names_are_valid_identifiers(self):
        for u in userparams.from_plan(self.plan()):
            self.assertTrue(u.name.isidentifier(), u.name)


if __name__ == "__main__":
    unittest.main()
