#!/usr/bin/env python3
"""Run the wraith with-versus-without benchmark. Stdlib only.

uv run benchmarks/run.py --task plan-review --max-cost-usd 20 --out DIR
Add --dry-run to print the exact commands instead of running a model.

Eval JSON shape (read from the claude 2.1.318 binary, not yet seen in a
real run): case reports with "name", "runs" (the with arm) and
"runs_without"; each run has "score", "error", "trace_path" and may have
"ended_on_api_error" or "auth_rejected". An unrecognised shape fails loud.
"""

import argparse
import datetime
import fnmatch
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCHEMA = HERE / "schemas" / "odcs-json-schema-v3.2.0.json"
AGENT_MODEL = "claude-sonnet-5-5"
JUDGE_MODEL = "claude-haiku-5-5"
DEFAULT_REPO = "https://github.com/wraith-proxy/wraith-skills.git"
TASKS = {
    "plan-review": ["Read", "Glob", "Grep", "Skill", "Write", "Edit"],
    "guard": ["Bash", "Read"],
    "contracts": ["Read", "Write", "Edit", "Glob", "Grep", "Skill", "Bash"],
}
# Applied only to the error text of a run flagged ended_on_api_error, never
# to agent output. TODO(verify): narrow to the CLI's exact message once a
# real subscription limit has been seen.
USAGE_LIMIT = re.compile(
    r"usage limit|hit your limit|rate limit|limit reached|"
    r"out of (extra )?usage|too many requests",
    re.IGNORECASE,
)
EXIT = {"done": 0, "dry_run": 0, "usage_limit": 3}


class BenchError(Exception):
    pass


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def case_names(task, pattern=None):
    names = sorted(f"{task}-{d.name}" for d in
                   (HERE / "fixtures" / task).iterdir() if d.is_dir())
    if not pattern:
        return names
    # eval matches --case against the full name, so accept a short id too
    return [n for n in names if fnmatch.fnmatch(n, pattern)
            or fnmatch.fnmatch(n, f"{task}-{pattern}")]


def check_task(task):
    if task == "cost":
        raise BenchError(
            "task 'cost' is deferred and not implemented: no fixtures and "
            "no dry-run proxy exist. Use plan-review, guard or contracts."
        )
    if task not in TASKS:
        raise BenchError(f"unknown task {task!r}; choose from {sorted(TASKS)}")


def check_auth(env, credentials, dry_run):
    if "ANTHROPIC_API_KEY" in env:
        raise BenchError(
            "ANTHROPIC_API_KEY is set. This would bill the API instead of "
            "the subscription. Unset it and rerun."
        )
    if not dry_run and not Path(credentials).is_file():
        raise BenchError(f"credentials file not found: {credentials}")


def eval_command(task, runs, cap, case=None, root="/work", json_name=None,
                 keep_temp=False):
    cmd = [
        "claude", "plugin", "eval", root, "--trust-plugin", "--scaffold",
        "--eval-dir", f"bench-{task}",
        "--allow-tools", *TASKS[task],
        "--ablation", "with-without", "--runs", str(runs),
        "--model", AGENT_MODEL, "--judge-model", JUDGE_MODEL,
        "--max-cost-usd", str(cap), "--no-publish",
        "--json", f"{root}/bench-{task}/results/{json_name or task}.json",
    ]
    if case:
        cmd += ["--case", case]
    if keep_temp:
        cmd.append("--keep-temp")
    return cmd


def docker_command(image, clone, credentials, cmd, uid, gid, tmpdir=None):
    return [
        "docker", "run", "--rm", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--user", f"{uid}:{gid}",
        "--tmpfs", f"/home/bench:rw,uid={uid},gid={gid},mode=0700,size=256m",
        *(["-v", f"{tmpdir}:/tmp"] if tmpdir else ["--tmpfs", "/tmp"]),
        "-v", f"{clone}:/work",
        "-v", f"{credentials}:/run/bench/credentials.json:ro",
        image, *cmd,
    ]


def run_container(full):
    proc = subprocess.run(full, capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


# ---- eval JSON

def arms_of(report):
    """(with, without) run lists. Real shape: report["arms"]["with"|"without"]
    (seen in a 2.1.316 eval JSON); the older in-memory shape is accepted."""
    if isinstance(report.get("arms"), dict):
        return (report["arms"].get("with", []),
                report["arms"].get("without", []))
    return report["runs"], report.get("runs_without", [])


def find_case_reports(data):
    """Case reports: dicts with a str "name" and "arms" (or "runs")."""
    found = []

    def walk(node):
        if isinstance(node, dict):
            if isinstance(node.get("name"), str) and (
                    isinstance(node.get("arms"), dict)
                    or isinstance(node.get("runs"), list)):
                found.append(node)
            else:
                for value in node.values():
                    walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(data)
    if not found:
        raise BenchError("unrecognised eval JSON: no case report found")
    return found


def flag(run, name):
    camel = re.sub(r"_(\w)", lambda m: m.group(1).upper(), name)
    return run.get(name) or run.get(camel)


def classify(data, expected_runs, expected_cases):
    """Split cases into complete and incomplete, flag limit and auth.

    A run with an error and no turns never started (for example the
    sandbox was unavailable). eval still scores it, so it is reported as a
    harness error and its case is not complete.
    """
    reports = {r["name"]: r for r in find_case_reports(data)}
    limit = auth = False
    complete, failures, harness = [], [], []
    for name in expected_cases:
        report = reports.get(name)
        if report is None:
            continue
        arms = dict(zip(("with", "without"), arms_of(report)))
        clean = all(len(runs) == expected_runs for runs in arms.values())
        for arm, runs in arms.items():
            for run in runs:
                if not isinstance(run, dict):
                    raise BenchError("unrecognised eval JSON: run not a dict")
                err = str(run.get("error") or "")
                if flag(run, "auth_rejected"):
                    auth, clean = True, False
                elif flag(run, "ended_on_api_error") and USAGE_LIMIT.search(
                        err):
                    limit, clean = True, False
                elif err and not run.get("turns"):
                    harness.append({"case": name, "arm": arm, "error": err})
                    clean = False
                elif err:
                    failures.append({"case": name, "arm": arm, "error": err})
        if clean:
            complete.append(name)
    return {"complete": complete, "usage_limit": limit, "auth_failed": auth,
            "failures": failures, "harness_errors": harness}


# ---- transcripts and contracts

def tool_use_blocks(node):
    """Yield tool_use blocks in order from any nesting of dicts/lists."""
    if isinstance(node, dict):
        if node.get("type") == "tool_use":
            yield node
        else:
            for value in node.values():
                yield from tool_use_blocks(value)
    elif isinstance(node, list):
        for value in node:
            yield from tool_use_blocks(value)


def first_write(events, path):
    """Content of the first Write to `path` in the transcript events."""
    for block in tool_use_blocks(events):
        args = block.get("input") or {}
        if block.get("name") == "Write" and str(
                args.get("file_path", "")).endswith(path):
            return args.get("content")
    return None


def delivered_file(events, path):
    """Replay Write and Edit calls on `path`. Returns (content, bash_touched).

    Bash edits cannot be replayed, so bash_touched flags a Bash command
    that names the file; the delivered result is then approximate.
    """
    content, touched = None, False
    for block in tool_use_blocks(events):
        args = block.get("input") or {}
        name = block.get("name")
        if name == "Bash" and Path(path).name in str(args.get("command", "")):
            touched = True
        if not str(args.get("file_path", "")).endswith(path):
            continue
        if name == "Write":
            content = args.get("content")
        elif name == "Edit" and content is not None:
            old, new = args.get("old_string", ""), args.get("new_string", "")
            count = -1 if args.get("replace_all") else 1
            content = content.replace(old, new, count)
    return content, touched


def load_trace(path):
    text = Path(path).read_text()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    except json.JSONDecodeError as err:
        raise BenchError(f"unrecognised trace format in {path}: {err}")


def resolve_trace(trace_path, attempt_dir, task):
    """Traces are written under /tmp/claude-eval-X/out in the container;
    collect_traces copies them to <attempt>/traces/claude-eval-X/."""
    m = re.match(r"/tmp/(claude-eval-[^/]+)/out/(.+)$", trace_path)
    if m:
        return Path(attempt_dir) / "traces" / m.group(1) / m.group(2)
    return Path(attempt_dir) / trace_path


def collect_traces(tmpdir, results):
    for trace in Path(tmpdir).glob("claude-eval-*/out/trace.jsonl"):
        dest = Path(results) / "traces" / trace.parent.parent.name
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(trace, dest / trace.name)


def trace_usage(events):
    """Token usage from the trace's final `result` event (seen in a real
    trace: usage.input_tokens, cache_creation_input_tokens,
    cache_read_input_tokens, output_tokens). None if there is no result."""
    for event in reversed(events if isinstance(events, list) else []):
        if isinstance(event, dict) and event.get("type") == "result":
            usage = event.get("usage") or {}
            keys = ("input_tokens", "cache_creation_input_tokens",
                    "cache_read_input_tokens", "output_tokens")
            return {k: usage.get(k, 0) for k in keys} | {
                "duration_ms": event.get("duration_ms"),
                "cost_usd": event.get("total_cost_usd")}
    return None


def summarise_usage(attempt_dir, data, task):
    rows = []
    for report in find_case_reports(data):
        for arm, runs in zip(("with", "without"), arms_of(report)):
            for i, run in enumerate(runs):
                row = {"case": report["name"], "arm": arm, "run": i,
                       "score": run.get("score"), "turns": run.get("turns"),
                       "seconds": run.get("durationSeconds"),
                       "cost_usd": run.get("costUsd"),
                       "judge_cost_usd": run.get("judgeCostUsd")}
                try:
                    events = load_trace(resolve_trace(
                        run.get("tracePath") or "", attempt_dir, task))
                    row["tokens"] = trace_usage(events)
                except (OSError, BenchError):
                    row["tokens"] = None
                rows.append(row)
    (Path(attempt_dir) / "usage.json").write_text(json.dumps(rows, indent=2))
    return rows


def validate_contract(path, schema=SCHEMA):
    proc = subprocess.run(
        ["uvx", "--from", "check-jsonschema==0.39.0", "check-jsonschema",
         "--schemafile", str(schema), str(path)],
        capture_output=True, text=True,
    )
    return {"valid": proc.returncode == 0,
            "output": (proc.stdout + proc.stderr).strip()}


def validate_text(content, validator):
    if content is None:
        return {"valid": False, "output": "no content"}
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "contract.yaml"
        f.write_text(content)
        return validator(f)


def score_contracts(attempt_dir, data, validator=validate_contract):
    """Validate first write and delivered file per case, arm and run."""
    cases, summary, unavailable = {}, {}, 0
    for report in find_case_reports(data):
        table = report["name"].removeprefix("contracts-")
        path = f"contracts/{table}.yaml"
        arms = dict(zip(("with", "without"), arms_of(report)))
        cases[report["name"]] = {}
        for arm, runs in arms.items():
            tally = summary.setdefault(arm, {"runs": 0, "first_write_valid": 0,
                                             "delivered_valid": 0})
            rows = []
            for run in runs:
                tally["runs"] += 1
                try:
                    events = load_trace(resolve_trace(
                        run.get("tracePath") or run.get("trace_path") or "",
                        attempt_dir, "contracts"))
                except (OSError, BenchError) as err:
                    unavailable += 1
                    rows.append({"error": f"trace unavailable: {err}"})
                    continue
                first = validate_text(first_write(events, path), validator)
                content, touched = delivered_file(events, path)
                final = validate_text(content, validator)
                tally["first_write_valid"] += first["valid"]
                tally["delivered_valid"] += final["valid"]
                rows.append({"first_write": first, "delivered": final,
                             "bash_touched": touched})
            cases[report["name"]][arm] = rows
    record = {"schema_sha256": sha256_file(SCHEMA), "summary": summary,
              "cases": cases, "traces_unavailable": unavailable}
    (Path(attempt_dir) / "validation.json").write_text(
        json.dumps(record, indent=2))
    total = sum(t["runs"] for t in summary.values())
    if total and unavailable == total:
        raise BenchError("no trace could be read; trace path or format "
                         "differs from what run.py assumes")
    return record


# ---- secrets

def credential_secrets(path):
    values = []

    def walk(node):
        if isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
        elif isinstance(node, str) and len(node) >= 16:
            values.append(node)

    walk(json.loads(Path(path).read_text()))
    return values


def scan_for_secrets(directory, secrets):
    for f in Path(directory).rglob("*"):
        if f.is_file():
            text = f.read_text(errors="ignore")
            if any(s in text for s in secrets):
                raise BenchError(f"credential value found in {f}; "
                                 "results not copied")


# ---- runner

def run_task(args, task, tmp, out, state):
    names = case_names(task, args.case)
    if not names:
        raise BenchError(f"--case {args.case!r} matches no {task} case")
    prior = state.get(task, {"attempts": [], "complete": {}})
    remaining = [n for n in names if n not in prior["complete"]]
    attempt = len(prior["attempts"]) + 1
    per_case = attempt > 1
    kind = "dry-run" if args.dry_run else "attempt"
    for name in (kind, "failed"):
        dest = out / task / f"{name}-{attempt}"
        if dest.exists():
            raise BenchError(f"{dest} already exists; pass a new --out "
                             "or remove it")
    jobs = ([(n, n) for n in remaining] if per_case
            else [(args.case, None)])
    cap = args.max_cost_usd
    clone = Path(tmp) / f"clone-{task}"
    subprocess.run(
        ["git", "-c", "advice.detachedHead=false", "clone", "--quiet",
         "--depth", "1", "--branch", args.wraith_ref, args.wraith_repo,
         str(clone)], check=True)
    sha = subprocess.run(["git", "-C", str(clone), "rev-parse", "HEAD"],
                         capture_output=True, text=True, check=True
                         ).stdout.strip()
    try:
        shutil.copytree(HERE / "fixtures" / task, clone / f"bench-{task}")
        results = clone / f"bench-{task}" / "results"
        results.mkdir(exist_ok=True)
        tmpdir = Path(tmp) / f"tmp-{task}"
        tmpdir.mkdir()
        print(f"[{task}] wraith {args.wraith_ref} = {sha}, attempt {attempt}")
        complete, flags, failures, ran = [], [], [], 0
        for case, exact in jobs:
            jname = exact or task
            case_cap = ("<cap>" if cap is None
                        else round(cap * (1 / len(names) if per_case
                                          else 1), 2))
            if case and len(names) == 1:
                case = names[0]
            cmd = eval_command(task, args.runs, case_cap, case, json_name=jname,
                               keep_temp=args.keep_temp)
            full = docker_command(args.image, clone, args.credentials, cmd,
                                  os.getuid(), os.getgid(), tmpdir)
            print(f"[{task}] eval command: {' '.join(cmd)}")
            print(f"[{task}] container command: {' '.join(full)}")
            if args.dry_run:
                (results / "DRY-RUN").write_text("no model was called\n")
                continue
            code, text = run_container(full)
            ran += 1
            collect_traces(tmpdir, results)
            (results / f"{jname}.log").write_text(text)
            jf = results / f"{jname}.json"
            if not jf.is_file():
                raise BenchError(
                    f"no eval JSON for {jname} (exit {code}); see "
                    f"{jname}.log in the results, nothing is scored")
            try:
                result = classify(json.loads(jf.read_text()), args.runs, names)
            except BenchError as err:
                scan_for_secrets(results, credential_secrets(args.credentials))
                shutil.copytree(results, out / task / f"failed-{attempt}")
                tail = " | ".join(text.strip().splitlines()[-4:])
                raise BenchError(f"{err} (exit {code}; eval said: {tail})")
            complete += result["complete"]
            failures += result["failures"]
            if result["harness_errors"]:
                flags.append("harness_error")
                failures += result["harness_errors"]
            if result["auth_failed"]:
                flags.append("auth_failed")
            if result["usage_limit"]:
                flags.append("usage_limit")
            if flags:
                break
        if args.dry_run:
            shutil.copytree(results, out / task / f"{kind}-{attempt}")
            return {"status": "dry_run", "wraith_sha": sha}
        scan_for_secrets(results, credential_secrets(args.credentials))
        rel = f"{task}/attempt-{attempt}"
        shutil.copytree(results, out / rel)
        for jf in sorted(results.glob("*.json")):
            summarise_usage(out / rel, json.loads(jf.read_text()), task)
        if task == "contracts":
            for jf in sorted(results.glob("*.json")):
                score_contracts(out / rel, json.loads(jf.read_text()))
        entry = {"n": attempt, "dir": rel, "complete": complete,
                 "failures": failures}
        merged = dict(prior["complete"])
        merged.update({c: rel for c in complete})
        status = ("harness_error" if "harness_error" in flags else
                  "auth_failed" if "auth_failed" in flags else
                  "usage_limit" if "usage_limit" in flags else
                  "done" if set(names) <= set(merged) else "incomplete")
        return {"status": status, "wraith_sha": sha, "complete": merged,
                "attempts": prior["attempts"] + [entry]}
    finally:
        shutil.rmtree(clone, ignore_errors=True)


def main(argv=None, env=None):
    env = os.environ if env is None else env
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--task", default="all")
    ap.add_argument("--wraith-ref", default="v0.5.10")
    ap.add_argument("--wraith-repo", default=DEFAULT_REPO)
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--case", help="case name glob, calibration only")
    ap.add_argument("--max-cost-usd", type=float)
    ap.add_argument("--out")
    ap.add_argument("--image", default="wraith-bench:latest")
    ap.add_argument("--credentials",
                    default=str(Path.home() / ".claude/.credentials.json"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--keep-temp", action="store_true",
                    help="eval keeps its temp dirs so traces can be collected")
    args = ap.parse_args(argv)
    try:
        tasks = list(TASKS) if args.task == "all" else [args.task]
        for task in tasks:
            check_task(task)
        check_auth(env, args.credentials, args.dry_run)
        if not args.dry_run and args.max_cost_usd is None:
            raise BenchError("--max-cost-usd is required for a real run")
    except BenchError as err:
        print(f"error: {err}", file=sys.stderr)
        return 2
    date = datetime.date.today().isoformat()
    scratch = tempfile.mkdtemp(prefix="wraith-bench-out-") \
        if args.dry_run and not args.out else None
    out = Path(args.out or scratch or HERE / "results" / date)
    out.mkdir(parents=True, exist_ok=True)
    state_file = out / "state.json"
    state = {}
    if state_file.exists():
        if not args.resume:
            print(f"error: {state_file} exists; pass --resume or a new --out",
                  file=sys.stderr)
            return 2
        state = json.loads(state_file.read_text())
    code = 0
    with tempfile.TemporaryDirectory(prefix="wraith-bench-") as tmp:
        for task in tasks:
            if state.get(task, {}).get("status") == "done":
                print(f"[{task}] already done, skipping")
                continue
            try:
                state[task] = run_task(args, task, tmp, out, state)
            except BenchError as err:
                print(f"error: {err}", file=sys.stderr)
                state[task] = {**state.get(task, {"attempts": [],
                                                  "complete": {}}),
                               "status": "error", "error": str(err)}
                code = 4
            if not args.dry_run:
                state_file.write_text(json.dumps(state, indent=2))
            status = state[task]["status"]
            if status == "usage_limit":
                print(f"[{task}] subscription usage limit hit; stopping. "
                      "Rerun with --resume later.", file=sys.stderr)
                code = 3
                break
            if status not in ("done", "dry_run"):
                code = code or 4
    if not args.dry_run:
        (out / "manifest.json").write_text(json.dumps({
            "date": date, "wraith_ref": args.wraith_ref, "runs": args.runs,
            "agent_model": AGENT_MODEL, "judge_model": JUDGE_MODEL,
            "image": args.image, "odcs_schema_sha256": sha256_file(SCHEMA),
            "auth": "subscription credentials mounted read-only",
            "tasks": state}, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
