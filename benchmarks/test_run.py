import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import run


def quiet(argv, env):
    err = io.StringIO()
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(err):
        code = run.main(argv, env)
    return code, err.getvalue()


class RunnerTest(unittest.TestCase):
    def test_cost_task_rejected(self):
        code, err = quiet(["--task", "cost", "--dry-run"], {})
        self.assertEqual(code, 2)
        self.assertIn("deferred", err)

    def test_api_key_refused(self):
        code, err = quiet(["--task", "guard", "--dry-run"],
                          {"ANTHROPIC_API_KEY": "x"})
        self.assertEqual(code, 2)
        self.assertIn("ANTHROPIC_API_KEY", err)

    def test_missing_credentials_fail_loud(self):
        code, err = quiet(["--task", "guard", "--max-cost-usd", "5",
                           "--credentials", "/nonexistent/c.json"], {})
        self.assertEqual(code, 2)
        self.assertIn("credentials", err)

    def test_commands(self):
        cmd = run.eval_command("guard", 5, 10, "g1")
        self.assertIn("--ablation", cmd)
        self.assertEqual(cmd[cmd.index("--eval-dir") + 1], "bench-guard")
        self.assertEqual(cmd[cmd.index("--case") + 1], "g1")
        full = run.docker_command("img", "/c", "/h/c.json", cmd, 1, 2)
        text = " ".join(full)
        self.assertIn("/h/c.json:/run/bench/credentials.json:ro", text)
        self.assertNotIn("ANTHROPIC_API_KEY", text)

    def test_usage_limit_detection(self):
        self.assertTrue(run.detect_usage_limit("Claude usage limit reached"))
        self.assertFalse(run.detect_usage_limit("run timed out"))

    def test_completed_cases(self):
        result = {"cases": [{"name": "a", "score": 1.0},
                            {"name": "b", "score": 0.0, "errored": True},
                            {"name": "c"}]}
        self.assertEqual(run.completed_cases(result, {"a", "b", "c"}), {"a"})

    def test_first_write(self):
        def ev(content):
            return {"message": {"content": [{
                "type": "tool_use", "name": "Write",
                "input": {"file_path": "/w/contracts/t.yaml",
                          "content": content}}]}}
        self.assertEqual(
            run.first_write([ev("one"), ev("two")], "contracts/t.yaml"),
            "one")
        self.assertIsNone(run.first_write([ev("x")], "contracts/u.yaml"))

    def test_dry_run_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            for step in (["init", "-q"],):
                subprocess.run(["git", "-C", str(repo), *step], check=True)
            (repo / "f.txt").write_text("x")
            subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
            ident = ["-c", "user.name=t", "-c", "user.email=t@example.com"]
            subprocess.run(["git", "-C", str(repo), *ident, "commit", "-qm",
                            "i"], check=True)
            subprocess.run(["git", "-C", str(repo), "tag", "v0"], check=True)
            out = Path(tmp) / "out"
            code, _ = quiet(["--task", "guard", "--wraith-ref", "v0",
                             "--wraith-repo", str(repo), "--out", str(out),
                             "--dry-run"], {})
            self.assertEqual(code, 0)
            self.assertTrue((out / "guard" / "DRY-RUN").exists())
            state = json.loads((out / "state.json").read_text())
            self.assertEqual(state["guard"]["status"], "done")
            manifest = json.loads((out / "manifest.json").read_text())
            self.assertEqual(len(manifest["odcs_schema_sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
