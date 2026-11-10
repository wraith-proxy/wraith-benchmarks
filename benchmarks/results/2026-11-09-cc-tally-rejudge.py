"""Claude Code v0.8.3 plan-review, re-judged like for like with Copilot.

Reads rejudge.json (copilot_run.py --rejudge: our judge on the final reply
plus Write content and Edit-inserted text) from the attempt each case is
credited to, and reports found / planted per arm, by category, and the
agreement with eval's own judge (final reply only).
Usage: python3 -I 2026-11-09-cc-tally-rejudge.py <results-root> [--json PATH]
"""
import collections
import glob
import json
import math
import sys

args = sys.argv[1:]
json_path = None
if "--json" in args:
    i = args.index("--json")
    json_path = args[i + 1]
    del args[i:i + 2]
root = args[0]
ARMS = ("with", "without")


def wilson(k, n, z=1.96):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


found, planted = collections.Counter(), collections.Counter()
cat = collections.defaultdict(collections.Counter)
cat_n = collections.defaultdict(collections.Counter)
per_case = {}
agree = compared = 0
flips = collections.Counter()
for out in sorted(glob.glob(f"{root}/2026-11-09-cc-p[0-9][0-9]")):
    state = json.load(open(f"{out}/state.json"))["plan-review"]
    for case, rel in state["complete"].items():
        rj = json.load(open(f"{out}/{rel}/rejudge.json"))
        agree += rj["agreed"]
        compared += rj["compared"]
        for grader, rows in rj["cases"][case].items():
            key = grader.split("-", 1)[1]
            for r in rows:
                arm = r["arm"]
                found[arm] += r["judge"]
                planted[arm] += 1
                cat[key][arm] += r["judge"]
                cat_n[key][arm] += 1
                per_case.setdefault((case, arm), 0)
                per_case[(case, arm)] += r["judge"]
                if r["eval"] is not None and bool(r["eval"]) != r["judge"]:
                    flips[(arm, "eval FAIL -> PASS" if r["judge"]
                           else "eval PASS -> FAIL")] += 1

for arm in ARMS:
    lo, hi = wilson(found[arm], planted[arm])
    print(f"- {arm}: {found[arm]}/{planted[arm]} = "
          f"{found[arm] / planted[arm]:.1%} (Wilson 95% {lo:.1%} to {hi:.1%})")
print(f"- agreement with eval's judge: {agree}/{compared} = "
      f"{agree / compared:.1%}")
for k, v in sorted(flips.items()):
    print(f"- {k[0]}: {k[1]} x{v}")
cases = sorted({c for c, _ in per_case})
print(f"- with higher: {sum(per_case[(c, 'with')] > per_case[(c, 'without')] for c in cases)}; "
      f"tied: {[c[-3:] for c in cases if per_case[(c, 'with')] == per_case[(c, 'without')]]}; "
      f"lower: {[c[-3:] for c in cases if per_case[(c, 'with')] < per_case[(c, 'without')]]}")
print("\n| Category | with | without |\n|---|---|---|")
for key in sorted(cat):
    print(f"| {key} | {cat[key]['with']} / {cat_n[key]['with']} | "
          f"{cat[key]['without']} / {cat_n[key]['without']} |")

if json_path:
    def side(arm):
        lo, hi = wilson(found[arm], planted[arm])
        return {"k": found[arm], "n": planted[arm], "lo": lo, "hi": hi}
    out = {"date": "2026-11-09", "host": "claude-code",
           "wraith_ref": "v0.8.3 (d7e2c3c)",
           "judge": "rejudge: reply + written and edited text",
           "tasks": {"plan-review": {
               "with": side("with"), "without": side("without"),
               "by_category": {k: {a: {"k": cat[k][a], "n": cat_n[k][a]}
                                   for a in ARMS} for k in sorted(cat)}}}}
    with open(json_path, "w") as f:
        json.dump(out, f, indent=2)
