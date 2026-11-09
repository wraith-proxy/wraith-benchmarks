import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import copilot_run as cr
import run

DATA = Path(__file__).resolve().parent / "testdata" / "copilot"
TOKEN = "ghu_synthetic_token_value_1234567890"


def fixture(name):
    return (DATA / name).read_text()


class Fake:
    """Stands in for subprocess.run: git, scaffold and docker only."""

    def __init__(self, stdout="", stderr="", code=0):
        self.stdout, self.stderr, self.code = stdout, stderr, code
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        out = ""
        if argv[0] == "git":
            if "clone" in argv:
                Path(argv[-1], "plugin").mkdir(parents=True)
            else:
                out = "abc123\n"
        elif argv[0] == "docker":
            return subprocess.CompletedProcess(
                argv, self.code, self.stdout, self.stderr)
        return subprocess.CompletedProcess(argv, 0, out, "")

    def dockers(self):
        return [a for a, _ in self.calls if a[0] == "docker"]


def run_main(tmp, fake, extra=(), env=None, runs="2"):
    token = Path(tmp) / "token"
    token.write_text(TOKEN + "\n")
    argv = ["--task", "guard", "--case", "g1", "--runs", runs,
            "--model", "m", "--max-ai-credits", "30",
            "--token-file", str(token), "--out", str(Path(tmp) / "out"),
            *extra]
    err = io.StringIO()
    with mock.patch("subprocess.run", fake), \
            contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(err):
        code = cr.main(argv, {} if env is None else env)
    return code, err.getvalue()


def out_json(tmp, path):
    return json.loads((Path(tmp) / "out" / path).read_text())


class ScoringTest(unittest.TestCase):
    def test_bq_rm_attempted_and_bq_ls_not(self):
        for name, expected in (("shell_rm.jsonl", True),
                               ("shell_ls.jsonl", False)):
            with tempfile.TemporaryDirectory() as tmp:
                code, _ = run_main(tmp, Fake(stdout=fixture(name)))
                self.assertEqual(code, 0)
                score = out_json(tmp, "guard/attempt-1/guard-score.json")
                rows = score["cases"]["guard-g1"]["with"]
                self.assertEqual([r["attempted"] for r in rows],
                                 [expected] * 2)

    def test_eval_json_passes_classify(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, _ = run_main(tmp, Fake(stdout=fixture("shell_rm.jsonl")))
            data = out_json(tmp, "guard/attempt-1/guard.json")
            result = run.classify(data, 2, ["guard-g1"])
            self.assertEqual(result["complete"], ["guard-g1"])
            run_entry = data["cases"][0]["arms"]["with"][0]
            for key in ("score", "turns", "error", "durationSeconds",
                        "tracePath", "graders"):
                self.assertIn(key, run_entry)
            self.assertEqual(run_entry["graders"][0]["passed"], True)

    def test_first_write_and_delivered_contents(self):
        norm = cr.normalise(cr.parse_events(fixture("write_edit.jsonl")))
        self.assertEqual(
            run.first_write(norm, "contracts/accounts.yaml"), "a: 1\n")
        content, _ = run.delivered_file(norm, "contracts/accounts.yaml")
        self.assertEqual(content, "a: 2\n")

    def test_contracts_delivered_read_from_files_dir(self):
        norm = cr.normalise(cr.parse_events(fixture("write_edit.jsonl")))
        with tempfile.TemporaryDirectory() as tmp:
            trace_dir = Path(tmp) / "traces/contracts-accounts/with-0"
            (trace_dir / "files/contracts").mkdir(parents=True)
            (trace_dir / "files/contracts/accounts.yaml").write_text("a: 2\n")
            (trace_dir / "trace.norm.jsonl").write_text(
                "".join(json.dumps(e) + "\n" for e in norm))
            entry = {"tracePath": "traces/contracts-accounts/with-0/"
                                  "trace.norm.jsonl"}
            data = {"cases": [{"name": "contracts-accounts",
                               "arms": {"with": [entry], "without": []}}]}

            def validator(path):
                return {"valid": "a: 2" in Path(path).read_text(),
                        "output": ""}
            record = cr.score_contract_arms(tmp, data, validator)
            row = record["cases"]["contracts-accounts"]["with"][0]
            self.assertFalse(row["first_write"]["valid"])
            self.assertTrue(row["delivered"]["valid"])


class RunnerTest(unittest.TestCase):
    def test_api_key_exits_2_before_any_subprocess(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Fake()
            code, err = run_main(tmp, fake, env={"ANTHROPIC_API_KEY": "x"})
            self.assertEqual(code, 2)
            self.assertEqual(fake.calls, [])
            self.assertIn("ANTHROPIC_API_KEY", err)

    def test_plugin_dir_only_with_arm_and_arms_alternate(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Fake(stdout=fixture("shell_ls.jsonl"))
            run_main(tmp, fake)
            arms = []
            for cmd in fake.dockers():
                has_flag = "--plugin-dir" in cmd
                has_mount = any(a.endswith("/plugin:ro") for a in cmd)
                self.assertEqual(has_flag, has_mount)
                arms.append("with" if has_flag else "without")
            self.assertEqual(arms, ["with", "without", "without", "with"])
            self.assertIn("COPILOT_GITHUB_TOKEN", fake.dockers()[0])
            self.assertNotIn(TOKEN, " ".join(fake.dockers()[0]))

    def test_tmpfs_home_allows_exec(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Fake(stdout=fixture("shell_ls.jsonl"))
            run_main(tmp, fake, runs="1")
            for cmd in fake.dockers():
                opt = next(c for c in cmd if c.startswith("/home/bench:"))
                self.assertIn(",exec,", opt)
                self.assertIn("nosuid", opt)

    def test_scaffold_runs_in_container_before_copilot(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Fake(stdout=fixture("shell_ls.jsonl"))
            run_main(tmp, fake, runs="1")
            self.assertTrue(fake.dockers())
            for cmd in fake.dockers():
                i = cmd.index("bash")
                self.assertEqual(cmd[i + 1], "-c")
                script = cmd[i + 2]
                self.assertLess(script.index("scaffold_script"),
                                script.index("exec copilot"))
                self.assertEqual(cmd[i + 3], "copilot-bench")
                self.assertIn("-p", cmd[i + 4:])
                self.assertIn("TASK=guard", cmd)
                self.assertIn("CASE=g1", cmd)
                self.assertIn(f"{cr.HERE / 'fixtures'}:/fixtures:ro", cmd)
            hosts = [a for a, _ in fake.calls
                     if a[0] == "bash" or "scaffold_script" in " ".join(a)
                     and a[0] != "docker"]
            self.assertEqual(hosts, [])

    def test_scaffold_failure_is_run_error_and_task_continues(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Fake(stderr="boom\nharness: scaffold failed (exit 1)\n",
                        code=cr.SCAFFOLD_FAILED)
            code, _ = run_main(tmp, fake)
            self.assertEqual(code, 0)
            self.assertEqual(len(fake.dockers()), 4)
            data = out_json(tmp, "guard/attempt-1/guard.json")
            for runs in data["cases"][0]["arms"].values():
                for entry in runs:
                    self.assertIn("scaffold failed", entry["error"])
                    self.assertIn("exit 1", entry["error"])

    def test_unknown_event_shape_raises(self):
        with self.assertRaises(run.BenchError):
            cr.normalise(cr.parse_events(fixture("unknown.jsonl")))
        with tempfile.TemporaryDirectory() as tmp:
            code, err = run_main(tmp, Fake(stdout=fixture("unknown.jsonl")))
            self.assertEqual(code, 4)
            self.assertIn("unrecognised event type", err)
            self.assertTrue(list((Path(tmp) / "out").rglob("trace.jsonl")))

    def test_limit_exits_3_then_resume_reruns_into_attempt_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            limited = Fake(stderr="premium request quota exceeded", code=1)
            code, _ = run_main(tmp, limited)
            self.assertEqual(code, 3)
            state = out_json(tmp, "state.json")["guard"]
            self.assertEqual(state["incomplete"], ["guard-g1"])
            self.assertEqual(state["complete"], {})
            ok = Fake(stdout=fixture("shell_rm.jsonl"))
            code, _ = run_main(tmp, ok, extra=["--resume"])
            self.assertEqual(code, 0)
            state = out_json(tmp, "state.json")["guard"]
            self.assertEqual(state["complete"],
                             {"guard-g1": "guard/attempt-2"})
            self.assertTrue((Path(tmp) / "out/guard/attempt-2/guard.json")
                            .is_file())

    def test_limit_text_in_agent_message_is_not_a_limit(self):
        text = json.dumps({"type": "assistant.message", "data": {
            "content": "the rate limit was exceeded"}}) + "\n"
        with tempfile.TemporaryDirectory() as tmp:
            code, _ = run_main(tmp, Fake(stdout=text))
            self.assertEqual(code, 0)

    def test_token_in_trace_blocks_copy(self):
        leaked = fixture("shell_ls.jsonl") + json.dumps(
            {"type": "assistant.message", "data": {"content": TOKEN}}) + "\n"
        with tempfile.TemporaryDirectory() as tmp:
            code, err = run_main(tmp, Fake(stdout=leaked))
            self.assertEqual(code, 4)
            for f in (Path(tmp) / "out").rglob("*"):
                if f.is_file():
                    self.assertNotIn(TOKEN, f.read_text())

    def test_dry_run_runs_nothing(self):
        fake = Fake()
        err = io.StringIO()
        with mock.patch("subprocess.run", fake), \
                contextlib.redirect_stdout(io.StringIO()):
            code = cr.main(["--task", "guard", "--model", "m",
                            "--max-ai-credits", "30", "--out", "/nonexistent",
                            "--dry-run"], {})
        self.assertEqual(code, 0)
        self.assertEqual(fake.calls, [])


def messages(n):
    return "".join(
        json.dumps({"type": "assistant.turn_start", "data": {}}) + "\n"
        + json.dumps({"type": "assistant.message",
                      "data": {"content": f"m{i}"}}) + "\n"
        for i in range(n))


class LoggingFake(Fake):
    """Docker run also drops files into the mounted workspace."""

    def __init__(self, files, **kwargs):
        super().__init__(**kwargs)
        self.files = files

    def __call__(self, argv, **kwargs):
        if argv[0] == "docker":
            mount = next(a for a in argv if a.endswith(":/work/ws"))
            for name, text in self.files.items():
                Path(mount[:-len(":/work/ws")], name).write_text(text)
        return super().__call__(argv, **kwargs)


class HardeningTest(unittest.TestCase):
    def test_token_in_stderr_redacted_in_task_and_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Fake(stdout=fixture("shell_ls.jsonl"),
                        stderr=f"boom {TOKEN} boom", code=1)
            code, err = run_main(tmp, fake)
            self.assertEqual(code, 0)
            text = (Path(tmp) / "out/guard/attempt-1/guard.json").read_text()
            self.assertIn("[redacted]", text)
            for f in (Path(tmp) / "out").rglob("*"):
                if f.is_file():
                    self.assertNotIn(TOKEN, f.read_text())

    def test_token_in_error_message_redacted_in_state(self):
        class Boom(Fake):
            def __call__(self, argv, **kwargs):
                if argv[0] == "docker":
                    raise subprocess.CalledProcessError(1, ["x", TOKEN])
                return super().__call__(argv, **kwargs)
        with tempfile.TemporaryDirectory() as tmp:
            code, err = run_main(tmp, Boom())
            self.assertEqual(code, 4)
            self.assertNotIn(TOKEN, err)
            state = (Path(tmp) / "out/state.json").read_text()
            self.assertIn("[redacted]", state)
            self.assertNotIn(TOKEN, state)

    def test_planted_token_exits_5_without_printing_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            out.mkdir()
            (out / "stray.txt").write_text(f"x {TOKEN} y")
            code, err = run_main(tmp, Fake(stdout=fixture("shell_ls.jsonl")))
            self.assertEqual(code, 5)
            self.assertIn("stray.txt", err)
            self.assertNotIn(TOKEN, err)

    def test_manifest_exists_after_crash_on_first_case(self):
        class Crash(Fake):
            def __call__(self, argv, **kwargs):
                if argv[0] == "docker":
                    raise RuntimeError("crash")
                return super().__call__(argv, **kwargs)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RuntimeError):
                run_main(tmp, Crash())
            manifest = out_json(tmp, "manifest.json")
            self.assertEqual(manifest["max_ai_credits_per_run"], 30.0)
            self.assertEqual(manifest["projected_total_credits"], 120.0)

    def test_secret_scan_runs_even_when_a_run_crashes(self):
        class Crash(Fake):
            def __call__(self, argv, **kwargs):
                if argv[0] == "docker":
                    raise RuntimeError("crash")
                return super().__call__(argv, **kwargs)
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(
                cr, "leaks", wraps=cr.leaks
            ) as scan:
                with self.assertRaises(RuntimeError):
                    run_main(tmp, Crash())
            scan.assert_called_once()

    def test_over_12_turns_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_main(tmp, Fake(stdout=messages(13)), runs="1")
            data = out_json(tmp, "guard/attempt-1/guard.json")
            arms = data["cases"][0]["arms"]
            self.assertEqual(arms["with"][0]["flags"], ["over_12_turns"])
            usage = out_json(tmp, "guard/attempt-1/usage.json")
            self.assertEqual(usage["flag_counts"]["over_12_turns"], 2)
        with tempfile.TemporaryDirectory() as tmp:
            run_main(tmp, Fake(stdout=messages(12)), runs="1")
            data = out_json(tmp, "guard/attempt-1/guard.json")
            self.assertEqual(data["cases"][0]["arms"]["with"][0]["flags"], [])

    def test_executed_log_recorded_without_changing_score(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = LoggingFake({"executed.log": "git-push x\n"},
                               stdout=fixture("shell_ls.jsonl"))
            run_main(tmp, fake, runs="1")
            rows = out_json(tmp, "guard/attempt-1/guard-score.json")[
                "cases"]["guard-g1"]["with"]
            self.assertTrue(rows[0]["executed"])
            self.assertFalse(rows[0]["attempted"])
        with tempfile.TemporaryDirectory() as tmp:
            run_main(tmp, Fake(stdout=fixture("shell_ls.jsonl")), runs="1")
            rows = out_json(tmp, "guard/attempt-1/guard-score.json")[
                "cases"]["guard-g1"]["with"]
            self.assertFalse(rows[0]["executed"])

    def test_truncated_last_line_is_error_and_task_continues(self):
        cut = fixture("shell_ls.jsonl") + '{"type": "assistant.mess'
        with tempfile.TemporaryDirectory() as tmp:
            fake = Fake(stdout=cut)
            code, _ = run_main(tmp, fake)
            self.assertEqual(code, 0)
            self.assertEqual(len(fake.dockers()), 4)
            data = out_json(tmp, "guard/attempt-1/guard.json")
            for runs in data["cases"][0]["arms"].values():
                for entry in runs:
                    self.assertEqual(entry["error"], "truncated output")
                    self.assertEqual(entry["score"], 0)

    def test_complete_bad_line_still_raises(self):
        with self.assertRaises(run.BenchError):
            cr.parse_events('{"type": "x"}\nnot json\n')

    def test_limit_pattern_ignores_bare_exceeded(self):
        self.assertIsNone(cr.COPILOT_LIMIT.search("max-ai-credits exceeded"))
        self.assertTrue(cr.COPILOT_LIMIT.search("Quota Exceeded"))

    def test_edit_only_file_reaches_judge_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace_dir = Path(tmp) / "traces/plan-review-p01/with-0"
            (trace_dir / "files").mkdir(parents=True)
            (trace_dir / "files/review.md").write_text("EDITED FINAL BODY")
            edit = {"type": "assistant", "message": {"content": [{
                "type": "tool_use", "name": "Edit",
                "input": {"file_path": "/work/ws/review.md",
                          "old_string": "a", "new_string": "b"}}]}}
            done = {"type": "assistant", "message": {"content": [
                {"type": "text", "text": "done"}]}}
            (trace_dir / "trace.norm.jsonl").write_text(
                json.dumps(edit) + "\n" + json.dumps(done) + "\n")
            entry = {"tracePath": "traces/plan-review-p01/with-0/"
                                  "trace.norm.jsonl"}
            data = {"cases": [{"name": "plan-review-p01",
                               "arms": {"with": [entry], "without": []}}]}
            prompts = []

            def fake_run(argv, **kwargs):
                prompts.append(kwargs["input"])
                return subprocess.CompletedProcess(
                    argv, 0, json.dumps({"result": "PASS"}), "")
            with mock.patch("subprocess.run", fake_run):
                cr.score_plan_review(tmp, data)
            self.assertIn("--- /work/ws/review.md ---\nEDITED FINAL BODY",
                          prompts[0])


def votes_of(*votes):
    it = iter(votes * 10)
    seen = []

    def vote(prompt):
        seen.append(prompt)
        return next(it)
    vote.seen = seen
    return vote


class JudgeTest(unittest.TestCase):
    def test_majority_and_explanation(self):
        vote = votes_of("PASS", "FAIL", "PASS")
        graders = cr.judge_case("plan-review-p01", "final", {}, vote)
        self.assertEqual(len(graders), 3)
        self.assertTrue(graders[0]["passed"])
        self.assertEqual(graders[0]["explanation"],
                         "judge votes: PASS FAIL PASS")

    def test_unparsable_vote_raises(self):
        with self.assertRaises(run.BenchError):
            cr.parse_vote(json.dumps({"result": "Probably PASS"}))
        with self.assertRaises(run.BenchError):
            cr.parse_vote("not json")
        bad = subprocess.CompletedProcess([], 0, "garbage", "")
        with mock.patch("subprocess.run", return_value=bad), \
                self.assertRaises(run.BenchError):
            cr.vote_once("p")

    def test_vote_parses_first_line(self):
        out = json.dumps({"result": "FAIL\nbecause"})
        self.assertEqual(cr.parse_vote(out), "FAIL")

    def test_argv_and_env_never_carry_api_key(self):
        environ = {"ANTHROPIC_API_KEY": "secret", "PATH": "/bin"}
        argv, kwargs = cr.judge_invocation("prompt", "/empty", environ)
        self.assertIn("-p", argv)
        self.assertEqual(argv[argv.index("--model") + 1], "claude-haiku-5-5")
        self.assertNotIn("ANTHROPIC_API_KEY", kwargs["env"])
        self.assertEqual(kwargs["env"]["PATH"], "/bin")
        self.assertEqual(kwargs["input"], "prompt")
        self.assertEqual(kwargs["cwd"], "/empty")

    def test_judge_input_has_final_text_and_written_files(self):
        vote = votes_of("PASS")
        cr.judge_case("plan-review-p01", "FINAL REVIEW TEXT",
                      {"/work/review.md": "FILE BODY"}, vote)
        prompt = vote.seen[0]
        self.assertIn("FINAL REVIEW TEXT", prompt)
        self.assertIn("--- /work/review.md ---\nFILE BODY", prompt)
        self.assertIn("Planted defect", prompt)

    def test_rejudge_agreement(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace = Path(tmp) / "traces/plan-review-p01/t.jsonl"
            trace.parent.mkdir(parents=True)
            trace.write_text(json.dumps({"type": "result",
                                         "result": "the review"}) + "\n")
            graders = [{"name": "1-grain", "passed": True},
                       {"name": "2-dedup", "passed": False},
                       {"name": "3-scan", "passed": True}]
            entry = {"tracePath": "traces/plan-review-p01/t.jsonl",
                     "graders": graders}
            (Path(tmp) / "plan-review.json").write_text(json.dumps({
                "cases": [{"name": "plan-review-p01",
                           "arms": {"with": [entry], "without": []}}]}))
            record = cr.rejudge(tmp, votes_of("PASS"))
            self.assertEqual(record["compared"], 3)
            self.assertEqual(record["agreed"], 2)
            self.assertTrue((Path(tmp) / "rejudge.json").is_file())

    def test_rejudge_sensitive_below_85_percent(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace = Path(tmp) / "traces/plan-review-p01/t.jsonl"
            trace.parent.mkdir(parents=True)
            trace.write_text(json.dumps({"type": "result",
                                         "result": "the review"}) + "\n")
            first = {"tracePath": "traces/plan-review-p01/t.jsonl",
                     "graders": [{"name": "1-grain", "passed": True},
                                 {"name": "2-dedup", "passed": False},
                                 {"name": "3-scan", "passed": True}]}
            second = {"tracePath": "traces/plan-review-p01/t.jsonl",
                      "graders": [{"name": "1-grain", "passed": True},
                                  {"name": "2-dedup", "passed": True}]}
            (Path(tmp) / "plan-review.json").write_text(json.dumps({
                "cases": [{"name": "plan-review-p01", "arms": {
                    "with": [first], "without": [second]}}]}))
            record = cr.rejudge(tmp, votes_of(*["PASS"] * 20))
            self.assertEqual((record["agreed"], record["compared"]), (4, 5))
            self.assertTrue(record["judge_sensitive"])
            saved = json.loads((Path(tmp) / "rejudge.json").read_text())
            self.assertTrue(saved["judge_sensitive"])

    def test_plan_review_dry_run_prints_commands_only(self):
        fake = Fake()
        buf = io.StringIO()
        with mock.patch("subprocess.run", fake), \
                contextlib.redirect_stdout(buf):
            code = cr.main(["--task", "plan-review", "--model", "m",
                            "--max-ai-credits", "30", "--out", "/nonexistent",
                            "--dry-run"], {})
        self.assertEqual(code, 0)
        self.assertEqual(fake.calls, [])
        self.assertIn("claude -p --model claude-haiku-5-5", buf.getvalue())


class FusionTest(unittest.TestCase):
    def test_auto_without_tier_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Fake()
            code, err = run_main(tmp, fake, extra=["--model", "auto"])
            self.assertEqual(code, 2)
            self.assertIn("--auto-tier", err)
            self.assertEqual(fake.calls, [])

    def test_auto_tier_in_argv_and_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Fake(stdout=fixture("shell_ls.jsonl"))
            code, _ = run_main(
                tmp, fake, runs="1",
                extra=["--model", "auto", "--auto-tier", "intelligence"])
            self.assertEqual(code, 0)
            argv = fake.dockers()[0]
            i = argv.index("--auto-tier")
            self.assertEqual(argv[i + 1], "intelligence")
            self.assertEqual(out_json(tmp, "manifest.json")["auto_tier"],
                             "intelligence")

    def test_credits_below_30_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Fake()
            code, err = run_main(tmp, fake,
                                 extra=["--max-ai-credits", "29"])
            self.assertEqual(code, 2)
            self.assertIn("Copilot needs --max-ai-credits of at least 30",
                          err)
            self.assertEqual(fake.calls, [])

    def test_all_runs_failing_before_a_turn_exits_4(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Fake(code=1, stderr='Error: Model "x" from --model '
                                       'flag is not available.\n')
            code, err = run_main(tmp, fake)
            self.assertEqual(code, 4)
            self.assertIn("[guard] no run reached the model; first error: "
                          'Error: Model "x" from --model flag is not '
                          "available.", err)

    def test_session_only_trace_parses_with_zero_tool_calls(self):
        trace = "".join(json.dumps(e) + "\n" for e in (
            {"type": "session.mcp_server_status_changed",
             "data": {"serverName": "a", "status": "connected"}},
            {"type": "session.mcp_server_tools_loaded",
             "data": {"serverName": "a", "tools": []}},
            {"type": "session.mcp_server_status_changed",
             "data": {"serverName": "b", "status": "connected"}}))
        parsed, _ = cr.split_events(trace)
        norm = cr.normalise(parsed)
        self.assertEqual(norm, [])


class RealTraceTest(unittest.TestCase):
    def setUp(self):
        self.events = cr.parse_events(fixture("real-plan-review-with.jsonl"))
        self.norm = cr.normalise(self.events)

    def calls(self):
        return [(b["name"], b["input"]) for b in run.tool_use_blocks(self.norm)]

    def test_calls_in_order(self):
        calls = self.calls()
        self.assertEqual(calls[0], ("Skill", {"skill": "plan-data-review"}))
        self.assertEqual([n for n, _ in calls[1:4]],
                         ["Glob", "Read", "Glob"])
        self.assertEqual(calls[2][1],
                         {"file_path": "/work/ws/docs/wraith/"
                          "2026-10-12-daily-revenue/plan.md"})
        self.assertEqual(len(calls), 11)

    def test_final_text_is_the_final_answer(self):
        self.assertTrue(cr.final_text(self.norm).startswith(
            "The plan is **NOT READY**"))

    def test_meta(self):
        meta = cr.run_meta(self.events)
        self.assertEqual(meta["model_routed"], "gpt-6-luna")
        self.assertEqual(meta["models_called"], ["gpt-6-luna"])
        self.assertEqual(meta["premium_requests"], 1)
        self.assertEqual(meta["nano_aiu"], 343703000)
        self.assertAlmostEqual(meta["ai_credits_est"], 0.343703)
        self.assertEqual(meta["api_ms"], 38910)
        self.assertEqual(meta["session_ms"], 41611)
        self.assertEqual(meta["turns"], 5)
        self.assertEqual(meta["unmapped_tools"], [])

    def test_unmapped_tool_is_recorded_not_raised(self):
        trace = json.dumps({"type": "tool.execution_start", "data": {
            "toolName": "web_fetch", "arguments": {"url": "x"}}}) + "\n"
        events = cr.parse_events(trace)
        self.assertEqual(cr.normalise(events), [])
        self.assertEqual(cr.run_meta(events)["unmapped_tools"],
                         ["web_fetch"])

    def test_unknown_event_type_still_raises(self):
        with self.assertRaises(run.BenchError):
            cr.normalise([{"type": "weird.event", "data": {}}])


def tool_events(*calls):
    return [{"type": "tool.execution_start",
             "data": {"toolName": n, "arguments": a}} for n, a in calls]


class ToolNamesTest(unittest.TestCase):
    def available(self, task):
        cmd = cr.copilot_command(task, "p", "m", 30, "without")
        return cmd[cmd.index("--available-tools") + 1:][:20]

    def test_guard_offers_bash_and_view(self):
        tools = self.available("guard")
        self.assertEqual(tools[:2], ["bash", "read_bash"])
        self.assertIn("view", tools)

    def test_contracts_offers_write_and_search_tools(self):
        tools = self.available("contracts")
        for name in ("create", "apply_patch", "edit", "view", "glob", "rg",
                     "skill", "bash"):
            self.assertIn(name, tools)
        self.assertEqual(tools.count("apply_patch"), 1)

    def test_apply_patch_add_file_is_a_write_the_scorer_sees(self):
        patch = ("*** Begin Patch\n*** Add File: contracts/accounts.yaml\n"
                 "+a: 1\n+b: 2\n*** Update File: x.md\n@@\n-o\n+n\n"
                 "*** Delete File: old.md\n*** End Patch")
        norm = cr.normalise(tool_events(("apply_patch", {"input": patch})))
        self.assertEqual(
            run.first_write(norm, "contracts/accounts.yaml"), "a: 1\nb: 2")
        inputs = [e["message"]["content"][0]["input"] for e in norm]
        self.assertIn({"file_path": "x.md"}, inputs)
        self.assertIn({"file_path": "old.md", "deleted": True}, inputs)

    def test_apply_patch_string_arguments(self):
        patch = "*** Begin Patch\n*** Add File: f\n+x\n*** End Patch"
        events = [{"type": "tool.execution_start", "data": {
            "toolName": "apply_patch", "arguments": patch}}]
        self.assertEqual(run.first_write(cr.normalise(events), "f"), "x")

    def test_str_replace_editor_create_is_write(self):
        norm = cr.normalise(tool_events(("str_replace_editor", {
            "command": "create", "path": "/w/a.yaml", "file_text": "k: v"})))
        self.assertEqual(run.first_write(norm, "a.yaml"), "k: v")

    def test_rg_is_grep_and_bash_session_tools_are_silent(self):
        norm = cr.normalise(tool_events(
            ("rg", {"pattern": "p", "paths": ["."], "output_mode": "x"}),
            ("read_bash", {"shellId": "1"})))
        self.assertEqual(len(norm), 1)
        block = norm[0]["message"]["content"][0]
        self.assertEqual((block["name"], block["input"]),
                         ("Grep", {"pattern": "p"}))
        self.assertEqual(cr.unmapped_tools(tool_events(
            ("read_bash", {}))), [])


if __name__ == "__main__":
    unittest.main()


class ShellEventsTest(unittest.TestCase):
    def test_shell_progress_events_are_ignored(self):
        lines = [
            {"type": "tool.execution_start", "data": {"toolCallId": "1",
             "toolName": "bash", "arguments": {"command": "bq ls"}}},
            {"type": "tool.execution_partial_result", "data": {"toolCallId": "1"}},
            {"type": "tool.shell_output", "data": {"toolCallId": "1"}},
            {"type": "prompt_cache_break", "data": {"primaryReason": "x"}},
        ]
        text = json.dumps(cr.normalise(lines))
        self.assertEqual(text.count('"name": "Bash"'), 1)
        self.assertIn("bq ls", text)


class ExistingOutTest(unittest.TestCase):
    def test_existing_manifest_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            out.mkdir()
            (out / "manifest.json").write_text('{"keep": true}')
            code, err = run_main(tmp, Fake(stdout=fixture("shell_ls.jsonl")))
            self.assertEqual(code, 2)
            self.assertIn("manifest.json exists", err)
            self.assertEqual((out / "manifest.json").read_text(), '{"keep": true}')


class VoteLineTest(unittest.TestCase):
    def test_reason_on_vote_line_is_accepted(self):
        out = json.dumps({"result": "FAIL: the review only asks about it"})
        self.assertEqual(cr.parse_vote(out), "FAIL")
        self.assertEqual(cr.parse_vote(json.dumps({"result": "PASS."})),
                         "PASS")

    def test_vote_must_lead_the_line(self):
        with self.assertRaises(cr.BenchError):
            cr.parse_vote(json.dumps({"result": "PASSABLE"}))


class WrittenFilesTest(unittest.TestCase):
    def test_edited_file_is_read_from_the_workspace_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            files = Path(tmp) / "files"
            plan = files / "docs/plan.md"
            plan.parent.mkdir(parents=True)
            plan.write_text("PLAN\n## Data review\nVerdict: NOT READY")
            norm = [{"type": "assistant", "message": {"content": [
                {"type": "tool_use", "name": "Edit",
                 "input": {"file_path": "/work/ws/docs/plan.md"}}]}}]
            got = cr.written_files(norm, files)
        self.assertIn("Verdict: NOT READY", got["/work/ws/docs/plan.md"])
