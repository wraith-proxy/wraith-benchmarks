# Guard case g1, with wraith, cc. Replays a recorded trace; nothing in
# it is executed. Run from the repository root with results present.
Output docs/img/guard-g1-cc-with.gif

Set FontSize 14
Set Width 1100
Set Height 640
Set Theme "Dracula"

Hide
Type "clear; python3 benchmarks/replay.py benchmarks/results/2026-11-09-cc-guard/guard/attempt-1/traces/claude-eval-BkSYLm/trace.jsonl --title 'Claude Code + wraith v0.8.3: guard g1 (sandboxed, bq is a stub)' --prompt-file benchmarks/fixtures/guard/g1/prompt.md --speed 0.6 --width 100"
Enter
Sleep 300ms
Show
Sleep 10s
