"""Print a recorded run (trace.norm.jsonl) as a terminal session.

Usage: replay.py TRACE --title TEXT --prompt-file FILE [--speed SECONDS]
                 [--width 100]

Only prints text from the trace; nothing in it is ever executed.
"""
import argparse
import json
import textwrap
import time


def steps(trace):
    """Yield (kind, text) in order; the last text block is the final one."""
    events = [json.loads(line) for line in open(trace) if line.strip()]
    blocks = [b for e in events if e.get("type") == "assistant"
              for b in e["message"]["content"]]
    last_text = max((i for i, b in enumerate(blocks)
                     if b.get("type") == "text"), default=None)
    for i, b in enumerate(blocks):
        if b.get("type") == "tool_use":
            inp = b.get("input", {})
            name = b["name"]
            if name == "Bash":
                yield "step", f"$ {inp.get('command', '')}"
            elif name in ("Write", "Edit"):
                yield "step", f"> {name} {inp.get('file_path', '')}"
            elif name == "Skill":
                yield "step", f"> Skill {inp.get('skill', '')}"
        elif i == last_text:
            yield "final", b["text"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("trace")
    ap.add_argument("--title", required=True)
    ap.add_argument("--prompt-file", required=True)
    ap.add_argument("--speed", type=float, default=0.4)
    ap.add_argument("--width", type=int, default=100)
    args = ap.parse_args()

    def show(text):
        for para in text.splitlines() or [""]:
            print(textwrap.fill(para, args.width) if para else "")
        time.sleep(args.speed)

    show(args.title)
    show("")
    show(open(args.prompt_file).read().rstrip())
    show("")
    for kind, text in steps(args.trace):
        show(text)
        if kind == "final":
            break


if __name__ == "__main__":
    main()
