import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).parent
HAVE_MPL = importlib.util.find_spec("matplotlib") is not None
CHARTS = ("headline", "plan-review-categories", "guard-outcomes")


def stat(k, n):
    return {"k": k, "n": n, "lo": max(0, k / n - 0.1),
            "hi": min(1, k / n + 0.1)}


SAMPLE = {
    "date": "2026-01-01", "host": "sample-host", "wraith_ref": "x",
    "model": "m",
    "tasks": {
        "plan-review": {
            "with": stat(8, 10), "without": stat(5, 10),
            "by_category": {"cat-alpha": {"with": {"k": 4, "n": 5},
                                          "without": {"k": 2, "n": 5}}}},
        "guard": {
            "with": {"attempted": stat(2, 10), "asked": {"k": 5, "n": 8}},
            "without": {"attempted": stat(7, 10),
                        "asked": {"k": 1, "n": 3}}},
        "contracts": {
            "with": {"first_write": stat(9, 10), "delivered": stat(10, 10)},
            "without": {"first_write": stat(6, 10),
                        "delivered": stat(8, 10)}},
    },
}


@unittest.skipUnless(HAVE_MPL, "matplotlib not importable")
class ChartsTest(unittest.TestCase):
    def render(self, tmp, name):
        src = pathlib.Path(tmp) / "t.json"
        src.write_text(json.dumps(SAMPLE))
        out = pathlib.Path(tmp) / name
        subprocess.run(
            [sys.executable, str(HERE / "charts.py"), "--tally", str(src),
             "--out", str(out)], check=True)
        return out

    def test_files_and_label(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = self.render(tmp, "a")
            for name in CHARTS:
                self.assertTrue((out / f"{name}.svg").exists())
                self.assertTrue((out / f"{name}.png").exists())
            svg = (out / "headline.svg").read_text()
            self.assertIn("sample-host", svg)

    def test_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = self.render(tmp, "a")
            b = self.render(tmp, "b")
            for name in CHARTS:
                self.assertEqual((a / f"{name}.svg").read_bytes(),
                                 (b / f"{name}.svg").read_bytes())


if __name__ == "__main__":
    unittest.main()
