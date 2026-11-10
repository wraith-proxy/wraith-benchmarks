"""Blind judge audit pack for both hosts: 10% of plan-review verdicts each.

Usage (from wraith-benchmarks/benchmarks, after the Claude Code rejudge):
  python3 -I make_audit.py RESULTS OUT_DIR
Writes OUT_DIR/key.json (secret: host, case, arm, run, grader, judge) and
OUT_DIR/items.json (what the grader sees: answer key and agent output).
"""
import glob
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
import copilot_run as cr  # noqa: E402
import run  # noqa: E402

SEED = 20261110
PER_HOST = 36
results, out = Path(sys.argv[1]), Path(sys.argv[2])


def key_text(case, grader):
    return dict(cr.llm_graders(case))[grader]


def copilot_pool():
    base = results / "2026-11-09-copilot-plan-review"
    state = json.loads((base / "state.json").read_text())["plan-review"]
    pool = []
    for case, rel in sorted(state["complete"].items()):
        data = json.loads((base / rel / "plan-review.json").read_text())
        rep = next(c for c in data["cases"] if c["name"] == case)
        for arm, runs in rep["arms"].items():
            for i, e in enumerate(runs):
                trace = base / rel / e["tracePath"]
                norm = run.load_trace(trace)
                text = cr.agent_output(cr.final_text(norm),
                                       cr.written_files(norm,
                                                        trace.parent / "files"))
                for g in e["graders"]:
                    pool.append(("copilot", case, arm, i, g["name"],
                                 g["passed"], text))
    return pool


def cc_pool():
    pool = []
    for d in sorted(glob.glob(str(results / "2026-11-09-cc-p[0-9][0-9]"))):
        state = json.loads((Path(d) / "state.json").read_text())["plan-review"]
        for case, rel in state["complete"].items():
            adir = Path(d) / rel
            rj = json.loads((adir / "rejudge.json").read_text())["cases"][case]
            data = json.loads(next(
                f for f in sorted(adir.glob("plan-review*.json"))
            ).read_text())
            rep = next(c for c in data["cases"] if c["name"] == case)
            for arm, runs in rep["arms"].items():
                for i, e in enumerate(runs):
                    ev = run.load_trace(run.resolve_trace(
                        e["tracePath"], adir, "plan-review"))
                    text = cr.agent_output(cr.claude_final(ev),
                                           cr.trace_files(ev))
                    for grader, rows in rj.items():
                        row = next(r for r in rows
                                   if r["arm"] == arm and r["run"] == i)
                        pool.append(("claude-code", case, arm, i, grader,
                                     row["judge"], text))
    return pool


rng = random.Random(SEED)
picked = []
for pool in (copilot_pool(), cc_pool()):
    assert len(pool) >= PER_HOST, len(pool)
    picked += rng.sample(pool, PER_HOST)
rng.shuffle(picked)
key, items = {}, {}
for n, (host, case, arm, i, grader, judge, text) in enumerate(picked, 1):
    key[str(n)] = {"host": host, "case": case, "arm": arm, "run": i,
                   "grader": grader, "judge": judge}
    items[str(n)] = {"answer_key": key_text(case, grader),
                     "agent_output": text}
out.mkdir(parents=True, exist_ok=True)
(out / "key.json").write_text(json.dumps(key, indent=2))
(out / "items.json").write_text(json.dumps(items, indent=2))
print(f"{len(key)} items; seed {SEED}; per host {PER_HOST}")
