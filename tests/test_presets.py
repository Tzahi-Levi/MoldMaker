import copy
import json
import unittest

from MoldMaker.core import model, presets


class PresetsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lib = presets.load_presets()
        with open(presets.default_path(), encoding="utf-8") as fh:
            cls.raw = json.load(fh)

    def test_bundled_file_valid(self):
        self.assertEqual(presets.validate_presets(self.raw), [])

    def test_expected_materials_present(self):
        for cid in ("mold_silicone_platinum", "mold_silicone_tin", "cast_platinum_silicone", "cast_tin_silicone",
                    "polyurethane", "epoxy", "polyester", "plaster", "concrete", "wax", "pewter_lowmelt",
                    "chocolate_food", "soap", "injection_ABS", "injection_PP", "injection_HDPE", "injection_PLA",
                    "plastisol_soft", "vacuum_forming", "slip_casting", "compression"):
            self.assertIn(cid, self.lib.casting)

    def test_spec_values(self):
        c = self.lib.casting
        self.assertEqual(c["injection_ABS"].defaults["shrink_pct"], 0.6)
        self.assertEqual(c["injection_PP"].defaults["shrink_pct"], 2.0)
        self.assertEqual(c["injection_HDPE"].defaults["shrink_pct"], 2.5)
        self.assertEqual(c["injection_PLA"].defaults["shrink_pct"], 0.4)
        self.assertEqual(c["slip_casting"].defaults["shrink_pct"], 12)
        self.assertEqual(c["pewter_lowmelt"].defaults["funnel_d_mm"], 12)
        self.assertEqual(self.lib.mold_materials["PLA"].max_service_C, 55)
        self.assertEqual(self.lib.mold_materials["SLA_high_temp"].max_service_C, 238)
        self.assertEqual(self.lib.mold_materials["silicone_hightemp"].max_service_C, 294)

    def test_default_type_is_allowed_and_known(self):
        for c in self.lib.casting.values():
            self.assertIn(c.default_mold_type, c.allowed_mold_types)
            for t in c.allowed_mold_types:
                self.assertIn(t, model.MOLD_TYPES)

    def test_printed_wall_override(self):
        self.assertEqual(self.lib.defaults_for("polyurethane", "silicone_box")["wall_mm"], 10)
        self.assertEqual(self.lib.defaults_for("polyurethane", "two_part")["wall_mm"], 4)

    def test_mold_material_choices_recommended_first(self):
        ids = [m.id for m in self.lib.mold_material_choices("pewter_lowmelt")]
        self.assertEqual(ids[:2], ["silicone_hightemp", "aluminum"])
        self.assertEqual(len(ids), len(self.lib.mold_materials))

    def _mutate(self, fn):
        raw = copy.deepcopy(self.raw)
        fn(raw)
        return presets.validate_presets(raw)

    def test_schema_rejects_bad_data(self):
        cm = lambda r: r["casting_materials"][0]  # noqa: E731
        self.assertTrue(self._mutate(lambda r: cm(r).update(default_mold_type="two_part")))
        self.assertTrue(self._mutate(lambda r: cm(r).update(allowed_mold_types=["nope"])))
        self.assertTrue(self._mutate(lambda r: cm(r).update(recommended_mold_materials=["unobtainium"])))
        self.assertTrue(self._mutate(lambda r: cm(r)["defaults"].update(wall_mm="ten")))
        self.assertTrue(self._mutate(lambda r: cm(r)["defaults"].update(key_type="cube")))
        self.assertTrue(self._mutate(lambda r: r["casting_materials"][1].update(id=cm(r)["id"])))
        self.assertTrue(self._mutate(lambda r: cm(r).update(
            recommended_mold_materials=["PLA"], forbidden_mold_materials=["PLA"])))
        self.assertTrue(self._mutate(lambda r: r.pop("mold_materials")))

    def test_load_missing_file(self):
        with self.assertRaises(presets.PresetError):
            presets.load_presets("definitely/not/here.json")


if __name__ == "__main__":
    unittest.main()
