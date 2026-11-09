# Template. Replace <date>, <host>, <arm>, <trace path>, <title> and
# <prompt file> when results exist.
Output results/<date>/img/<host>-<arm>.gif

Set FontSize 14
Set Width 1100
Set Height 600
Set Theme "Dracula"

Type "uv run --no-project --python 3.12 python benchmarks/replay.py <trace path> --title '<title>' --prompt-file <prompt file>"
Enter
Sleep 30s
