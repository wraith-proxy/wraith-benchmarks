import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

REPLAY = pathlib.Path(__file__).parent / "replay.py"


def event(block):
    return {"type": "assistant", "message": {"content": [block]}}


class ReplayTest(unittest.TestCase):
    def test_prints_steps_in_order_without_executing(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            marker = tmp / "ran"
            events = [
                event({"type": "tool_use", "name": "Skill",
                       "input": {"skill": "wraith:careful"}}),
                event({"type": "tool_use", "name": "Bash",
                       "input": {"command": f"touch {marker}"}}),
                event({"type": "tool_use", "name": "Write",
                       "input": {"file_path": "a.yaml", "content": "x"}}),
                event({"type": "tool_use", "name": "Edit",
                       "input": {"file_path": "b.yaml"}}),
                event({"type": "text", "text": "All done."}),
            ]
            trace = tmp / "trace.norm.jsonl"
            trace.write_text("".join(json.dumps(e) + "\n" for e in events))
            prompt = tmp / "prompt.md"
            prompt.write_text("Do the thing.\n")
            out = subprocess.run(
                [sys.executable, str(REPLAY), str(trace), "--title",
                 "t1 c1 host with", "--prompt-file", str(prompt),
                 "--speed", "0"],
                check=True, capture_output=True, text=True).stdout
            self.assertFalse(marker.exists())
            self.assertTrue(out.startswith("t1 c1 host with"))
            want = ["Do the thing.", "> Skill wraith:careful",
                    f"$ touch {marker}", "> Write a.yaml", "> Edit b.yaml",
                    "All done."]
            pos = [out.index(w) for w in want]
            self.assertEqual(pos, sorted(pos))


if __name__ == "__main__":
    unittest.main()
