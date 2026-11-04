#!/usr/bin/env python3
"""Run the wraith with-versus-without benchmark. Stdlib only.

uv run benchmarks/run.py --task plan-review --out benchmarks/results/DATE/
Add --dry-run to print the exact commands instead of running a model.
"""

import argparse
import datetime
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
# Subscription limits are not scored as fails. The eval exit status for
# them is unknown until calibration, so match the text of the output.
USAGE_LIMIT = re.compile(
    r"usage limit|rate[ _-]?limit|limit reached|too many requests|"
    r"\b429\b",
    re.IGNORECASE,
)


class BenchError(Exception):
    pass


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check_task(task):
    if task == "cost":
        raise BenchError(
            "task 'cost' is deferred and not implemented: no fixtures and "
            "no dry-run proxy exist. Use plan-review, guard or contracts."
        )
    if task not in TASKS:
        raise BenchError(f"unknown task {task!r}; choose from {sorted(TASKS)}")


def check_auth(env, credentials, dry_run):
    if env.get("ANTHROPIC_API_KEY"):
        raise BenchError(
            "ANTHROPIC_API_KEY is set. This would bill the API instead of "
            "the subscription. Unset it and rerun."
        )
    if not dry_run and not Path(credentials).is_file():
        raise BenchError(f"credentials file not found: {credentials}")


def eval_command(task, runs, cap, case=None, root="/work"):
    cmd = [
        "claude", "plugin", "eval", root, "--trust-plugin", "--scaffold",
        "--eval-dir", f"bench-{task}",
        "--allow-tools", *TASKS[task],
        "--ablation", "with-without", "--runs", str(runs),
        "--model", AGENT_MODEL, "--judge-model", JUDGE_MODEL,
        "--max-cost-usd", str(cap), "--no-publish",
        "--json", f"{root}/bench-{task}/results/{task}.json",
    ]
    if case:
        cmd += ["--case", case]
    return cmd


def docker_command(image, clone, credentials, cmd, uid, gid):
    return [
        "docker", "run", "--rm", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--user", f"{uid}:{gid}",
        "--tmpfs", f"/home/bench:rw,uid={uid},gid={gid},mode=0700,size=256m",
        "--tmpfs", "/tmp",
        "-v", f"{clone}:/work",
        "-v", f"{credentials}:/run/bench/credentials.json:ro",
        image, *cmd,
    ]


def detect_usage_limit(text):
    return bool(USAGE_LIMIT.search(text or ""))


def completed_cases(result, names):
    """Case names with a finished score in an eval JSON result.

    Assumes cases are dicts with "name" and a numeric "score" and not
    "errored". TODO(verify) against the calibration --json.
    """
    done = set()

    def walk(node):
        if isinstance(node, dict):
            if (node.get("name") in names
                    and isinstance(node.get("score"), (int, float))
                    and not node.get("errored")):
                done.add(node["name"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(result)
    return done


def first_write(events, path):
    """Content of the first Write to `path` in transcript events.

    Assumes Claude Code transcript lines: assistant messages whose
    content has tool_use blocks named Write with input.file_path and
    input.content. TODO(verify) against a real transcript.
    """
    for event in events:
        message = event.get("message") if isinstance(event, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            continue
        for block in content:
            if (isinstance(block, dict) and block.get("type") == "tool_use"
                    and block.get("name") == "Write"):
                args = block.get("input") or {}
                if str(args.get("file_path", "")).endswith(path):
                    return args.get("content")
    return None


def validate_contract(path, schema=SCHEMA):
    proc = subprocess.run(
        ["uvx", "--from", "check-jsonschema==0.39.0", "check-jsonschema",
         "--schemafile", str(schema), str(path)],
        capture_output=True, text=True,
    )
    return {"file": str(path), "valid": proc.returncode == 0,
            "output": (proc.stdout + proc.stderr).strip()}


def validate_dir(out):
    """Validate every contracts/*.yaml found under out (delivered file)."""
    results = [validate_contract(p) for p in
               sorted(Path(out).glob("**/contracts/*.yaml"))]
    record = {"schema_sha256": sha256_file(SCHEMA), "results": results}
    (Path(out) / "validation.json").write_text(json.dumps(record, indent=2))
    return record


def run_task(args, task, clone_root, out):
    cap = args.max_cost_usd if args.max_cost_usd is not None else "<cap>"
    clone = clone_root / f"clone-{task}"
    subprocess.run(
        ["git", "-c", "advice.detachedHead=false", "clone", "--quiet", "--depth", "1", "--branch",
         args.wraith_ref, args.wraith_repo, str(clone)], check=True)
    sha = subprocess.run(["git", "-C", str(clone), "rev-parse", "HEAD"],
                         capture_output=True, text=True, check=True
                         ).stdout.strip()
    try:
        bench = clone / f"bench-{task}"
        shutil.copytree(HERE / "fixtures" / task, bench)
        cmd = eval_command(task, args.runs, cap, args.case)
        full = docker_command(args.image, clone, args.credentials, cmd,
                              os.getuid(), os.getgid())
        print(f"[{task}] wraith {args.wraith_ref} = {sha}")
        print(f"[{task}] eval command: {' '.join(cmd)}")
        print(f"[{task}] container command: {' '.join(full)}")
        results = bench / "results"
        results.mkdir(exist_ok=True)
        status = "done"
        if args.dry_run:
            (results / "DRY-RUN").write_text("no model was called\n")
        else:
            proc = subprocess.run(full, capture_output=True, text=True)
            (results / "run.log").write_text(proc.stdout + proc.stderr)
            if detect_usage_limit(proc.stdout + proc.stderr):
                status = "usage_limit"
            elif proc.returncode != 0:
                status = f"exit_{proc.returncode}"
        dest = out / task
        shutil.copytree(results, dest, dirs_exist_ok=True)
        return {"task": task, "wraith_sha": sha, "status": status}
    finally:
        shutil.rmtree(clone, ignore_errors=True)


def main(argv=None, env=None):
    env = os.environ if env is None else env
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--task", default="all")
    ap.add_argument("--wraith-ref", default="v0.5.10")
    ap.add_argument("--wraith-repo", default=DEFAULT_REPO)
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--case")
    ap.add_argument("--max-cost-usd", type=float)
    ap.add_argument("--out")
    ap.add_argument("--image", default="wraith-bench:latest")
    ap.add_argument("--credentials",
                    default=str(Path.home() / ".claude/.credentials.json"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--validate", metavar="DIR",
                    help="validate delivered contracts under DIR, no run")
    args = ap.parse_args(argv)
    try:
        if args.validate:
            print(json.dumps(validate_dir(args.validate), indent=2))
            return 0
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
    out = Path(args.out or HERE / "results" / date)
    out.mkdir(parents=True, exist_ok=True)
    state_file = out / "state.json"
    state = json.loads(state_file.read_text()) if state_file.exists() else {}
    manifest = {
        "date": date, "wraith_ref": args.wraith_ref, "runs": args.runs,
        "agent_model": AGENT_MODEL, "judge_model": JUDGE_MODEL,
        "image": args.image, "dry_run": args.dry_run,
        "odcs_schema_sha256": sha256_file(SCHEMA),
        "auth": "subscription credentials mounted read-only",
    }
    code = 0
    with tempfile.TemporaryDirectory(prefix="wraith-bench-") as tmp:
        for task in tasks:
            if args.resume and state.get(task, {}).get("status") == "done":
                print(f"[{task}] already done, skipping")
                continue
            state[task] = run_task(args, task, Path(tmp), out)
            state_file.write_text(json.dumps(state, indent=2))
            if state[task]["status"] == "usage_limit":
                print(f"[{task}] subscription usage limit hit; stopping. "
                      "Rerun with --resume later.", file=sys.stderr)
                code = 3
                break
    manifest["tasks"] = state
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
