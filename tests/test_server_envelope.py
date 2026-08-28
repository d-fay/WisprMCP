#!/usr/bin/env python3
"""Tests for the WisprMCP MCP server envelope. Stdlib only, no deps.

Run: python3 -m unittest discover -s tests -v   (from the repo root)
"""
import json
import os
import subprocess
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from wispr_mcp.mcp.server import (  # noqa: E402
    LEAD_BLOCK_MAX,
    LEAD_BLOCK_THRESHOLD,
    _digest_line,
    _model_content_blocks,
)

#: A prefix-scanning host appends control metadata to the first text block and
#: scans only this many characters of the joined content (Kiro Crew's ACP cut).
HOST_PREFIX_SCAN = 4000


def rpc(*messages, cwd=REPO):
    """Drive the real stdio server and return its responses by id."""
    payload = "\n".join(json.dumps(m) for m in messages) + "\n"
    proc = subprocess.run(
        [sys.executable, "mcp_server.py"],
        input=payload, capture_output=True, text=True, cwd=cwd,
    )
    out = {}
    for line in proc.stdout.splitlines():
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "id" in msg:
            out[msg["id"]] = msg
    return out, proc.stderr


class ContentBlockShape(unittest.TestCase):
    def test_small_result_stays_one_block(self):
        blocks = _model_content_blocks("t", {"a": 1, "b": "short"})
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]["type"], "text")
        self.assertEqual(json.loads(blocks[0]["text"]), {"a": 1, "b": "short"})

    def test_large_result_leads_with_a_digest_block(self):
        result = {"entry_count": 105, "transcript": "x" * (LEAD_BLOCK_THRESHOLD + 1)}
        blocks = _model_content_blocks("get_meeting_transcript", result)
        self.assertEqual(len(blocks), 2)
        self.assertLess(len(blocks[0]["text"]), LEAD_BLOCK_THRESHOLD)
        # The full payload is preserved verbatim in the second block.
        self.assertEqual(json.loads(blocks[1]["text"]), result)

    def test_digest_is_bounded_and_never_inlines_bulk(self):
        result = {
            "title": "T" * 5000,
            "entries": list(range(4000)),
            "breakdown": {str(i): i for i in range(500)},
            "count": 7,
            "flag": True,
            "nothing": None,
        }
        line = _digest_line("tool", result)
        self.assertLessEqual(len(line), LEAD_BLOCK_MAX)
        self.assertNotIn("TTTT", line)
        self.assertIn("entries=<4000 items>", line)
        self.assertIn("breakdown=<500 keys>", line)
        self.assertIn("count=7", line)
        self.assertIn("flag=True", line)
        self.assertIn("nothing=None", line)

    def test_appended_marker_survives_a_prefix_scanning_host(self):
        """The regression this shape exists for.

        A marker appended to the END of block 0 must land inside the first
        HOST_PREFIX_SCAN characters of the joined content, or the host's
        ui:// view silently never mounts.
        """
        result = {"entry_count": 105, "transcript": "x" * 60000}
        blocks = _model_content_blocks("get_meeting_transcript", result)
        blocks[0] = dict(blocks[0], text=blocks[0]["text"] + " [marker]")
        joined = "\n".join(b["text"] for b in blocks)
        self.assertIn("[marker]", joined[:HOST_PREFIX_SCAN])


class ServerRoundTrip(unittest.TestCase):
    def test_every_tool_returns_a_wellformed_envelope(self):
        listed, _ = rpc(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        )
        tools = listed[2]["result"]["tools"]
        self.assertGreater(len(tools), 0)
        for tool in tools:
            self.assertIsInstance(tool["name"], str)
            self.assertIn("inputSchema", tool)

    def test_transcript_tool_carries_ui_metadata_and_structured_content(self):
        listed, _ = rpc(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            {"jsonrpc": "2.0", "id": 3, "method": "list_meetings", "params": {}},
        )
        tools = {t["name"]: t for t in listed[2]["result"]["tools"]}
        meta = tools["get_meeting_transcript"]["_meta"]["ui"]
        self.assertTrue(meta["resourceUri"].startswith("ui://"))

        meetings, _ = rpc(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": "list_meetings", "arguments": {"limit": 1}}},
        )
        body = json.loads(meetings[2]["result"]["content"][-1]["text"])
        found = body.get("meetings") or []
        if not found:
            self.skipTest("no meetings in the local Wispr Flow database")
        meeting_id = found[0]["meeting_id"]

        called, _ = rpc(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": "get_meeting_transcript",
                        "arguments": {"meeting_id": meeting_id}}},
        )
        result = called[2]["result"]
        # structuredContent is the app's channel and must stay complete.
        structured = result.get("structuredContent")
        if structured is None:
            self.skipTest(f"meeting {meeting_id} has no transcript artifact")
        self.assertIn("entries", structured)
        self.assertEqual(structured["entry_count"], len(structured["entries"]))
        # Model-facing text: last block always holds the full payload.
        json.loads(result["content"][-1]["text"])

    def test_ui_resource_is_served(self):
        got, _ = rpc(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "resources/list", "params": {}},
            {"jsonrpc": "2.0", "id": 3, "method": "resources/read",
             "params": {"uri": "ui://wispr/transcript"}},
        )
        listed = got[2]["result"]["resources"]
        self.assertTrue(any(r["uri"] == "ui://wispr/transcript" for r in listed))
        contents = got[3]["result"]["contents"][0]
        self.assertEqual(contents["mimeType"], "text/html;profile=mcp-app")
        self.assertIn("<!DOCTYPE html>", contents["text"])

    def test_initialize_advertises_only_implemented_capabilities(self):
        got, _ = rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        caps = got[1]["result"]["capabilities"]
        self.assertIn("tools", caps)
        self.assertIn("resources", caps)
        self.assertNotIn("prompts", caps)


if __name__ == "__main__":
    unittest.main(verbosity=2)
