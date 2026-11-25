import unittest

from MoldMaker.core import model, ui_rules


class UiRulesTest(unittest.TestCase):
    def test_every_type_has_all_groups(self):
        for t in model.MOLD_TYPES:
            self.assertEqual(set(ui_rules.visible_groups(t)), set(ui_rules.GROUPS))

    def test_open_block_hides_split_groups(self):
        self.assertFalse(any(ui_rules.visible_groups("open_block").values()))
        self.assertFalse(ui_rules.parting_applies("open_block"))

    def test_two_part_shows_split_groups_but_not_shell(self):
        v = ui_rules.visible_groups("two_part")
        self.assertTrue(v["grp_registration"] and v["grp_pour"] and v["grp_clamping"])
        self.assertFalse(v["grp_shell"])
        self.assertTrue(ui_rules.parting_applies("two_part"))

    def test_silicone_box_variant(self):
        self.assertFalse(any(ui_rules.visible_groups("silicone_box", False).values()))
        v = ui_rules.visible_groups("silicone_box", True)
        self.assertTrue(v["grp_registration"] and v["grp_pour"] and not v["grp_clamping"])

    def test_brush_on_mother(self):
        v = ui_rules.visible_groups("brush_on_mother")
        self.assertTrue(v["grp_registration"] and v["grp_clamping"] and v["grp_shell"])
        self.assertFalse(v["grp_pour"])
        f = ui_rules.visible_shell_fields("brush_on_mother")
        self.assertTrue(f["skin"] and f["shell"] and f["flange_w"])
        self.assertFalse(f["plaster_t"] or f["vent_hole_d"])

    def test_slip_cast_and_vacuum_fields(self):
        f = ui_rules.visible_shell_fields("slip_cast_case")
        self.assertTrue(f["plaster_t"] and f["case_wall"] and f["well_h"] and f["well_d"])
        self.assertFalse(f["skin"])
        f = ui_rules.visible_shell_fields("vacuum_buck")
        self.assertTrue(f["shell"] and f["flange_w"] and f["vent_hole_d"])
        self.assertFalse(ui_rules.visible_groups("vacuum_buck")["grp_registration"])
        self.assertFalse(ui_rules.parting_applies("vacuum_buck"))

    def test_every_field_belongs_to_a_known_type(self):
        for types in ui_rules.SHELL_FIELDS.values():
            for t in types:
                self.assertIn(t, model.MOLD_TYPES)


if __name__ == "__main__":
    unittest.main()
