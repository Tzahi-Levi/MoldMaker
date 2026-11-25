import unittest

from MoldMaker.core import compat, presets


class CompatTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lib = presets.load_presets()

    def chk(self, casting, mold_type, mold_material):
        return compat.check(self.lib, casting, mold_type, mold_material)

    def test_pewter_pla_error(self):
        self.assertFalse(self.chk("pewter_lowmelt", "open_block", "PLA").ok)

    def test_pewter_other_unsuitable_materials_error(self):
        self.assertFalse(self.chk("pewter_lowmelt", "open_block", "PETG").ok)
        self.assertFalse(self.chk("pewter_lowmelt", "open_block", "SLA_standard").ok)
        self.assertFalse(self.chk("pewter_lowmelt", "open_block", "SLA_high_temp").ok)  # 250 C > 238 C

    def test_pewter_aluminum_ok(self):
        self.assertTrue(self.chk("pewter_lowmelt", "open_block", "aluminum").ok)

    def test_pewter_silicone_box_with_pla_box_is_only_warning(self):
        r = self.chk("pewter_lowmelt", "silicone_box", "PLA")
        self.assertTrue(r.ok)
        self.assertTrue(any("PLA" in w for w in r.warnings))

    def test_pewter_hightemp_silicone_ok(self):
        self.assertTrue(self.chk("pewter_lowmelt", "silicone_box", "silicone_hightemp").ok)

    def test_wax_pla_error(self):
        self.assertFalse(self.chk("wax", "two_part", "PLA").ok)

    def test_injection_requires_hot_mold(self):
        self.assertFalse(self.chk("injection_ABS", "core_cavity", "PETG").ok)
        self.assertFalse(self.chk("injection_ABS", "core_cavity", "PLA").ok)
        self.assertTrue(self.chk("injection_ABS", "core_cavity", "aluminum").ok)
        self.assertTrue(self.chk("injection_ABS", "core_cavity", "SLA_high_temp").ok)

    def test_unsupported_mold_type_error(self):
        self.assertFalse(self.chk("polyester", "two_part", "PLA").ok)

    def test_epoxy_pla_warns_not_errors(self):
        r = self.chk("epoxy", "silicone_box", "PLA")
        self.assertTrue(r.ok)
        self.assertTrue(any("recommended" in w for w in r.warnings))
        self.assertTrue(any("xotherm" in w for w in r.warnings))

    def test_platinum_inhibition_warning_present(self):
        r = self.chk("mold_silicone_platinum", "silicone_box", "PLA")
        self.assertTrue(any("inhibited" in w for w in r.warnings))

    def test_release_note_and_warning_reported(self):
        r = self.chk("concrete", "open_block", "PETG")
        self.assertTrue(any("Oil-based" in n for n in r.notes))
        self.assertTrue(any("Abrasive" in w for w in r.warnings))

    def test_low_confidence_flagged(self):
        r = self.chk("compression", "core_cavity", "aluminum")
        self.assertTrue(any("low-confidence" in w for w in r.warnings))

    def test_every_default_combo_has_no_error(self):
        for c in self.lib.casting.values():
            r = self.chk(c.id, c.default_mold_type, c.recommended_mold_materials[0])
            self.assertTrue(r.ok, f"{c.id}: {r.errors}")


if __name__ == "__main__":
    unittest.main()
