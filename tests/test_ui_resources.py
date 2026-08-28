#!/usr/bin/env python3
"""Tests for the ui:// (MCP Apps) surface. Stdlib only, no deps.

Run: python3 -m unittest discover -s tests -v   (from the repo root)
"""
import json
import os
import re
import subprocess
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from wispr_mcp.mcp.apps import (  # noqa: E402
    APP_MIME_TYPE,
    MEETINGS_URI,
    TRANSCRIPT_URI,
    UI_RESOURCES,
    list_ui_resources,
    read_ui_resource,
)

#: Tools the meeting-index view calls on itself through the host's serverTools
#: capability. The host filters an app-initiated tools/call by the tool's
#: _meta.ui.visibility, so any of these gaining a model-only visibility would
#: silently break the drill-down.
APP_CALLED_TOOLS = ("get_meeting_summary", "get_meeting_transcript")


def rpc(*messages):
    payload = "\n".join(json.dumps(m) for m in messages) + "\n"
    proc = subprocess.run(
        [sys.executable, "mcp_server.py"],
        input=payload, capture_output=True, text=True, cwd=REPO,
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


def tools_by_name():
    got, _ = rpc(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    )
    return {t["name"]: t for t in got[2]["result"]["tools"]}


class Registry(unittest.TestCase):
    def test_every_registered_resource_exists_on_disk(self):
        for uri, resource in UI_RESOURCES.items():
            self.assertTrue(resource.path.is_file(), f"{uri} -> {resource.path} missing")

    def test_both_views_are_listed(self):
        listed = {r["uri"]: r for r in list_ui_resources()}
        self.assertIn(TRANSCRIPT_URI, listed)
        self.assertIn(MEETINGS_URI, listed)
        for uri, entry in listed.items():
            self.assertEqual(entry["mimeType"], APP_MIME_TYPE, uri)
            self.assertTrue(entry["name"], uri)
            self.assertTrue(entry["description"], uri)

    def test_unknown_uri_reads_as_none(self):
        self.assertIsNone(read_ui_resource("ui://wispr/does-not-exist"))

    def test_views_declare_no_external_origins(self):
        """The declared csp promises zero external origins; the HTML must match.

        Comments are stripped first: both views carry a note explaining why the
        host's esm.sh allowance is deliberately unused, and prose about an origin
        is not a reference to it.
        """
        for uri, resource in UI_RESOURCES.items():
            self.assertEqual(resource.csp.get("resourceDomains"), [], uri)
            html = resource.path.read_text(encoding="utf-8")
            stripped = re.sub(r"<!--.*?-->", "", html, flags=re.S)
            stripped = re.sub(r"//.*$", "", stripped, flags=re.M)
            for needle in ('src="http', 'href="http', "esm.sh", "unpkg", "jsdelivr",
                           'fetch("http', 'import("http', "XMLHttpRequest"):
                if needle in stripped:
                    line = next((i + 1 for i, l in enumerate(stripped.splitlines())
                                 if needle in l), 0)
                    self.fail(f"{uri} references an external origin "
                              f"({needle!r} at stripped line {line})")

    def test_views_are_self_contained_html(self):
        for uri, resource in UI_RESOURCES.items():
            html = resource.path.read_text(encoding="utf-8")
            self.assertTrue(html.lstrip().lower().startswith("<!doctype html>"), uri)
            self.assertIn("<script>", html, uri)
            # The host does not send styles.variables, so each view must carry
            # its own CSS-var fallbacks and key light/dark off hostContext.theme.
            self.assertIn("data-theme", html, uri)


class ToolWiring(unittest.TestCase):
    def test_index_view_is_bound_to_list_meetings(self):
        ui = tools_by_name()["list_meetings"]["_meta"]["ui"]
        self.assertEqual(ui["resourceUri"], MEETINGS_URI)
        self.assertIn("model", ui["visibility"])
        self.assertIn("app", ui["visibility"])

    def test_transcript_view_is_bound_to_get_meeting_transcript(self):
        ui = tools_by_name()["get_meeting_transcript"]["_meta"]["ui"]
        self.assertEqual(ui["resourceUri"], TRANSCRIPT_URI)

    def test_tools_the_view_calls_stay_app_visible(self):
        tools = tools_by_name()
        for name in APP_CALLED_TOOLS:
            visibility = tools[name].get("_meta", {}).get("ui", {}).get("visibility")
            if visibility is None:
                continue  # absent means both audiences, per SEP-1865
            self.assertIn("app", visibility,
                          f"{name} is called by the index view but is not app-visible")

    def test_every_declared_resource_uri_is_servable(self):
        """A tool must never advertise a ui:// resource this server cannot read."""
        declared = {
            t["_meta"]["ui"]["resourceUri"]
            for t in tools_by_name().values()
            if t.get("_meta", {}).get("ui", {}).get("resourceUri")
        }
        self.assertTrue(declared)
        got, _ = rpc(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            *[
                {"jsonrpc": "2.0", "id": 10 + i, "method": "resources/read",
                 "params": {"uri": uri}}
                for i, uri in enumerate(sorted(declared))
            ],
        )
        for i, uri in enumerate(sorted(declared)):
            reply = got[10 + i]
            self.assertNotIn("error", reply, f"{uri} is declared but not servable")
            contents = reply["result"]["contents"][0]
            self.assertEqual(contents["mimeType"], APP_MIME_TYPE)
            self.assertIn("<!DOCTYPE html>", contents["text"])


class IndexPayload(unittest.TestCase):
    def setUp(self):
        got, _ = rpc(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": "list_meetings", "arguments": {"limit": 20}}},
        )
        self.result = got[2]["result"]

    def test_index_rows_are_carried_in_structured_content(self):
        structured = self.result.get("structuredContent")
        self.assertIsNotNone(structured, "the view has no index to render without this")
        self.assertIn("meetings", structured)
        self.assertIn("count", structured)
        self.assertIn("filters", structured)
        self.assertEqual(structured["count"], len(structured["meetings"]))

    def test_rows_carry_the_fields_the_view_renders(self):
        rows = self.result["structuredContent"]["meetings"]
        if not rows:
            self.skipTest("no meetings in the local Wispr Flow database")
        for field in ("meeting_id", "title", "created_at", "duration", "participants",
                      "has_summary", "has_transcript", "has_notes", "chat_count"):
            self.assertIn(field, rows[0], f"the index view renders {field}")

    def test_ui_payload_key_never_leaks_into_model_text(self):
        body = json.loads(self.result["content"][-1]["text"])
        self.assertNotIn("_ui_structured", body)
        self.assertIn("meetings", body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
