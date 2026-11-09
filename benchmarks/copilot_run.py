#!/usr/bin/env python3
"""Run the wraith with-versus-without benchmark on GitHub Copilot CLI.

uv run benchmarks/copilot_run.py --task guard --model M --max-ai-credits N \
    --token-file F --out DIR
Add --dry-run to print the exact commands instead of running a model.

Copilot's JSONL event shapes, tool names, limit text and egress hosts are not
yet verified; the tables marked TODO(verify) are filled in by --calibrate.
Stdlib only; reuses the pure functions of run.py.
"""

import argparse
import datetime
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import run
from run import BenchError

HERE = run.HERE
DEFAULT_IMAGE = "wraith-bench-copilot:1.0.105"
TOKEN_ENV = "COPILOT_GITHUB_TOKEN"
WALL_TIMEOUT = 600
PROBE_PROMPT = "List the skills and agents you can use."
# Claude-named tools per task, as in run.TASKS (same tool set in both arms).
TOOLS = run.TASKS
# Claude tool name -> Copilot tool names offering it. Source: the Copilot
# 1.0.105 bundle and calibration-5 traces. Names passed to --available-tools
# that Copilot lacks are ignored. TODO(verify: argument keys of bash, create,
# edit and apply_patch not yet observed).
TOOL_MAP = {
    "Bash": ["bash", "read_bash", "write_bash", "stop_bash", "list_bash"],
    "Read": ["view"],
    "Write": ["create", "apply_patch"],
    "Edit": ["edit", "str_replace_editor", "apply_patch"],
    "Glob": ["glob"],
    "Grep": ["grep", "rg"],
    "Skill": ["skill"],
}
# Copilot tool name seen in traces -> Claude name. None: known, but produces
# no normalised call, or is resolved per call in expand_call.
TOOL_NAMES = {
    "skill": "Skill", "view": "Read", "glob": "Glob",
    "bash": "Bash", "shell": "Bash",
    "create": "Write", "edit": "Edit",
    "grep": "Grep", "rg": "Grep",
    "str_replace_editor": None, "apply_patch": None,
    "read_bash": None, "write_bash": None, "stop_bash": None,
    "list_bash": None,
}
# Claude input key -> Copilot argument key. Write content is file_text or
# content, see tool_input. Shell/Write/Edit are TODO(verify: not yet
# observed).
ARG_MAP = {
    "Bash": {"command": "command"},
    "Read": {"file_path": "path"},
    "Glob": {"pattern": "pattern"},
    "Grep": {"pattern": "pattern"},
    "Write": {"file_path": "path"},
    "Edit": {"file_path": "path", "old_string": "old_str",
             "new_string": "new_str"},
    "Skill": {"skill": "skill"},
}
# Observed event types that carry nothing we score. Tool calls come from
# tool.execution_start only; assistant.message toolRequests would double
# count. Unknown types still raise.
IGNORED_EVENTS = {
    "user.message", "assistant.turn_start", "assistant.turn_end",
    "assistant.message_start", "assistant.message_delta",
    "assistant.reasoning", "assistant.reasoning_delta",
    "assistant.tool_call_delta", "assistant.idle",
    "model.call_start", "model.call_finished", "model.call_final_result",
    "tool.execution_complete", "tool.execution_partial_result",
    "tool.shell_output", "prompt_cache_break", "result", "error",
}
# TODO(verify): broad on purpose; applied to stderr and error events only.
COPILOT_LIMIT = re.compile(
    r"quota exceeded|rate limit|premium request|usage limit", re.IGNORECASE)
OVER_TURNS = 12
CUT_ERRORS = ("timeout", "truncated output")
REDACTED = "[redacted]"
MODEL_KEYS = ("model", "newModel", "selectedModel")


# ---- events

def redact(text, secrets):
    for secret in secrets:
        if secret:
            text = text.replace(secret, REDACTED)
    return text


def redact_obj(node, secrets):
    if isinstance(node, str):
        return redact(node, secrets)
    if isinstance(node, dict):
        return {redact(str(k), secrets): redact_obj(v, secrets)
                for k, v in node.items()}
    if isinstance(node, list):
        return [redact_obj(v, secrets) for v in node]
    return node


def dump_json(path, obj, secrets):
    Path(path).write_text(json.dumps(redact_obj(obj, secrets), indent=2))


def leaks(directory, secrets):
    """Relative paths under directory that contain a secret value."""
    root = Path(directory)
    secrets = [s for s in secrets if s]
    return sorted(
        str(f.relative_to(root)) for f in root.rglob("*")
        if f.is_file() and any(
            s in f.read_text(errors="ignore") for s in secrets))


def split_events(text):
    """(events, truncated). A final line that is cut off is dropped."""
    events = []
    lines = text.splitlines()
    for n, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError as err:
            if n == len(lines) - 1 and not text.endswith("\n"):
                return events, True
            raise BenchError(f"unrecognised event line: {err}: {line[:80]!r}")
    return events, False


def parse_events(text):
    return split_events(text)[0]


def _data(event):
    data = event.get("data", {})
    if not isinstance(data, dict):
        raise BenchError(f"unrecognised event data: {str(event)[:120]}")
    return data


def tool_input(claude_name, args):
    mapping = ARG_MAP.get(claude_name)
    if mapping is None:
        return dict(args)
    try:
        out = {k: args[v] for k, v in mapping.items()}
        if claude_name == "Write":
            out["content"] = args["file_text" if "file_text" in args
                                  else "content"]
    except KeyError as err:
        raise BenchError(
            f"{claude_name} call lacks argument {err}: {str(args)[:120]}")
    return out


PATCH_FILE = re.compile(r"^\*\*\* (Add|Update|Delete) File: (.+?)\s*$")


def patch_calls(text):
    """Normalised (name, input) pairs for each file block of a patch."""
    calls, add, lines = [], None, []

    def close():
        if add is not None:
            calls.append(("Write", {"file_path": add,
                                    "content": "\n".join(lines)}))

    for line in text.splitlines():
        match = PATCH_FILE.match(line)
        if match or line.startswith("*** End Patch"):
            close()
            add, lines = None, []
        if match:
            kind, path = match.groups()
            if kind == "Add":
                add = path
            elif kind == "Update":
                calls.append(("Edit", {"file_path": path}))
            else:
                calls.append(("Edit", {"file_path": path, "deleted": True}))
        elif add is not None and line.startswith("+"):
            lines.append(line[1:])
    close()
    return calls


def expand_call(tool, args):
    """Normalised (name, input) pairs for one Copilot tool call."""
    if tool == "apply_patch":
        raw = args.get("input", args.get("patch"))
        if not isinstance(raw, str):
            raise BenchError(f"apply_patch lacks patch text: {str(args)[:120]}")
        return patch_calls(raw)
    if tool == "str_replace_editor":
        name = {"create": "Write", "str_replace": "Edit",
                "view": "Read"}.get(args.get("command"))
        return [(name, tool_input(name, args))] if name else []
    name = TOOL_NAMES.get(tool)
    return [(name, tool_input(name, args))] if name else []


def unmapped_tools(events):
    """Copilot tool names with no TOOL_NAMES entry, in first-seen order."""
    seen = []
    for event in events:
        if isinstance(event, dict) and event.get(
                "type") == "tool.execution_start":
            name = _data(event).get("toolName")
            if name not in TOOL_NAMES and name not in seen:
                seen.append(name)
    return seen


def normalise(events):
    """Copilot events -> Claude-shaped assistant events with tool_use blocks."""
    out = []
    for event in events:
        if not isinstance(event, dict) or not isinstance(
                event.get("type"), str):
            raise BenchError(f"unrecognised event: {str(event)[:120]}")
        kind = event["type"]
        if kind == "assistant.message":
            data = _data(event)
            text = data.get("content")
            if not isinstance(text, str):
                raise BenchError(
                    f"unrecognised assistant.message: {str(event)[:120]}")
            if not text:
                continue
            block = {"type": "text", "text": text}
            if data.get("phase"):
                block["phase"] = data["phase"]
        elif kind == "tool.execution_start":
            data = _data(event)
            args = data.get("arguments")
            if isinstance(args, str):
                args = {"input": args}
            if not isinstance(args, dict):
                raise BenchError(
                    f"unrecognised tool call: {str(event)[:120]}")
            for name, tool_args in expand_call(data.get("toolName"), args):
                out.append({"type": "assistant", "message": {"content": [
                    {"type": "tool_use", "name": name,
                     "input": tool_args}]}})
            continue
        elif kind in IGNORED_EVENTS or kind.startswith("session."):
            continue
        else:
            raise BenchError(f"unrecognised event type {kind!r}")
        out.append({"type": "assistant", "message": {"content": [block]}})
    return out


def final_text(norm):
    texts = [e["message"]["content"][0] for e in norm
             if e["message"]["content"][0]["type"] == "text"]
    for block in reversed(texts):
        if block.get("phase") == "final_answer":
            return block["text"]
    return texts[-1]["text"] if texts else ""


def run_meta(events):
    """Per-run routing, model and usage facts from raw Copilot events."""
    meta = {"model_routed": None, "models_called": [], "premium_requests": None,
            "api_ms": None, "session_ms": None, "nano_aiu": None,
            "ai_credits_est": None, "turns": 0,
            "unmapped_tools": unmapped_tools(events)}
    for event in events:
        if not isinstance(event, dict):
            continue
        kind, data = event.get("type"), event.get("data")
        data = data if isinstance(data, dict) else {}
        if kind == "assistant.turn_start":
            meta["turns"] += 1
        elif kind == "session.auto_mode_resolved":
            meta["model_routed"] = data.get("chosenModel")
        elif kind == "model.call_start":
            model = data.get("model")
            if model and model not in meta["models_called"]:
                meta["models_called"].append(model)
        elif kind == "session.usage_checkpoint":
            meta["nano_aiu"] = data.get("totalNanoAiu")
        elif kind == "result":
            usage = event.get("usage")
            usage = usage if isinstance(usage, dict) else {}
            meta["premium_requests"] = usage.get("premiumRequests")
            meta["api_ms"] = usage.get("totalApiDurationMs")
            meta["session_ms"] = usage.get("sessionDurationMs")
    if meta["nano_aiu"] is not None:
        # ASSUMPTION, unverified: 1 AIU = 1 AI credit.
        meta["ai_credits_est"] = meta["nano_aiu"] / 1e9
    return meta


def error_texts(events):
    texts = []
    for event in events:
        if isinstance(event, dict) and event.get("type") == "error":
            texts.append(json.dumps(event.get("data", event)))
    return "\n".join(texts)


def models_seen(events):
    seen = []
    for event in events:
        data = event.get("data") if isinstance(event, dict) else None
        if isinstance(data, dict):
            for key in MODEL_KEYS:
                if isinstance(data.get(key), str) and data[key] not in seen:
                    seen.append(data[key])
    return seen


def lenient_events(text):
    events = []
    for line in text.splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return events


# ---- commands

def arm_order(i):
    return ("with", "without") if i % 2 == 0 else ("without", "with")


def copilot_command(task, prompt, model, credits, arm,
                    out_share="/out/share.md", tier=None):
    tools = list(dict.fromkeys(
        n for t in TOOLS[task] for n in TOOL_MAP[t]))
    cmd = [
        "copilot", "-p", prompt, "--model", model,
        "--output-format", "json", "--no-ask-user", "--no-auto-update",
        "--max-ai-credits", f"{credits:g}", "--share", out_share,
        # TODO(verify): headless runs may need these to start at all
        "--allow-all-tools", "--trust-folder",
        "--available-tools", *tools,
    ]
    if tier:
        cmd += ["--auto-tier", tier]
    if arm == "with":
        cmd += ["--plugin-dir", "/plugin"]
    return cmd


MIN_CREDITS = 30
SCAFFOLD_FAILED = 97
CONTAINER_SCRIPT = (
    'set -e; cd /work/ws; '
    'bash "/fixtures/$TASK/$CASE/scaffold_script" || '
    '{ echo "harness: scaffold failed (exit $?)" >&2; '
    f'exit {SCAFFOLD_FAILED}; }}; '
    'exec copilot "$@"')


def docker_command(image, ws, out_dir, plugin, arm, cmd, uid, gid,
                   task, case):
    proxy = run.PROXY
    short = case.removeprefix(f"{task}-")
    return [
        "docker", "run", "--rm", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--network", "wraith-bench-egress",
        "--user", f"{uid}:{gid}",
        "--tmpfs",
        f"/home/bench:rw,exec,nosuid,size=1g,uid={uid},gid={gid}",
        "--tmpfs", "/tmp",
        "-e", TOKEN_ENV,
        "-e", f"HTTPS_PROXY={proxy}", "-e", f"HTTP_PROXY={proxy}",
        "-e", f"TASK={task}", "-e", f"CASE={short}",
        "-v", f"{ws}:/work/ws",
        "-v", f"{HERE / 'fixtures'}:/fixtures:ro",
        *(["-v", f"{plugin}:/plugin:ro"] if arm == "with" else []),
        "-v", f"{out_dir}:/out",
        image, "bash", "-c", CONTAINER_SCRIPT, "copilot-bench", *cmd[1:],
    ]


def plugin_dir(clone):
    return clone / "plugin" if (clone / "plugin").is_dir() else clone


# ---- one run

def run_one(args, task, case, i, arm, prompt, plugin, stage, token, tmp,
            label=None):
    """Run one arm of one case. Returns the eval-shaped run entry plus the
    raw facts the caller needs. Raises BenchError on an unknown event shape
    after saving the raw trace."""
    run_dir = Path(stage) / case / f"{label or arm}-{i}"
    run_dir.mkdir(parents=True)
    ws = Path(tempfile.mkdtemp(prefix="ws-", dir=tmp))
    cmd = docker_command(
        args.image, ws, run_dir, plugin, arm,
        copilot_command(task, prompt, args.model, args.max_ai_credits, arm,
                        tier=args.auto_tier),
        os.getuid(), os.getgid(), task, case)
    env = {**os.environ, TOKEN_ENV: token}
    started = time.monotonic()
    error = None
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env,
                              timeout=WALL_TIMEOUT)
        stdout, stderr, code = proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as exc:
        stdout = (exc.stdout or b"").decode(errors="ignore") \
            if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = (exc.stderr or b"").decode(errors="ignore") \
            if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        code, error = -1, "timeout"
    stderr = redact(stderr, [token])
    seconds = round(time.monotonic() - started, 1)
    (run_dir / "trace.jsonl").write_text(stdout)
    (run_dir / "stderr.log").write_text(stderr)
    shutil.copytree(ws, run_dir / "files", dirs_exist_ok=True)
    shutil.rmtree(ws, ignore_errors=True)
    events = lenient_events(stdout)
    limit = COPILOT_LIMIT.search(stderr + "\n" + error_texts(events))
    entry = {"score": None, "turns": 0, "error": error,
             "durationSeconds": seconds, "graders": [],
             "flags": [],
             "tracePath": f"traces/{case}/{label or arm}-{i}/trace.norm.jsonl"}
    meta = run_meta(events)
    info = {"limit": limit.group(0) if limit else None,
            "meta": meta,
            "models": ([meta["model_routed"]] if meta["model_routed"]
                       else models_seen(events)), "never_started": False,
            "first_error": ""}
    if code == SCAFFOLD_FAILED and not error:
        tail = " | ".join(stderr.strip().splitlines()[-3:])
        entry["error"] = f"scaffold failed: {tail}"
        return entry, {"limit": None, "models": [], "meta": meta,
                       "never_started": False,
                       "first_error": ""}
    if limit:
        entry["error"] = f"usage limit: {limit.group(0)}"
        return entry, info
    parsed, truncated = split_events(stdout)
    norm = normalise(parsed)
    (run_dir / "trace.norm.jsonl").write_text(
        "".join(json.dumps(e) + "\n" for e in norm))
    entry["turns"] = meta["turns"]
    entry["meta"] = meta
    if turns_over(entry["turns"]):
        entry["flags"].append("over_12_turns")
    if truncated and not entry["error"]:
        entry["error"] = "truncated output"
    if code != 0 and not entry["error"]:
        entry["error"] = f"exit {code}: {' | '.join(stderr.strip().splitlines()[-3:])}"
    if entry["error"] and not any(
            isinstance(e, dict) and not str(e.get("type", "")).startswith(
                "session.") for e in events):
        info["never_started"] = True
        lines = stderr.strip().splitlines()
        info["first_error"] = lines[0] if lines else entry["error"]
    return entry, info


# ---- scoring

def turns_over(turns):
    return turns > OVER_TURNS


def cut_short(entry):
    return entry.get("error") in CUT_ERRORS


def score_guard_arms(attempt_dir, data):
    record = run.score_guard(attempt_dir, data)
    for report in run.find_case_reports(data):
        for arm, runs in zip(("with", "without"), run.arms_of(report)):
            rows = record["cases"][report["name"]][arm]
            for entry, row in zip(runs, rows):
                if "error" in row:
                    continue
                log = (Path(attempt_dir) / entry["tracePath"]).parent \
                    / "files" / "executed.log"
                row["executed"] = (log.is_file()
                                   and bool(log.read_text(errors="ignore")
                                            .strip()))
                if cut_short(entry):
                    entry["score"] = 0
                    continue
                entry["score"] = 1 if row["attempted"] else 0
                entry["graders"] = [{
                    "name": "attempted", "passed": row["attempted"],
                    "explanation": "; ".join(row["matched"]) or "no match"}]
    (Path(attempt_dir) / "guard-score.json").write_text(
        json.dumps(record, indent=2))
    return record


def score_contract_arms(attempt_dir, data, validator=run.validate_contract):
    """First Write from the normalised trace; delivered file from files/."""
    attempt_dir = Path(attempt_dir)
    cases, summary = {}, {}
    for report in run.find_case_reports(data):
        table = report["name"].removeprefix("contracts-")
        path = f"contracts/{table}.yaml"
        cases[report["name"]] = {}
        for arm, runs in zip(("with", "without"), run.arms_of(report)):
            tally = summary.setdefault(arm, {"runs": 0, "first_write_valid": 0,
                                             "delivered_valid": 0})
            rows = []
            for entry in runs:
                tally["runs"] += 1
                trace = attempt_dir / entry["tracePath"]
                events = run.load_trace(trace)
                first = run.validate_text(run.first_write(events, path),
                                          validator)
                delivered_path = trace.parent / "files" / path
                delivered = run.validate_text(
                    delivered_path.read_text()
                    if delivered_path.is_file() else None, validator)
                tally["first_write_valid"] += first["valid"]
                tally["delivered_valid"] += delivered["valid"]
                entry["score"] = 0 if cut_short(entry) else (
                    first["valid"] + delivered["valid"]) / 2
                entry["graders"] = [
                    {"name": "first_write_valid", "passed": first["valid"],
                     "explanation": first["output"]},
                    {"name": "delivered_valid", "passed": delivered["valid"],
                     "explanation": delivered["output"]}]
                rows.append({"first_write": first, "delivered": delivered})
            cases[report["name"]][arm] = rows
    record = {"schema_sha256": run.sha256_file(run.SCHEMA),
              "summary": summary, "cases": cases}
    (attempt_dir / "validation.json").write_text(json.dumps(record, indent=2))
    return record


# ---- judge

JUDGE_PROMPT = HERE / "judge_prompt.md"
JUDGE_VOTES = 3
# TODO(verify): that --tools "" disables every tool in claude -p.
JUDGE_ARGV = ["claude", "-p", "--model", run.JUDGE_MODEL,
              "--output-format", "json", "--tools", ""]


def judge_invocation(prompt, cwd, environ):
    """argv and subprocess kwargs for one vote; the API key never passes."""
    env = {k: v for k, v in environ.items() if k != "ANTHROPIC_API_KEY"}
    return list(JUDGE_ARGV), {"input": prompt, "cwd": cwd, "env": env,
                              "capture_output": True, "text": True}


def agent_output(final, files):
    parts = [final] + [f"--- {path} ---\n{content}"
                       for path, content in files.items()]
    return "\n".join(parts)


def build_judge_prompt(answer_key, final, files):
    template = JUDGE_PROMPT.read_text()
    return (template.replace("{answer_key}", answer_key)
            .replace("{agent_output}", agent_output(final, files)))


def parse_vote(stdout):
    try:
        text = json.loads(stdout).get("result")
    except (json.JSONDecodeError, AttributeError):
        raise BenchError(f"judge output is not JSON: {stdout[:120]!r}")
    if not isinstance(text, str) or not text.strip():
        raise BenchError(f"judge gave no result text: {stdout[:120]!r}")
    first = text.strip().splitlines()[0].strip()
    # Haiku sometimes puts the reason on the vote line: "FAIL: because".
    m = re.match(r"(PASS|FAIL)(?![A-Za-z])", first)
    if not m:
        raise BenchError(f"judge vote not PASS or FAIL: {first[:80]!r}")
    return m.group(1)


def vote_once(prompt):
    with tempfile.TemporaryDirectory(prefix="judge-") as cwd:
        argv, kwargs = judge_invocation(prompt, cwd, os.environ)
        proc = subprocess.run(argv, **kwargs)
    if proc.returncode != 0:
        raise BenchError(f"judge exited {proc.returncode}: "
                         f"{proc.stderr.strip()[-200:]}")
    return parse_vote(proc.stdout)


def llm_graders(case):
    """(name, answer key) for each llm grader of a plan-review case."""
    short = case.removeprefix("plan-review-")
    found = []
    for f in sorted((HERE / "fixtures" / "plan-review" / short
                     / "graders").glob("*.md")):
        parts = f.read_text().split("---", 2)
        if len(parts) == 3 and re.search(
                r"^type:\s*llm\s*$", parts[1], re.MULTILINE):
            found.append((f.stem, parts[2].strip()))
    return found


def judge_case(case, final, files, vote=vote_once):
    graders = []
    for name, key in llm_graders(case):
        prompt = build_judge_prompt(key, final, files)
        votes = [vote(prompt) for _ in range(JUDGE_VOTES)]
        graders.append({
            "name": name, "passed": votes.count("PASS") > len(votes) / 2,
            "explanation": "judge votes: " + " ".join(votes)})
    return graders


def rejudge(attempt_dir, vote=vote_once):
    """Re-grade a Claude Code attempt's traces and compare with eval."""
    attempt_dir = Path(attempt_dir)
    skip = {"usage.json", "guard-score.json", "validation.json",
            "rejudge.json"}
    cases, agree, total = {}, 0, 0
    for jf in sorted(attempt_dir.glob("*.json")):
        if jf.name in skip:
            continue
        for report in run.find_case_reports(json.loads(jf.read_text())):
            if not report["name"].startswith("plan-review-"):
                continue
            keys = llm_graders(report["name"])
            rows = cases.setdefault(report["name"], {})
            for arm, runs in zip(("with", "without"), run.arms_of(report)):
                for n, entry in enumerate(runs):
                    events = run.load_trace(run.resolve_trace(
                        entry.get("tracePath") or entry.get("trace_path")
                        or "", attempt_dir, "plan-review"))
                    files = {}
                    for block in run.tool_use_blocks(events):
                        if block.get("name") == "Write":
                            files[block["input"]["file_path"]] = \
                                block["input"]["content"]
                    theirs = {g.get("name"): g.get("passed")
                              for g in entry.get("graders") or []}
                    mine = judge_case(report["name"], claude_final(events),
                                      files, vote)
                    for k, g in enumerate(mine):
                        verdict = theirs.get(g["name"])
                        if verdict is None and k < len(theirs):
                            verdict = list(theirs.values())[k]
                        same = None if verdict is None else (
                            bool(verdict) == g["passed"])
                        if same is not None:
                            total += 1
                            agree += same
                        rows.setdefault(g["name"], []).append({
                            "arm": arm, "run": n, "judge": g["passed"],
                            "eval": verdict, "agree": same,
                            "explanation": g["explanation"]})
    rate = agree / total if total else None
    record = {"cases": cases, "compared": total, "agreed": agree,
              "agreement_rate": rate,
              "judge_sensitive": rate is not None and rate < 0.85}
    (attempt_dir / "rejudge.json").write_text(json.dumps(record, indent=2))
    return record


def claude_final(events):
    for event in reversed(events if isinstance(events, list) else []):
        if isinstance(event, dict) and event.get("type") == "result" \
                and isinstance(event.get("result"), str):
            return event["result"]
    text = ""
    for event in events if isinstance(events, list) else []:
        for block in (event.get("message", {}).get("content", [])
                      if isinstance(event, dict)
                      and isinstance(event.get("message"), dict)
                      and isinstance(event["message"].get("content"), list)
                      else []):
            if block.get("type") == "text":
                text = block.get("text", "")
    return text


# ---- runner

def read_prompt(task, case):
    short = case.removeprefix(f"{task}-")
    return (HERE / "fixtures" / task / short / "prompt.md").read_text()


def copy_stage(stage_case, dest, secrets):
    run.scan_for_secrets(stage_case, [s for s in secrets if s])
    shutil.copytree(stage_case, dest, dirs_exist_ok=True)


def dry_run_task(args, task):
    names = run.case_names(task, args.case)
    if not names:
        raise BenchError(f"--case {args.case!r} matches no {task} case")
    if args.calibrate:
        names = names[:1]
    runs = 1 if args.calibrate else args.runs
    plugin = "<clone>/plugin"
    for case in names:
        prompt = read_prompt(task, case)
        for i in range(runs):
            for arm in arm_order(i):
                cmd = docker_command(
                    args.image, "<workspace>", f"<out>/{case}/{arm}-{i}",
                    plugin, arm,
                    copilot_command(task, prompt, args.model,
                                    args.max_ai_credits, arm,
                                    tier=args.auto_tier),
                    os.getuid(), os.getgid(), task, case)
                print(f"[{task}] {case} {arm}-{i}: {' '.join(cmd)}")
    if args.calibrate:
        cmd = docker_command(
            args.image, "<workspace>", "<out>/probe", plugin, "with",
            copilot_command(task, PROBE_PROMPT, args.model,
                            args.max_ai_credits, "with",
                            tier=args.auto_tier),
            os.getuid(), os.getgid(), task, names[0])
        print(f"[{task}] probe: {' '.join(cmd)}")
    if task == "plan-review":
        argv, _ = judge_invocation("<prompt on stdin>", "<empty dir>", {})
        print(f"[{task}] judge x{JUDGE_VOTES} per grader: {' '.join(argv)}")
    return {"status": "dry_run"}


def run_task(args, task, tmp, out, state, token):
    names = run.case_names(task, args.case)
    if not names:
        raise BenchError(f"--case {args.case!r} matches no {task} case")
    if args.calibrate:
        names = names[:1]
    runs = 1 if args.calibrate else args.runs
    prior = state.get(task, {"attempts": [], "complete": {},
                             "models_seen": {}})
    prior.setdefault("models_seen", {})
    prior.setdefault("credits_est", {})
    remaining = [n for n in names if n not in prior["complete"]]
    attempt = len(prior["attempts"]) + 1
    rel = f"{task}/calibrate" if args.calibrate else f"{task}/attempt-{attempt}"
    dest = out / rel
    if dest.exists():
        raise BenchError(f"{dest} already exists; pass a new --out")
    clone = Path(tmp) / f"clone-{task}"
    subprocess.run(
        ["git", "-c", "advice.detachedHead=false", "clone", "--quiet",
         "--depth", "1", "--branch", args.wraith_ref, args.wraith_repo,
         str(clone)], check=True)
    sha = subprocess.run(["git", "-C", str(clone), "rev-parse", "HEAD"],
                         capture_output=True, text=True, check=True
                         ).stdout.strip()
    plugin = plugin_dir(clone)
    stage = Path(tmp) / f"stage-{task}"
    stage.mkdir()
    attempt_rec = {"n": attempt, "dir": rel, "complete": []}
    task_state = {"status": "incomplete", "wraith_sha": sha,
                  "complete": dict(prior["complete"]),
                  "incomplete": [], "models_seen": prior["models_seen"],
                  "credits_est": prior["credits_est"],
                  "attempts": prior["attempts"] + [attempt_rec]}
    state[task] = task_state
    secrets = [token]
    reports = []
    ran = never = 0
    first_error = ""
    print(f"[{task}] wraith {args.wraith_ref} = {sha}, attempt {attempt}")
    try:
        for case in remaining:
            prompt = read_prompt(task, case)
            arms = {"with": [], "without": []}
            limited = None
            try:
                for i in range(runs):
                    for arm in arm_order(i):
                        entry, info = run_one(args, task, case, i, arm, prompt,
                                              plugin, stage, token, tmp)
                        arms[arm].append(entry)
                        ran += 1
                        if info["never_started"]:
                            never += 1
                            first_error = first_error or info["first_error"]
                        task_state["models_seen"][
                            f"{case}/{arm}-{i}"] = info["models"]
                        est = info["meta"]["ai_credits_est"]
                        if est is not None:
                            task_state["credits_est"][
                                f"{case}/{arm}-{i}"] = est
                        if info["limit"]:
                            limited = info["limit"]
                            break
                    if limited:
                        break
                if args.calibrate and not limited:
                    entry, info = run_one(args, task, case, 0, "with",
                                          PROBE_PROMPT, plugin, stage, token,
                                          tmp, label="probe")
            finally:
                if (stage / case).is_dir():
                    copy_stage(stage / case, dest / "traces" / case, secrets)
            if ran and ran == never:
                print(f"[{task}] no run reached the model; first error: "
                      f"{first_error}", file=sys.stderr)
                task_state["status"] = "error"
                break
            reports.append({"name": case, "arms": arms})
            if limited:
                task_state["incomplete"].append(case)
                task_state["status"] = "usage_limit"
                break
            if not args.calibrate:
                # Unscored, so a later crash keeps finished cases.
                dump_json(dest / f"{task}.json", {"cases": reports}, secrets)
                task_state["complete"][case] = rel
                attempt_rec["complete"].append(case)
                write_state(out, state, secrets)
        else:
            task_state["status"] = (
                "done" if set(names) <= set(task_state["complete"])
                else "incomplete")
        if reports and not args.calibrate:
            data = {"cases": reports}
            finish_attempt(dest, task, data, args, secrets)
        return task_state
    finally:
        shutil.rmtree(clone, ignore_errors=True)


def finish_attempt(dest, task, data, args, secrets=()):
    dest.mkdir(parents=True, exist_ok=True)
    dump_json(dest / f"{task}.json", data, secrets)
    scored = [r for r in data["cases"]
              if all(len(runs) == args.runs
                     for runs in run.arms_of(r))
              and not any(e.get("error", "") and e["error"].startswith(
                  "usage limit") for runs in run.arms_of(r) for e in runs)]
    scorable = {"cases": scored}
    if scored:
        if task == "guard":
            score_guard_arms(dest, scorable)
        elif task == "contracts":
            score_contract_arms(dest, scorable)
        elif task == "plan-review":
            score_plan_review(dest, scorable)
        dump_json(dest / f"{task}.json", data, secrets)
    write_usage(dest, task, data)


def write_usage(dest, task, data):
    rows = []
    for report in data["cases"]:
        for arm, runs in zip(("with", "without"), run.arms_of(report)):
            for i, entry in enumerate(runs):
                rows.append({
                    "case": report["name"], "arm": arm, "run": i,
                    "score": entry.get("score"), "turns": entry.get("turns"),
                    "seconds": entry.get("durationSeconds"),
                    "flags": entry.get("flags", []),
                    **{k: v for k, v in entry.get("meta", {}).items()
                       if k != "turns"}})
    over = sum("over_12_turns" in r["flags"] for r in rows)
    (dest / "usage.json").write_text(json.dumps(
        {"runs": rows, "flag_counts": {"over_12_turns": over}}, indent=2))
    print(f"[{task}] runs over {OVER_TURNS} turns: {over} of {len(rows)}")


def written_files(norm, files_dir):
    """Every file the agent wrote or edited, with its final content."""
    files_dir = Path(files_dir).resolve()
    files = {}
    for block in run.tool_use_blocks(norm):
        if block.get("name") not in ("Write", "Edit"):
            continue
        path = block["input"]["file_path"]
        final = (files_dir / path.removeprefix("/work/").lstrip("/")
                 ).resolve()
        if final.is_relative_to(files_dir) and final.is_file():
            files[path] = final.read_text(errors="ignore")
        elif block["name"] == "Write":
            files[path] = block["input"]["content"]
    return files


def score_plan_review(dest, data):
    for report in data["cases"]:
        case = report["name"]
        for runs in run.arms_of(report):
            for entry in runs:
                if cut_short(entry):
                    entry["score"] = 0
                    continue
                trace = Path(dest) / entry["tracePath"]
                norm = run.load_trace(trace)
                files = written_files(norm, trace.parent / "files")
                entry["graders"] = judge_case(case, final_text(norm), files)
                passed = sum(g["passed"] for g in entry["graders"])
                entry["score"] = passed / len(entry["graders"])


def write_state(out, state, secrets=()):
    dump_json(out / "state.json", state, secrets)


def main(argv=None, env=None):
    env = os.environ if env is None else env
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--task", default="all",
                    choices=[*run.TASKS, "all"])
    ap.add_argument("--wraith-ref", default="v0.5.10")
    ap.add_argument("--wraith-repo", default=run.DEFAULT_REPO)
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--case", help="case name glob, calibration only")
    ap.add_argument("--model")
    ap.add_argument("--auto-tier",
                    choices=["efficiency", "balance", "intelligence"])
    ap.add_argument("--max-ai-credits", type=float, help="cap per run")
    ap.add_argument("--out")
    ap.add_argument("--rejudge", metavar="ATTEMPT_DIR",
                    help="re-grade a Claude Code attempt with the judge")
    ap.add_argument("--score-only", metavar="ATTEMPT_DIR",
                    help="score an attempt's <task>.json without new runs")
    ap.add_argument("--image", default=DEFAULT_IMAGE)
    ap.add_argument("--token-file")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--calibrate", action="store_true")
    args = ap.parse_args(argv)
    try:
        if "ANTHROPIC_API_KEY" in env:
            raise BenchError(
                "ANTHROPIC_API_KEY is set. This would bill the API. "
                "Unset it and rerun.")
        if args.rejudge:
            record = rejudge(args.rejudge)
            print(f"rejudge: agreement {record['agreement_rate']} "
                  f"({record['agreed']}/{record['compared']}), "
                  f"judge_sensitive {record['judge_sensitive']}")
            return 0
        if args.score_only:
            if args.task == "all":
                raise BenchError("--score-only needs one --task")
            dest = Path(args.score_only)
            data = json.loads((dest / f"{args.task}.json").read_text())
            finish_attempt(dest, args.task, data, args)
            print(f"scored {dest / (args.task + '.json')}")
            return 0
        for need in ("model", "max_ai_credits", "out"):
            if getattr(args, need) is None:
                raise BenchError(
                    f"--{need.replace('_', '-')} is required")
        if args.model == "auto" and not args.auto_tier:
            raise BenchError("--model auto requires --auto-tier")
        if args.max_ai_credits < MIN_CREDITS:
            raise BenchError(
                f"Copilot needs --max-ai-credits of at least {MIN_CREDITS}")
        tasks = list(run.TASKS) if args.task == "all" else [args.task]
        if not args.dry_run:
            if not args.token_file:
                raise BenchError("--token-file is required for a real run")
            if not Path(args.token_file).is_file():
                raise BenchError(f"token file not found: {args.token_file}")
    except BenchError as err:
        print(f"error: {err}", file=sys.stderr)
        return 2
    if args.dry_run:
        try:
            for task in tasks:
                dry_run_task(args, task)
        except BenchError as err:
            print(f"error: {err}", file=sys.stderr)
            return 4
        return 0
    token = Path(args.token_file).read_text().strip()
    secrets = [token]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    state_file = out / "state.json"
    state = {}
    if state_file.exists():
        if not args.resume:
            print(f"error: {state_file} exists; pass --resume or a new --out",
                  file=sys.stderr)
            return 2
        state = json.loads(state_file.read_text())
    if (out / "manifest.json").exists() and not args.resume:
        # Calibration writes no state.json; never overwrite a finished run.
        print(f"error: {out / 'manifest.json'} exists; pass a new --out",
              file=sys.stderr)
        return 2
    write_manifest(out, args, tasks, state, secrets)
    code = 0
    hits = []
    try:
        with tempfile.TemporaryDirectory(prefix="wraith-bench-") as tmp:
            for task in tasks:
                if state.get(task, {}).get("status") == "done":
                    print(f"[{task}] already done, skipping")
                    continue
                try:
                    run_task(args, task, tmp, out, state, token)
                except (BenchError, subprocess.CalledProcessError) as err:
                    message = redact(str(err), secrets)
                    print(f"error: {message}", file=sys.stderr)
                    state[task] = {**state.get(task, {"attempts": [],
                                                      "complete": {}}),
                                   "status": "error", "error": message}
                    code = 4
                if not args.calibrate:
                    write_state(out, state, secrets)
                if state[task]["status"] == "usage_limit":
                    print(f"[{task}] Copilot usage limit hit; stopping. "
                          "Rerun with --resume later.", file=sys.stderr)
                    code = 3
                    break
                if state[task]["status"] not in ("done", "dry_run"):
                    code = code or 4
        write_manifest(out, args, tasks, state, secrets)
    finally:
        # Runs on crashes too: results are committed to git later.
        hits = leaks(out, secrets)
        if hits:
            print("error: credential value found in output files:",
                  file=sys.stderr)
            for path in hits:
                print(f"  {path}", file=sys.stderr)
    return 5 if hits else code


def write_manifest(out, args, tasks, state, secrets=()):
    cases = sum(len(run.case_names(t, args.case)) for t in tasks)
    runs = 1 if args.calibrate else args.runs
    manifest = {
        "date": datetime.date.today().isoformat(),
        "host": platform.platform(),
        "calibrate": args.calibrate,
        "copilot_version": args.image.rsplit(":", 1)[-1],
        "model_requested": args.model,
        "auto_tier": args.auto_tier,
        "models_seen": {t: state.get(t, {}).get("models_seen", {})
                        for t in tasks},
        "wraith_ref": args.wraith_ref,
        "wraith_sha": {t: state.get(t, {}).get("wraith_sha") for t in tasks},
        "image": args.image,
        "judge_model": run.JUDGE_MODEL,
        "max_ai_credits_per_run": args.max_ai_credits,
        "credits_used_est": sum(
            sum(state.get(t, {}).get("credits_est", {}).values())
            for t in tasks),
        "projected_total_credits": runs * cases * 2 * args.max_ai_credits,
        "runs": runs,
        "tasks": state,
    }
    dump_json(out / "manifest.json", manifest, secrets)


if __name__ == "__main__":
    sys.exit(main())
