# Tapes

Terminal recordings of benchmark runs, rendered with
[vhs](https://github.com/charmbracelet/vhs). Each tape types a
`benchmarks/replay.py` command, which prints a recorded
`trace.norm.jsonl`; nothing in a trace is executed.

Render one tape from the repository root:

```
docker run --rm -v "$PWD":/vhs ghcr.io/charmbracelet/vhs:v0.10.0 benchmarks/tapes/<name>.tape
```

`example.tape` is a template. Copy it to `<name>.tape` and fill the
placeholders (`<date>`, `<host>`, `<arm>`, trace path, title, prompt
file) once results exist. The gif lands at
`results/<date>/img/<host>-<arm>.gif`.
