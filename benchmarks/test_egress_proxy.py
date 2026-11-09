import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "sandbox"))
import egress_proxy  # noqa: E402


class AllowedTest(unittest.TestCase):
    def test_default_allows_only_claude_api(self):
        self.assertTrue(egress_proxy.allowed("api.anthropic.com", {}))
        self.assertFalse(egress_proxy.allowed("api.github.com", {}))

    def test_custom_list(self):
        env = {"BENCH_EGRESS_ALLOW": "a.example, b.example"}
        self.assertTrue(egress_proxy.allowed("a.example", env))
        self.assertTrue(egress_proxy.allowed("b.example", env))
        self.assertFalse(egress_proxy.allowed("api.anthropic.com", env))

    def test_denied_host(self):
        env = {"BENCH_EGRESS_ALLOW": "a.example"}
        self.assertFalse(egress_proxy.allowed("evil.example", env))


if __name__ == "__main__":
    unittest.main()
