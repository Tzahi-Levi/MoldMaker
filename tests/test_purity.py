"""Pure modules (core/, strategies/) must never import adsk."""
import os
import unittest

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "MoldMaker")


class PurityTest(unittest.TestCase):
    def test_no_adsk_in_pure_modules(self):
        checked = 0
        for sub in ("core", "strategies"):
            for dirpath, _, files in os.walk(os.path.join(ROOT, sub)):
                for name in files:
                    if name.endswith(".py"):
                        path = os.path.join(dirpath, name)
                        with open(path, encoding="utf-8") as fh:
                            text = fh.read()
                        self.assertNotIn("import adsk", text, f"'import adsk' found in {path}")
                        self.assertNotIn("from adsk", text, f"'from adsk' found in {path}")
                        checked += 1
        self.assertGreater(checked, 5)


if __name__ == "__main__":
    unittest.main()
