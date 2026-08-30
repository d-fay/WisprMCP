# Security Audit — WisprMCP

**Date:** 2026-08-30
**Scope:** Full repository at commit `e6fbcae` — all Python source (26 files), both MCP App
HTML views, GitHub Actions workflows, packaging, tests, documentation, and the complete
git history of every branch.
**Method:** Manual line-by-line review of every source file; static sweeps for network,
code-execution, and obfuscation primitives; full-history scans for secrets, exfiltration
endpoints, and later-removed code; Trojan-Source (invisible Unicode) scan; dynamic
verification (module imports under a socket canary, offline test suite).

---

## Verdict

**No malicious or nefarious code was found. No high-severity vulnerabilities were found.**

The codebase does what it claims: read-only, local-only access to Wispr Flow's SQLite
database and NDJSON artifacts, exposed via a library, CLI, and stdio MCP server. The
security-relevant claims in the README were verified against the code, with one
documentation inaccuracy (the "zero dependencies" claim — see W2).

## Verified security properties

| Claim | Status | Evidence |
|---|---|---|
| No network activity | ✅ Verified | No `urllib`/`socket`/`http`/`requests` imports anywhere in package code or in any historical commit; UI views fetch nothing (enforced by `tests/test_ui_resources.py::test_views_declare_no_external_origins`); all modules import cleanly under a socket canary. |
| Read-only database access | ✅ Verified | Single connection factory opens `file:<path>?mode=ro` (`core/parser.py:147`); SQLite enforces read-only at the connection level. No write statements exist. |
| No SQL injection | ✅ Verified | Every user/tool-supplied *value* is a bound `?` parameter. Dynamic SQL fragments are identifiers only, drawn from hardcoded allowlists intersected with `PRAGMA table_info` results (`_existing_columns`), never from input. |
| No code-execution primitives | ✅ Verified | No `eval`/`exec`/`pickle`/`marshal`/`__import__`/`os.system`; `subprocess` appears only in tests, spawning the local server under test. |
| No resource-read traversal | ✅ Verified | `resources/read` resolves URIs against a fixed dict of two hardcoded filenames (`mcp/apps.py`); the URI never touches a path. |
| No XSS in MCP App views | ✅ Verified | Both views escape all interpolated data via an `esc()` helper covering `&<>"'`; the mini-markdown renderer escapes *before* introducing markup; regex built from search input is `re`-escaped; colors come from a fixed palette. |
| No committed secrets | ✅ Verified | Full-history scan: the only "secret" matches are proper `${{ secrets.* }}` workflow references. |
| No hidden/removed malicious code | ✅ Verified | The only files ever deleted from history are superseded copies of the same two Claude workflow files. All committed URLs are GitHub/packaging links. |
| No Trojan-Source tricks | ✅ Verified | No bidi/zero-width Unicode control characters in any source file. |
| No install-time hooks | ✅ Verified | `setup.py` is declarative — no custom `cmdclass`, no scripts. |

## Findings

None are malicious; all are hardening or robustness items, ranked by priority.

### W1 — CI: automated review workflow holds write permissions (Medium, hardening)

`.github/workflows/claude-code-review.yml` runs on every `pull_request`
(opened/synchronize) and grants `contents: write`, `pull-requests: write`,
`issues: write`, `id-token: write`; `claude.yml` additionally grants `actions: write`.
History shows these were deliberately escalated from `read` (commits `b6d1e31`,
`adc151c`). An automated agent that ingests untrusted PR content (diffs, descriptions,
comments) while holding `contents: write` is a prompt-injection target: adversarial text
in a PR could try to steer the action into pushing changes. Fork PRs receive no secrets
under the `pull_request` event, which limits exposure to same-repo branches, but the
review job only needs to comment.

*Recommendation:* drop the review workflow to `contents: read` (keep
`pull-requests: write` for comments); reserve write permissions for the
mention-triggered `claude.yml` flow. Pin actions by commit SHA instead of the moving
`@beta` / `@v4` tags.

### W2 — "Zero external dependencies" claim is inaccurate, and the fallback is broken (Low, robustness/docs)

`setup.py` declares `install_requires=["rich>=10.0.0"]`, and the CLI imports `rich`
(`cli/commands/stats.py`, `cli/formatters/table.py`). The intended graceful fallback
does not work: without `rich` installed, `import wispr_mcp.cli.main` raises
`NameError: name 'Panel' is not defined`, because `stats.py` uses bare `-> Panel`
annotations (lines 269, 301, 378) that are evaluated at class-creation time while
`Panel` is only bound inside the `try: import rich` block / `TYPE_CHECKING`. The whole
CLI is therefore hard-dependent on `rich`. The MCP server and core library are genuinely
stdlib-only (verified by import inspection).

*Recommendation:* quote those three annotations (or add
`from __future__ import annotations`), then either keep `rich` as an optional extra or
amend the README/CLAUDE.md "zero dependencies" claims to "MCP server and core library
are dependency-free."

### W3 — MCP tool arguments are not validated server-side (Low, defense in depth)

`WisprTools.execute_tool` splats client-supplied `arguments` directly into handlers.
The JSON-Schema bounds advertised in `tools/list` (e.g. `limit` ≤ 100) are not
enforced, so a client can pass `limit=10**9` (unbounded query) or wrong types
(caught, returned as error strings). Exposure is minimal — the server is local, stdio,
read-only, and serves a trusted host — but clamping `limit`/`offset` and type-checking
would be cheap.

### W4 — Meeting IDs reach filesystem paths without shape validation (Low, defense in depth)

`MeetingArtifactStore.meeting_dir()` computes `meetings_dir / meeting_id`. Through the
MCP/CLI surface this is not exploitable: IDs are first resolved against the `Meetings`
table and only two fixed filenames (`live.ndjson`, `refined.ndjson`) are ever read, then
parsed as JSON. But the public library API (`load_transcript`, `available_artifacts`,
`artifact_summary`) called with a hostile string would resolve `../`-style paths.
A `A-Za-z0-9-` / UUID pattern check on `meeting_id` would close it. Related nit:
prefix lookup uses `LIKE ?` with the raw prefix, so `%`/`_` in an ID argument act as
wildcards (correctness quirk only — all rows belong to the user).

### W5 — CSV export is not hardened against spreadsheet formula injection (Low)

`wispr export --format csv` writes `display_text` (and conversation summaries) verbatim.
A cell beginning with `=`, `+`, `-`, or `@` is interpreted as a formula by Excel/Sheets.
Since transcript text can be influenced by whatever is dictated or transcribed,
prefix-escape such cells (e.g. lead with `'`) or quote-guard them.

### W6 — Informational notes

- **`.env` is loaded from the current working directory** (`utils/config.py`), so
  running `wispr` inside an untrusted directory lets that directory's `.env` redirect
  `WISPR_DATABASE_PATH`/`WISPR_MEETINGS_DIR`. Impact is limited to choosing which local
  files are read — the standard dotenv trade-off, noted for awareness.
- **Identifier quoting nit:** `get_datasource_inventory` and `_columns` interpolate
  table names sourced from `sqlite_master` into `"{table}"` without doubling embedded
  `"` characters. A table name containing a quote (legal in SQLite) produces a caught
  syntax error against a read-only connection to the user's own database — no realistic
  impact; `table.replace('"', '""')` would be strictly correct.
- **UI plumbing:** the views `postMessage(..., "*")` and accept messages without an
  `event.origin` check. This is the conventional pattern for null-origin sandboxed
  MCP-Apps iframes (there is no stable origin to pin), and because all rendering is
  escaped, a spoofed message could at most alter displayed content inside the widget.
- **Inherent data sensitivity (by design, not a bug):** the tools expose everything
  Wispr Flow stores — dictated text from every app, `additionalContext` (accessibility
  text, active URLs), dictionary snippets, meeting transcripts, shared-note owner
  emails, calendar pre-reads. Connecting this server to any AI host exports that data
  into model context; users should treat host selection accordingly. Processing itself
  stays local, as documented.
- `wispr_mcp_config.json` hardcodes the author's personal absolute path — cosmetic.

## Files reviewed

All repository files were read in full: `setup.py`, `mcp_server.py`, every module under
`wispr_mcp/` (core, cli, mcp, utils, ui HTML), `tests/`, both workflow files, config and
dotfile templates; README and schema documentation were reviewed for embedded
instructions or misleading claims; full `git log -p` history was scanned across all
branches.
