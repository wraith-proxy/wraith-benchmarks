"""Plan-review tally: per-case table, Wilson 95% per arm, judge splits.

Reads r2 attempt-1 for p01-p05 (p06-p12 there are usage-limit zeros)
and every r3-pNN dir. Usage: python3 -I tally.py <results-root>
"""
import collections
import glob
import json
import math
import re
import statistics as st
import sys

root = sys.argv[1]
R2 = "2026-11-04-r2/plan-review/attempt-1/plan-review.json"
VALID_R2 = {f"plan-review-p0{i}" for i in range(1, 6)}


def wilson(k, n, z=1.96):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


cases = {}
src = {}
for path in [f"{root}/{R2}"] + sorted(
        glob.glob(f"{root}/2026-11-04-r3-p*/plan-review/attempt-*/"
                  "plan-review.json")):
    for c in json.load(open(path))["cases"]:
        if path.endswith(R2) and c["name"] not in VALID_R2:
            continue
        assert c["name"] not in cases, f"duplicate {c['name']}"
        cases[c["name"]] = c
        src[c["name"]] = path[len(root) + 1:]

found = collections.Counter()
planted = collections.Counter()
splits = total_votes = 0
bad = []
print("| Case | Arm | Runs | Found / planted | Mean | SD | Turns | "
      "Mean s | Mean USD | Source |")
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
                m = re.search(r"judge votes: ([A-Z ]+)",
                              g.get("explanation", ""))
                if m:
                    v = m.group(1).split()
                    total_votes += 1
                    splits += len(set(v)) > 1
        found[arm] += k
        planted[arm] += n
        s = [r["score"] for r in runs]
        t = [r["turns"] for r in runs]
        print(f"| {name[-3:]} | {arm} | {len(runs)} | {k} / {n} | "
              f"{st.mean(s):.2f} | {st.pstdev(s):.2f} | "
              f"{min(t)}-{max(t)} | "
              f"{st.mean(r['durationSeconds'] for r in runs):.0f} | "
              f"{st.mean(r['costUsd'] for r in runs):.3f} | "
              f"`{src[name]}` |")

print()
for arm in ("with", "without"):
    lo, hi = wilson(found[arm], planted[arm])
    print(f"- {arm}: {found[arm]}/{planted[arm]} = "
          f"{found[arm] / planted[arm]:.1%} (Wilson 95% {lo:.1%} to "
          f"{hi:.1%})")
print(f"- cases: {len(cases)}; judge 2-1 splits: {splits}/{total_votes}")
print(f"- suspect runs (error or <=1 turn): {len(bad)} {bad[:3]}")
