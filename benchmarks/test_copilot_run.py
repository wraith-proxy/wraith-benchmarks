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
            "--model", "m", "--max-ai-credits", "1",
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
                            "--max-ai-credits", "1", "--out", "/nonexistent",
                            "--dry-run"], {})
        self.assertEqual(code, 0)
        self.assertEqual(fake.calls, [])


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

    def test_plan_review_dry_run_prints_commands_only(self):
        fake = Fake()
        buf = io.StringIO()
        with mock.patch("subprocess.run", fake), \
                contextlib.redirect_stdout(buf):
            code = cr.main(["--task", "plan-review", "--model", "m",
                            "--max-ai-credits", "1", "--out", "/nonexistent",
                            "--dry-run"], {})
        self.assertEqual(code, 0)
        self.assertEqual(fake.calls, [])
        self.assertIn("claude -p --model claude-haiku-5-5", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
