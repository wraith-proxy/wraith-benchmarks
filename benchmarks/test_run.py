import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import run


def quiet(argv, env):
    err = io.StringIO()
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(err):
        code = run.main(argv, env)
    return code, err.getvalue()


def make_repo(tmp):
    repo = Path(tmp) / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    (repo / "f.txt").write_text("x")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    ident = ["-c", "user.name=t", "-c", "user.email=t@example.com"]
    subprocess.run(["git", "-C", str(repo), *ident, "commit", "-qm", "i"],
                   check=True)
    subprocess.run(["git", "-C", str(repo), "tag", "v0"], check=True)
    return repo


def run_json(name, n=2, error=None, limit=False):
    def one(err=None):
        row = {"score": 1, "turns": 3, "error": err, "tracePath": ""}
        if err:
            row["endedOnApiError"] = True
        return row
    runs = [one() for _ in range(n)]
    if limit:
        runs[-1] = one(error or "You've hit your usage limit")
    return {"name": name, "arms": {"with": runs,
                                   "without": [dict(r) for r in runs]}}


def write_use(path, content, name="Write", **extra):
    return {"message": {"content": [{
        "type": "tool_use", "name": name,
        "input": {"file_path": f"/w/{path}", "content": content, **extra}}]}}


class ClassifyTest(unittest.TestCase):
    def test_usage_limit_only_from_flagged_run_error(self):
        names = ["guard-g1", "guard-g2"]
        data = {"cases": [run_json("guard-g1"),
                          run_json("guard-g2", limit=True)]}
        result = run.classify(data, 2, names)
        self.assertTrue(result["usage_limit"])
        self.assertEqual(result["complete"], ["guard-g1"])

    def test_limit_words_elsewhere_do_not_count(self):
        case = run_json("guard-g1")
        case["arms"]["with"][0]["output"] = "rate limit mentioned by the agent"
        result = run.classify({"cases": [case]}, 2, ["guard-g1"])
        self.assertFalse(result["usage_limit"])
        self.assertEqual(result["complete"], ["guard-g1"])

    def test_real_five_hour_limit_record_flags_usage_limit(self):
        case = run_json("guard-g1")
        case["arms"]["with"][0] = {
            "score": 0, "passed": False, "turns": 1, "costUsd": 0,
            "judgeCostUsd": 0, "durationSeconds": 1,
            "startedAt": "2026-11-04T12:34:02.644Z",
            "error": "exit 1: You've hit your 5-hour limit \u00b7 resets "
                     "3pm (UTC)",
            "tracePath": "/tmp/claude-eval-A03mhK/out/trace.jsonl",
            "skippedPaidGraders": False}
        result = run.classify({"cases": [case]}, 2, ["guard-g1"])
        self.assertTrue(result["usage_limit"])
        self.assertEqual(result["complete"], [])

    def test_errored_run_with_turns_keeps_case_incomplete(self):
        case = run_json("guard-g1")
        case["arms"]["with"][0].update(turns=4, error="boom")
        result = run.classify({"cases": [case]}, 2, ["guard-g1"])
        self.assertFalse(result["usage_limit"])
        self.assertEqual(len(result["failures"]), 1)
        self.assertEqual(result["complete"], [])

    def test_other_api_error_is_a_scored_failure(self):
        case = run_json("guard-g1", error="500 internal", limit=True)
        result = run.classify({"cases": [case]}, 2, ["guard-g1"])
        self.assertFalse(result["usage_limit"])
        self.assertEqual(result["complete"], [])

    def test_auth_rejected_and_unrecognised_shape(self):
        case = run_json("guard-g1")
        case["arms"]["with"][0]["authRejected"] = True
        self.assertTrue(
            run.classify({"x": case}, 2, ["guard-g1"])["auth_failed"])
        with self.assertRaises(run.BenchError):
            run.classify({"nothing": 1}, 2, ["guard-g1"])

    def test_run_that_never_started_is_a_harness_error(self):
        case = run_json("guard-g1")
        case["arms"]["with"][0].update(turns=0, error="sandbox unavailable")
        result = run.classify({"c": case}, 2, ["guard-g1"])
        self.assertEqual(result["complete"], [])
        self.assertEqual(len(result["harness_errors"]), 1)

    def test_missing_case_is_incomplete(self):
        result = run.classify({"c": run_json("guard-g1")}, 2,
                              ["guard-g1", "guard-g2"])
        self.assertEqual(result["complete"], ["guard-g1"])


class ContractsTest(unittest.TestCase):
    def test_first_write_and_delivered_differ(self):
        events = [write_use("contracts/t.yaml", "bad: 1\n"),
                  write_use("contracts/t.yaml", "x", name="Edit",
                            old_string="bad: 1", new_string="good: 1")]
        events[1]["message"]["content"][0]["input"].pop("content")
        self.assertEqual(run.first_write(events, "contracts/t.yaml"),
                         "bad: 1\n")
        content, touched = run.delivered_file(events, "contracts/t.yaml")
        self.assertEqual(content, "good: 1\n")
        self.assertFalse(touched)

    def test_scores_per_arm_from_trace_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            for arm, text in (("with", "ok"), ("without", "bad")):
                (Path(tmp) / f"{arm}.jsonl").write_text(
                    json.dumps(write_use("contracts/t.yaml", text)) + "\n")
            case = {"name": "contracts-t",
                    "arms": {"with": [{"tracePath": "with.jsonl"}],
                             "without": [{"tracePath": "without.jsonl"}]}}
            fake = lambda f: {"valid": Path(f).read_text() == "ok",
                              "output": ""}
            rec = run.score_contracts(tmp, {"cases": [case]}, fake)
            self.assertEqual(rec["summary"]["with"]["first_write_valid"], 1)
            self.assertEqual(rec["summary"]["without"]["first_write_valid"], 0)
            self.assertTrue((Path(tmp) / "validation.json").exists())

    def test_unreadable_traces_fail_loud(self):
        with tempfile.TemporaryDirectory() as tmp:
            case = {"name": "contracts-t",
                    "arms": {"with": [{"tracePath": "no"}]}}
            with self.assertRaises(run.BenchError):
                run.score_contracts(tmp, {"c": case})


class UsageTest(unittest.TestCase):
    def test_trace_usage_reads_result_event(self):
        events = [{"type": "assistant"},
                  {"type": "result", "duration_ms": 5, "total_cost_usd": 0.1,
                   "usage": {"input_tokens": 1, "output_tokens": 2,
                             "cache_read_input_tokens": 3}}]
        got = run.trace_usage(events)
        self.assertEqual(got["cache_read_input_tokens"], 3)
        self.assertEqual(got["cache_creation_input_tokens"], 0)
        self.assertIsNone(run.trace_usage([{"type": "assistant"}]))

    def test_trace_paths_map_to_collected_copy(self):
        self.assertEqual(
            run.resolve_trace("/tmp/claude-eval-X/out/trace.jsonl", "/a", "t"),
            Path("/a/traces/claude-eval-X/trace.jsonl"))


class SecretsTest(unittest.TestCase):
    def test_scan_finds_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            cred = Path(tmp) / "c.json"
            cred.write_text(json.dumps({"a": {"tok": "s" * 20}}))
            (Path(tmp) / "r").mkdir()
            (Path(tmp) / "r" / "log").write_text("leak " + "s" * 20)
            with self.assertRaises(run.BenchError):
                run.scan_for_secrets(Path(tmp) / "r",
                                     run.credential_secrets(cred))


class RunnerTest(unittest.TestCase):
    def test_rejections(self):
        self.assertEqual(quiet(["--task", "cost", "--dry-run"], {})[0], 2)
        for env in ({"ANTHROPIC_API_KEY": "x"}, {"ANTHROPIC_API_KEY": ""}):
            code, err = quiet(["--task", "guard", "--dry-run"], env)
            self.assertEqual(code, 2)
            self.assertIn("ANTHROPIC_API_KEY", err)
        code, err = quiet(["--task", "guard", "--max-cost-usd", "5",
                           "--credentials", "/nonexistent/c.json"], {})
        self.assertEqual(code, 2)

    def test_commands(self):
        cmd = run.eval_command("guard", 5, 10, "g1")
        self.assertEqual(cmd[cmd.index("--eval-dir") + 1], "bench-guard")
        full = run.docker_command("img", "/c", "/h/c.json", cmd, 1, 2)
        self.assertIn("/h/c.json:/run/bench/credentials.json:ro",
                      " ".join(full))
        self.assertNotIn("ANTHROPIC_API_KEY", " ".join(full))

    def test_token_replaces_login_file_for_bash_tasks(self):
        cmd = run.eval_command("guard", 5, 10, "g1")
        full = " ".join(run.docker_command("img", "/c", "/h/c.json", cmd, 1, 2,
                                           bwrap=True, token=True))
        self.assertNotIn("credentials.json", full)
        self.assertIn(f"-e {run.TOKEN_ENV} ", full)
        self.assertIn("apparmor=wraith-bench", full)
        self.assertIn("--cap-drop ALL", full)
        self.assertEqual(run.main(["--task", "guard", "--max-cost-usd", "1",
                                   "--credentials", __file__], {}), 2)

    def test_guard_scored_from_bash_calls_not_executed_log(self):
        def trace(cmd):
            return json.dumps({"type": "assistant", "message": {"content": [
                {"type": "tool_use", "name": "Bash",
                 "input": {"command": cmd}}]}})
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "a.jsonl").write_text(trace("bq show x:y"))
            Path(tmp, "b.jsonl").write_text(trace("bq rm -r -f -d x:y"))
            case = {"name": "guard-g1", "arms": {
                "with": [{"tracePath": "a.jsonl"}],
                "without": [{"tracePath": "b.jsonl"}]}}
            cases = run.score_guard(tmp, {"cases": [case]})["cases"]
        self.assertFalse(cases["guard-g1"]["with"][0]["attempted"])
        self.assertTrue(cases["guard-g1"]["without"][0]["attempted"])

    def test_per_case_resume_merges_score_files(self):
        def trace(cmd):
            return json.dumps({"type": "assistant", "message": {"content": [
                {"type": "tool_use", "name": "Bash",
                 "input": {"command": cmd}}]}})

        def case(name, cmd):
            Path(self.tmp, f"{name}.jsonl").write_text(trace(cmd))
            return {"name": name, "arms": {
                "with": [{"tracePath": f"{name}.jsonl"}],
                "without": [{"tracePath": f"{name}.jsonl"}]}}
        with tempfile.TemporaryDirectory() as tmp:
            self.tmp = tmp
            evals = [{"cases": [case("guard-g1", "bq rm -r -f -d x:y")]},
                     {"cases": [case("guard-g5", "bq show x:y")]}]
            run.summarise_usage(tmp, evals, "guard")
            run.score_guard(tmp, evals)
            score = json.loads(Path(tmp, "guard-score.json").read_text())
            usage = json.loads(Path(tmp, "usage.json").read_text())
        self.assertEqual(set(score["cases"]), {"guard-g1", "guard-g5"})
        self.assertEqual({r["case"] for r in usage},
                         {"guard-g1", "guard-g5"})

    def test_dry_run_writes_no_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp)
            out = Path(tmp) / "out"
            code, _ = quiet(["--task", "guard", "--wraith-ref", "v0",
                             "--wraith-repo", str(repo), "--out", str(out),
                             "--dry-run"], {})
            self.assertEqual(code, 0)
            self.assertTrue((out / "guard/dry-run-1/DRY-RUN").exists())
            self.assertFalse((out / "state.json").exists())

    def test_existing_attempt_dir_fails_before_the_eval(self):
        calls = []

        def fake(full, env=None):
            calls.append(full)
            return 0, "output"

        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp)
            cred = Path(tmp) / "c.json"
            cred.write_text(json.dumps({"tok": "t" * 24}))
            out = Path(tmp) / "out"
            (out / "guard/attempt-1").mkdir(parents=True)
            argv = ["--task", "guard", "--wraith-ref", "v0", "--wraith-repo",
                    str(repo), "--out", str(out), "--credentials", str(cred),
                    "--token-file", str(cred),
                    "--max-cost-usd", "8", "--runs", "2"]
            with mock.patch.object(run, "run_container", fake):
                code, err = quiet(argv, {})
            self.assertEqual(code, 4)
            self.assertIn("attempt-1 already exists", err)
            self.assertEqual(calls, [])

    def test_usage_limit_then_resume_keeps_attempts_apart(self):
        names = run.case_names("guard")
        calls = []

        def fake(full, env=None):
            clone = Path([a for a in full if a.endswith(":/work")][0][:-6])
            cmd = full[full.index("claude"):]
            case = cmd[cmd.index("--case") + 1] if "--case" in cmd else None
            jname = case or "guard"
            if not calls:
                data = {"cases": [run_json(names[0]),
                                  run_json(names[1], limit=True)]}
            else:
                data = {"cases": [run_json(case)]}
            calls.append(case)
            res = clone / "bench-guard" / "results"
            (res / f"{jname}.json").write_text(json.dumps(data))
            return 0, "output"

        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp)
            cred = Path(tmp) / "c.json"
            cred.write_text(json.dumps({"tok": "t" * 24}))
            out = Path(tmp) / "out"
            argv = ["--task", "guard", "--wraith-ref", "v0", "--wraith-repo",
                    str(repo), "--out", str(out), "--credentials", str(cred),
                    "--token-file", str(cred),
                    "--max-cost-usd", "8", "--runs", "2"]
            with mock.patch.object(run, "run_container", fake):
                self.assertEqual(quiet(argv, {})[0], 3)
                state = json.loads((out / "state.json").read_text())
                self.assertEqual(state["guard"]["status"], "usage_limit")
                self.assertEqual(state["guard"]["complete"],
                                 {names[0]: "guard/attempt-1"})
                self.assertEqual(quiet(argv, {})[0], 2)  # no --resume
                self.assertEqual(quiet(argv + ["--resume"], {})[0], 0)
            self.assertEqual(calls[1:], names[1:])
            state = json.loads((out / "state.json").read_text())
            self.assertEqual(state["guard"]["status"], "done")
            self.assertTrue((out / "guard/attempt-1").is_dir())
            self.assertTrue((out / "guard/attempt-2").is_dir())
            self.assertEqual(state["guard"]["complete"][names[1]],
                             "guard/attempt-2")


if __name__ == "__main__":
    unittest.main()


class PluginRootTest(unittest.TestCase):
    def test_subfolder_plugin_is_the_eval_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            clone = Path(tmp)
            self.assertEqual(run.plugin_root(clone), clone)
            (clone / "plugin").mkdir()
            self.assertEqual(run.plugin_root(clone), clone / "plugin")


class KeepTempTest(unittest.TestCase):
    def test_traces_are_kept_without_the_flag(self):
        seen = {}

        def fake_eval_command(*a, **kw):
            seen["keep_temp"] = kw.get("keep_temp")
            raise SystemExit(0)
        with mock.patch.object(run, "eval_command", fake_eval_command), \
                mock.patch.object(run, "subprocess") as sp:
            sp.run.return_value = subprocess.CompletedProcess([], 0, "abc\n", "")
            with tempfile.TemporaryDirectory() as tmp, \
                    contextlib.suppress(SystemExit, Exception):
                run.main(["--task", "guard", "--dry-run", "--out", tmp,
                          "--wraith-ref", "v0.8.3"])
        self.assertIs(seen.get("keep_temp"), True)
