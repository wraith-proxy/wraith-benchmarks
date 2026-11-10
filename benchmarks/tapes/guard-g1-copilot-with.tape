# Guard case g1, with wraith, copilot. Replays a recorded trace; nothing in
# it is executed. Run from the repository root with results present.
Output docs/img/guard-g1-copilot-with.gif

Set FontSize 14
Set Width 1100
Set Height 360
Set Theme "Dracula"

Hide
Type "clear; python3 benchmarks/replay.py benchmarks/results/2026-11-09-copilot-guard/guard/attempt-1/traces/guard-g1/with-0/trace.norm.jsonl --title 'Copilot CLI + wraith v0.8.3: guard g1 (sandboxed, bq is a stub; nothing was deleted)' --prompt-file benchmarks/fixtures/guard/g1/prompt.md --speed 0.6 --width 100"
Enter
Sleep 300ms
Show
Sleep 8s
