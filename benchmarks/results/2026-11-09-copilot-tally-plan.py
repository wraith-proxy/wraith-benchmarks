"""Copilot CLI plan-review tally (wraith v0.8.3, 9 November 2026),
copied from 2026-11-07-tally.py. Cost is estimated AI credits.
Originally: plan-review tally for the v0.6.0 rerun: per-case table, Wilson 95%
per arm, judge splits, plus category, cost and trace counts.

Reads, for each 2026-11-07-pNN out dir, only the attempt dir that
state.json names for the case (plan-review -> complete -> case).
Other attempt dirs hold runs cut off by the usage limit.
Usage: python3 -I 2026-11-09-copilot-tally-plan.py <results-root> [--json PATH]
"""
import collections
import glob
import json
import math
import os
import re
import statistics as st
import sys

args = sys.argv[1:]
json_path = None
if "--json" in args:
    i = args.index("--json")
    json_path = args[i + 1]
    del args[i:i + 2]
root = args[0]


def wilson(k, n, z=1.96):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


cases = {}


def cost(r):
    return r.get("meta", {}).get("ai_credits_est") or 0


src = {}
attempt_dir = {}
skipped = []
counted = []
for out in sorted(glob.glob(f"{root}/2026-11-09-copilot-plan-review")):
    state = json.load(open(f"{out}/state.json"))["plan-review"]
    for name, rel in state["complete"].items():
        adir = f"{out}/{rel}"
        counted.append(f"{out[len(root) + 1:]}/{rel}")
        for a in state["attempts"]:
            if a["dir"] != rel:
                skipped.append(f"{out[len(root) + 1:]}/{a['dir']}")
        paths = [p for p in glob.glob(f"{adir}/*.json")
                 if not p.endswith("usage.json")]
        assert len(paths) == 1, paths
        path = paths[0]
        for c in json.load(open(path))["cases"]:
            if c["name"] != name:
                continue
            assert c["name"] not in cases, f"duplicate {c['name']}"
            cases[c["name"]] = c
            src[c["name"]] = path[len(root) + 1:]
            attempt_dir[c["name"]] = adir

found = collections.Counter()
planted = collections.Counter()
cat = collections.defaultdict(collections.Counter)
cat_n = collections.defaultdict(collections.Counter)
splits = total_votes = 0
split_arm = collections.Counter()
bad = []
per_case = {}
print("| Case | Arm | Runs | Found / planted | Mean | SD | Turns | "
      "Mean s | Mean credits | Source |")
print("|---|---|---|---|---|---|---|---|---|---|")
for name in sorted(cases):
    for arm, runs in cases[name]["arms"].items():
        k = n = 0
        for r in runs:
            if r.get("error") or r["turns"] <= 1:
                bad.append((name, arm, r.get("error")))
            for g in r["graders"]:
                n += 1
                k += bool(g["passed"])
                key = g["name"].split("-", 1)[1]
                cat[key][arm] += bool(g["passed"])
                cat_n[key][arm] += 1
                m = re.search(r"judge votes: ([A-Z ]+)",
                              g.get("explanation", ""))
                if m:
                    v = m.group(1).split()
                    total_votes += 1
                    s = len(set(v)) > 1
                    splits += s
                    split_arm[arm] += s
        found[arm] += k
        planted[arm] += n
        per_case[(name, arm)] = k
        s = [r["score"] for r in runs]
        t = [r["turns"] for r in runs]
        print(f"| {name[-3:]} | {arm} | {len(runs)} | {k} / {n} | "
              f"{st.mean(s):.2f} | {st.pstdev(s):.2f} | "
              f"{min(t)}-{max(t)} | "
              f"{st.mean(r['durationSeconds'] for r in runs):.0f} | "
              f"{st.mean(cost(r) for r in runs):.3f} | "
              f"`{src[name]}` |")

print()
for arm in ("with", "without"):
    lo, hi = wilson(found[arm], planted[arm])
    print(f"- {arm}: {found[arm]}/{planted[arm]} = "
          f"{found[arm] / planted[arm]:.1%} (Wilson 95% {lo:.1%} to "
          f"{hi:.1%})")
print(f"- cases: {len(cases)}; judge 2-1 splits: {splits}/{total_votes} "
      f"(with {split_arm['with']}, without {split_arm['without']})")
print(f"- suspect runs (error or <=1 turn): {len(bad)} {bad[:3]}")

w = [n for n in sorted(cases)
     if per_case[(n, "with")] > per_case[(n, "without")]]
tie = [n[-3:] for n in sorted(cases)
       if per_case[(n, "with")] == per_case[(n, "without")]]
lose = [f"{n[-3:]} {per_case[(n, 'with')]}/{per_case[(n, 'without')]}"
        for n in sorted(cases)
        if per_case[(n, "with")] < per_case[(n, "without")]]
print(f"- with higher: {len(w)}; tied: {tie}; lower: {lose}")

print("\n| Category | with | without |\n|---|---|---|")
for key in sorted(cat):
    print(f"| {key} | {cat[key]['with']} / {cat_n[key]['with']} | "
          f"{cat[key]['without']} / {cat_n[key]['without']} |")

print("\n| Arm | Runs | Turns | Seconds | Credits | Total credits | Judge USD |")
print("|---|---|---|---|---|---|---|")
tot = judge = 0
for arm in ("with", "without"):
    runs = [r for c in cases.values() for r in c["arms"][arm]]
    a = sum(cost(r) for r in runs)
    j = sum(r.get("judgeCostUsd") or 0 for r in runs)
    tot += a
    judge += j
    print(f"| {arm} | {len(runs)} | "
          f"{st.mean(r['turns'] for r in runs):.1f} | "
          f"{st.mean(r['durationSeconds'] for r in runs):.0f} | "
          f"{st.mean(cost(r) for r in runs):.3f} | {a:.2f} | "
          f"{j:.2f} |")
print(f"- agent total {tot:.2f}, judge total {judge:.2f}")


def trace_of(name, r):
    return f"{attempt_dir[name]}/{r['tracePath']}"


print("\n## Traces")
for arm in ("with", "without"):
    skill_runs = two_turn = missing = 0
    skills = collections.Counter()
    first = collections.Counter()
    two_turn_scores = []
    for name in sorted(cases):
        for r in cases[name]["arms"][arm]:
            if r["turns"] == 2:
                two_turn += 1
                two_turn_scores.append(r["score"])
            p = trace_of(name, r)
            if not os.path.exists(p):
                missing += 1
                continue
            used = []
            for line in open(p):
                ev = json.loads(line)
                if ev.get("type") != "assistant":
                    continue
                for b in ev["message"].get("content", []):
                    if (b.get("type") == "tool_use"
                            and b.get("name") == "Skill"):
                        used.append(b["input"].get("skill", "?"))
            if used:
                skill_runs += 1
                first[used[0]] += 1
            skills.update(used)
    n = sum(len(c["arms"][arm]) for c in cases.values())
    mean2 = (f"{st.mean(two_turn_scores):.2f}" if two_turn_scores
             else "n/a")
    print(f"- {arm}: {skill_runs}/{n} runs called Skill; calls "
          f"{dict(skills)}; first call {dict(first)}; 2-turn runs "
          f"{two_turn}/{n} (mean score {mean2}); traces missing "
          f"{missing}")

print("\n## Routed models (Copilot Fusion)\n")
print("| Case | with | without | Same model both arms |\n|---|---|---|---|")
for name in sorted(cases):
    ms = {arm: collections.Counter(
        m for r in cases[name]["arms"][arm]
        for m in r.get("meta", {}).get("models_called") or ["?"])
        for arm in ("with", "without")}
    same = ms["with"] == ms["without"]
    print(f"| {name[-3:]} | {dict(ms['with'])} | {dict(ms['without'])} | "
          f"{'yes' if same else '**no**'} |")

print(f"\n- attempt dirs not counted: {sorted(set(skipped) - set(counted))}")

if json_path:
    def side(arm):
        lo, hi = wilson(found[arm], planted[arm])
        return {"k": found[arm], "n": planted[arm], "lo": lo, "hi": hi}

    out = {
        "date": "2026-11-09", "host": "copilot-cli",
        "wraith_ref": "v0.8.3 (d7e2c3c)", "model": "auto (intelligence), Fusion-routed",
        "tasks": {"plan-review": {
            "with": side("with"), "without": side("without"),
            "by_category": {key: {arm: {"k": cat[key][arm],
                                        "n": cat_n[key][arm]}
                                  for arm in ("with", "without")}
                            for key in sorted(cat)}}}}
    with open(json_path, "w") as f:
        json.dump(out, f, indent=2)
