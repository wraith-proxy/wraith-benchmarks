"""Charts from tally JSON (the --json output of the tally scripts).

Usage: uv run --no-project --python 3.12 --with matplotlib==3.10.* \
    benchmarks/charts.py --tally a.json [b.json ...] --out DIR

Tally files with the same host are merged, so a host's plan-review file
and its guard/contracts file can be passed together. Every label and
number comes from the JSON.
"""
import argparse
import json
import pathlib

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

plt.rcParams["svg.hashsalt"] = "wraith"
plt.rcParams["svg.fonttype"] = "none"

ARMS = ("with", "without")
COLOURS = {
    "with": ("#1b7837", "#7fbf7b"),
    "without": ("#762a83", "#af8dc3"),
}
OUTCOME_COLOURS = {
    "attempted": "#e66101",
    "asked": "#5e3c99",
    "stopped": "#999999",
}


def load(paths):
    hosts = {}
    for path in paths:
        data = json.loads(pathlib.Path(path).read_text())
        host = hosts.setdefault(data["host"], {"tasks": {}})
        host["tasks"].update(data["tasks"])
    return hosts


def save(fig, out, name):
    fig.savefig(out / f"{name}.svg", dpi=150, metadata={"Date": None})
    fig.savefig(out / f"{name}.png", dpi=150, metadata={"Software": None})
    plt.close(fig)


def measures(tasks):
    """name -> {arm: (rate, lo, hi)}; guard is reported as not attempted."""
    out = {}
    if "plan-review" in tasks:
        out["plan-review found"] = {
            a: _rate(tasks["plan-review"][a]) for a in ARMS}
    if "guard" in tasks:
        out["guard not attempted"] = {
            a: _flip(tasks["guard"][a]["attempted"]) for a in ARMS}
    if "contracts" in tasks:
        out["contracts first-write valid"] = {
            a: _rate(tasks["contracts"][a]["first_write"]) for a in ARMS}
    return out


def _rate(s):
    return s["k"] / s["n"], s["lo"], s["hi"]


def _flip(s):
    return 1 - s["k"] / s["n"], 1 - s["hi"], 1 - s["lo"]


def headline(hosts, out):
    per_host = {h: measures(v["tasks"]) for h, v in hosts.items()}
    names = []
    for m in per_host.values():
        names += [n for n in m if n not in names]
    series = [(h, a) for h in hosts for a in ARMS]
    width = 0.8 / len(series)
    fig, ax = plt.subplots(figsize=(9, 5))
    for i, (host, arm) in enumerate(series):
        shade = COLOURS[arm][list(hosts).index(host) % 2]
        xs, ys, err = [], [], [[], []]
        for j, name in enumerate(names):
            if name not in per_host[host]:
                continue
            rate, lo, hi = per_host[host][name][arm]
            xs.append(j - 0.4 + width * (i + 0.5))
            ys.append(rate)
            err[0].append(rate - lo)
            err[1].append(hi - rate)
        ax.bar(xs, ys, width, color=shade, label=f"{host} {arm}",
               yerr=err, capsize=3)
    ax.set_xticks(range(len(names)), names)
    ax.set_ylim(0, 1)
    ax.set_ylabel("rate (Wilson 95%)")
    ax.legend()
    fig.tight_layout()
    save(fig, out, "headline")


def plan_review_categories(hosts, out):
    cats = []
    for v in hosts.values():
        pr = v["tasks"].get("plan-review")
        if pr:
            cats += [c for c in pr["by_category"] if c not in cats]
    series = [(h, a) for h, v in hosts.items()
              if "plan-review" in v["tasks"] for a in ARMS]
    width = 0.8 / max(len(series), 1)
    fig, ax = plt.subplots(figsize=(9, 5))
    for i, (host, arm) in enumerate(series):
        by = hosts[host]["tasks"]["plan-review"]["by_category"]
        shade = COLOURS[arm][list(hosts).index(host) % 2]
        xs = [j - 0.4 + width * (i + 0.5)
              for j, c in enumerate(cats) if c in by]
        ys = [by[c][arm]["k"] / by[c][arm]["n"] for c in cats if c in by]
        ax.bar(xs, ys, width, color=shade, label=f"{host} {arm}")
    ax.set_xticks(range(len(cats)), cats, rotation=30, ha="right")
    ax.set_ylim(0, 1)
    ax.set_ylabel("planted problems found")
    ax.legend()
    fig.tight_layout()
    save(fig, out, "plan-review-categories")


def guard_outcomes(hosts, out):
    labels, parts = [], {"attempted": [], "asked": [], "stopped": []}
    for host, v in hosts.items():
        g = v["tasks"].get("guard")
        if not g:
            continue
        for arm in ARMS:
            att = g[arm]["attempted"]
            asked = g[arm]["asked"]["k"]
            labels.append(f"{host} {arm}")
            parts["attempted"].append(att["k"])
            parts["asked"].append(asked)
            parts["stopped"].append(att["n"] - att["k"] - asked)
    fig, ax = plt.subplots(figsize=(9, 5))
    bottom = [0] * len(labels)
    for key, vals in parts.items():
        ax.bar(labels, vals, bottom=bottom, color=OUTCOME_COLOURS[key],
               label=key)
        bottom = [b + x for b, x in zip(bottom, vals)]
    ax.set_ylabel("guard runs")
    ax.legend()
    fig.tight_layout()
    save(fig, out, "guard-outcomes")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tally", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    hosts = load(args.tally)
    headline(hosts, out)
    plan_review_categories(hosts, out)
    guard_outcomes(hosts, out)


if __name__ == "__main__":
    main()
