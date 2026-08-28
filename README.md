# WisprMCP

**A Python library for accessing Wispr Flow's SQLite database with CLI and MCP server support.**

WisprMCP provides programmatic access to your Wispr Flow local database, enabling you to query transcripts, search conversations, analyze usage patterns, and integrate with AI workflows through the Model Context Protocol (MCP).

## Recent Updates

- **2026-08-28**: Added a second MCP App view -- `list_meetings` now serves a `ui://wispr/meetings` index with a summary drill-down that the view loads itself through the host's `serverTools` capability, so browsing meetings costs no model context
- **2026-08-28**: Large tool results now lead with a short digest content block. A host that appends control metadata to the end of the first text block and then scans only a truncated prefix for it would otherwise lose that metadata on any result over ~4 KB -- which silently prevented `ui://` views from mounting at all (see [MCP App views](#-mcp-app-views-sep-1865))
- **2026-08-27**: Added meetings support -- AI summaries, user notes, speaker-attributed NDJSON transcripts, todos, notetaker chats, calendar pre-reads, and a `get_datasource_inventory` drift check (10 tools -> 22)
- **2026-08-27**: Added the first MCP App view -- `get_meeting_transcript` serves an interactive `ui://wispr/transcript` timeline
- **2026-08-27**: Fixed `get_dictionary_entries`, which failed with `no such column: frequencySeen` after a Wispr Flow schema migration; queries now resolve columns at runtime
- **2026-08-27**: Database is now opened read-only
- **2025-07-04**: Added collect command for word extraction by day (similar to GranolaMCP)
- **2025-07-04**: Added sane defaults - `wispr list` now defaults to last 2 days
- **2025-07-04**: Fixed timestamp parsing for proper date filtering and time display
- **2025-07-04**: Initial release with full database access, CLI tools, and MCP server
- Zero external dependencies - built entirely with Python standard library
- Comprehensive search and filtering capabilities
- Rich CLI with colored output and multiple formats
- JSON-RPC 2.0 compliant MCP server for AI integration

## Complete Feature Overview

### 📚 **Library Access**
- Direct SQLite database access to Wispr Flow transcripts
- Rich data models for transcripts, conversations, and metadata
- Comprehensive search and filtering capabilities
- Zero external dependencies - pure Python standard library

### 🖥️ **Command Line Interface (7 Commands)**

| Command | Purpose | Key Features |
|---------|---------|--------------|
| `list` | List recent transcripts | Defaults to 2 days, rich table output, filtering |
| `show` | Show specific transcript | Full details, context, all text versions |
| `search` | Search transcript text | Highlighting, context, date filtering |
| `stats` | Database statistics | Overall stats, app breakdown, quality metrics |
| `apps` | App usage analysis | Usage by app, sorting, filtering |
| `export` | Export data | JSON/CSV/Markdown, conversation grouping |
| `collect` | **Extract YOUR words** | **Daily files (YYYY-MM-DD.txt) for analysis** |

**Output Features:**
- Rich colored output with semantic highlighting
- Multiple formats: table, JSON, text, markdown
- Advanced filtering: date, app, status, conversation, word count
- Sane defaults: `wispr list` shows last 2 days automatically

### 🗣️ **Word Collection (Like GranolaMCP)**
- **Extract YOUR spoken words** into daily text files
- **4 output formats**: `raw` (pure text), `words`, `sentences`, `entries`
- **Smart filtering**: Exclude apps, minimum word counts, date ranges
- **Ready for analysis**: Word clouds, linguistic analysis, voice training
- **Example**: `wispr collect ./my-words` → creates `2025-07-04.txt` with YOUR words

### 🤖 **MCP Server Integration (22 Tools)**

**Dictation transcripts**

| Tool | Purpose |
|------|---------|
| `get_recent_transcripts` | Get most recent entries |
| `list_transcripts` | List with date/app filters |
| `search_transcripts` | Search for specific text |
| `get_transcript` | Get specific transcript by ID |
| `get_conversations` | Get grouped conversations |
| `get_conversation` | Get specific conversation |
| `get_app_statistics` | App usage statistics |
| `export_transcripts` | Export data in various formats |
| `get_dictionary_entries` | Custom dictionary and snippet entries |

**Meetings** (title, AI summary, "My Thoughts" notes, speaker-attributed transcript)

| Tool | Purpose |
|------|---------|
| `list_meetings` | List meetings with participants and artifact availability |
| `get_meeting` | One meeting, optionally with its transcript |
| `get_meeting_summary` | Just the AI summary and user notes (cheapest) |
| `get_meeting_transcript` | Speaker-attributed transcript from the NDJSON artifact |
| `search_meetings` | Search titles, summaries, notes, and optionally transcripts |

**Notes, todos, chats, calendar**

| Tool | Purpose |
|------|---------|
| `list_notes` | List standalone notes |
| `get_note` | One note with content and transform history |
| `list_todos` | Action items, optionally scoped to a meeting |
| `list_notetaker_chats` | AI chat threads about meetings |
| `get_notetaker_chat` | One chat thread with all turns |
| `list_calendar_events` | Synced events with AI pre-read briefings |

**Diagnostics**

| Tool | Purpose |
|------|---------|
| `get_database_statistics` | Counts across every surface, plus date ranges |
| `get_datasource_inventory` | Every table, row count, and read coverage |

**MCP Features:**
- JSON-RPC 2.0 STDIO compliant for Claude Desktop
- Read-only database access (opened `mode=ro`); never mutates Wispr Flow data
- Meeting transcripts assembled from on-disk NDJSON with speaker-name resolution
  and user corrections applied
- Runtime column resolution, so a Wispr Flow schema migration degrades instead of
  raising `no such column`
- Token-aware transcript output: `text` (default), `markdown`, or capped `json`
- Serves two **MCP App** (`ui://`) views — a meeting index and a transcript
  timeline — see below

### 🖼️ MCP App views (SEP-1865)

Two tools declare a `ui://` resource, so a host that supports the
`io.modelcontextprotocol/ui` extension renders an interactive view instead of a
wall of JSON:

| View | Declared on | What it shows |
|------|-------------|---------------|
| `ui://wispr/meetings` | `list_meetings` | Index of meetings — filter by title or speaker and by artifact availability, with a detail pane that loads the selected meeting's AI summary and notes on demand, plus an optional 12-entry transcript preview |
| `ui://wispr/transcript` | `get_meeting_transcript` | Speaker-attributed timeline — per-speaker filtering, text search, and inline display of user corrections |

Each view is a single self-contained HTML file under `wispr_mcp/mcp/ui/` with
**zero dependencies and no network requests**, so neither can fail on a CDN. Each
declares its own fallbacks for every CSS variable and keys light/dark off the
host's reported `theme`.

#### Two payloads, one result

The model and the view get different payloads, which is the point:

| | Goes to | Contents |
|---|---|---|
| `content` | model context | the compact `text`/`markdown`/capped-`json` form |
| `structuredContent` | the view only | transcript: every entry, speakers, per-speaker breakdown, markers. index: every meeting row |

So asking for `format="text"` keeps the model's context small while the view still
renders all 100+ entries.

#### The index loads its own detail

The meeting index ships only the index rows up front. When you select a meeting it
calls `get_meeting_summary` **itself**, through the host's `serverTools`
capability, and caches the answer. Nothing about the drill-down passes through
model context, so reading several summaries costs nothing and the view scales past
the handful of rows a text response can carry.

Two consequences worth knowing if you edit the tool definitions:

- `get_meeting_summary` and `get_meeting_transcript` must stay **app-visible**.
  A host filters an app-initiated `tools/call` by the tool's `_meta.ui.visibility`,
  so giving either a model-only visibility breaks the drill-down silently.
  `tests/test_ui_resources.py` pins this.
- App-initiated calls are **schema-validated** by the host, so the arguments the
  view sends have to satisfy the tool's own `inputSchema`.

#### Large results lead with a digest block

A result whose payload exceeds `LEAD_BLOCK_THRESHOLD` is emitted as **two** text
content blocks: a short one-line digest first, then the full payload verbatim.

This is not cosmetic. A host may append control metadata to the end of the *first*
text block and then scan only a truncated prefix of the joined content for it —
Kiro Crew appends an app-render marker and its ACP layer caps each block at 4000
characters, so a single 12 KB block put the marker at offset ~12,840 and the view
silently never mounted, with no error and no log line. Leading with a digest keeps
any such appended marker a few hundred characters in. The model still receives the
complete result, because that truncation applies to the host's display event rather
than to the tool result itself.

#### Enabling the views is host-side, not server-side

In Kiro Crew the server must be routed through the MCP gateway
(**Developer → MCP Management**, or `mcp_gateway.stub_servers`), because the
gateway is what intercepts the result and resolves the `ui://` resource. Without
that you get the tool's text with no error. Note that routing a server restarts
active sessions.

These views are **viewers**. Kiro Crew answers `ui/message` and
`ui/update-model-context` with `-32601`, so a click cannot feed a selection back
into model context; every control only changes what is displayed.

Hosts with no MCP Apps support ignore the metadata entirely and both tools behave
exactly as before, so the declarations are safe unconditionally.

## Installation

### Prerequisites

- **Python 3.8+** (Python 3.9+ recommended)
- **Wispr Flow** installed and running on macOS
- **Git** for cloning the repository

### Quick Install

```bash
# Clone the repository
git clone https://github.com/d-fay/WisprMCP.git
cd WisprMCP

# Install the package
pip install -e .

# Verify installation
wispr --help
```

### PyPI Install (if published)

```bash
# Install from PyPI (when available)
pip install wispr-mcp

# Verify installation
wispr --help
```

### Development Install

```bash
# Clone and install with development dependencies
git clone https://github.com/d-fay/WisprMCP.git
cd WisprMCP
pip install -e ".[dev]"

# Run tests to verify setup
pytest

# Format code
black wispr_mcp/

# Type checking
mypy wispr_mcp/
```

### Virtual Environment (Recommended)

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
venv\Scripts\activate

# Install WisprMCP
pip install -e .
```

### System Requirements

- **macOS**: Primary platform (where Wispr Flow runs)
- **Database**: Wispr Flow must be installed and have created transcripts
- **Permissions**: Read access to `~/Library/Application Support/Wispr Flow/flow.sqlite`

### Verification

After installation, verify everything works:

```bash
# Check CLI is working
wispr --help

# Test database access
wispr stats

# Test basic functionality
wispr list --limit 5
```

## Configuration

WisprMCP automatically detects your Wispr Flow database. You can also configure custom paths:

### Environment Variables

```bash
# Custom database path
export WISPR_DATABASE_PATH="/path/to/custom/flow.sqlite"

# Custom backup directory
export WISPR_BACKUP_DIR="/path/to/backups"

# Custom meetings artifact directory (NDJSON transcripts)
export WISPR_MEETINGS_DIR="/path/to/meetings"
```

### Configuration File

Create `~/.wispr_mcp/.env`:

```bash
WISPR_DATABASE_PATH=/custom/path/flow.sqlite
WISPR_BACKUP_DIR=/custom/backups
WISPR_MEETINGS_DIR=/custom/path/meetings
```

## CLI Usage

### List Recent Transcripts

```bash
# List recent transcripts (defaults to last 2 days)
wispr list

# List from specific app
wispr list --app Slack

# List from last 3 days
wispr list --since 3d

# List with custom limit
wispr list --limit 50

# JSON output
wispr list --format json
```

### Search Transcripts

```bash
# Search for text
wispr search "hello world"

# Search in specific app
wispr search "meeting" --app Slack

# Search with date range
wispr search "project" --since 1w --until 2d

# Highlight matches
wispr search "important" --highlight

# Show context around matches
wispr search "error" --context 50
```

### Show Specific Transcript

```bash
# Show by full ID
wispr show abc123-def456-789...

# Show by partial ID (first 8 characters)
wispr show abc123de

# Show with additional context
wispr show abc123de --show-context

# Show all text versions (ASR, formatted, edited)
wispr show abc123de --show-all-versions
```

### Database Statistics

```bash
# Overall statistics
wispr stats

# Detailed statistics
wispr stats --detailed

# Statistics for specific period
wispr stats --since 1m

# Statistics for specific app
wispr stats --app Obsidian
```

### App Usage Analysis

```bash
# Top apps by usage
wispr apps

# Sort by different metrics
wispr apps --sort words
wispr apps --sort duration
wispr apps --sort last_used

# Filter by minimum entries
wispr apps --min-entries 10
```

### Export Data

```bash
# Export to JSON
wispr export --format json > transcripts.json

# Export to CSV
wispr export --format csv > transcripts.csv

# Export to Markdown
wispr export --format markdown > transcripts.md

# Export with filters
wispr export --since 1w --app Slack --format json

# Group by conversations
wispr export --group-by-conversation --format json
```

### Collect YOUR Spoken Words by Day

Extract YOUR spoken words into daily text files (YYYY-MM-DD.txt) for word cloud generation, linguistic analysis, or voice training data.

```bash
# Collect YOUR raw spoken words only (default: 7 days, no headers/metadata)
wispr collect ./my-words

# Collect YOUR words from last month
wispr collect ./words --since 1m

# Raw format: YOUR words with punctuation cleaned (default)
wispr collect ./clean --format raw --since 2w

# Sentence format: YOUR words as complete sentences (with headers)
wispr collect ./sentences --format sentences --since 2w

# Entries format: YOUR words with metadata (timestamps, apps)
wispr collect ./detailed --format entries --since 3d

# Exclude certain apps from YOUR word collection
wispr collect ./clean --exclude-apps "Wispr Flow" "ChatGPT"

# Only include longer spoken entries
wispr collect ./quality --exclude-short --min-words 10

# Example output files:
# ./my-words/2025-07-04.txt  - Contains only YOUR spoken words from July 4th
# ./my-words/2025-07-03.txt  - Contains only YOUR spoken words from July 3rd
```

**Output formats:**
- `raw` (default): Pure text, YOUR words only, ready for word cloud tools
- `words`: YOUR words with statistics headers
- `sentences`: YOUR complete sentences with metadata
- `entries`: YOUR words with timestamps and app context

## MCP Server Integration

### Claude Desktop Configuration

Add to your Claude Desktop configuration file:

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "WisprMCP": {
      "command": "python",
      "args": ["/path/to/WisprMCP/wispr_mcp/mcp/server.py"],
      "cwd": "/path/to/WisprMCP"
    }
  }
}
```

### Available MCP Tools

**Dictation:** `get_recent_transcripts`, `list_transcripts`,
`search_transcripts`, `get_transcript`, `get_conversations`, `get_conversation`,
`get_app_statistics`, `export_transcripts`, `get_dictionary_entries`

**Meetings:** `list_meetings`, `get_meeting`, `get_meeting_summary`,
`get_meeting_transcript`, `search_meetings`

**Notes / todos / chats / calendar:** `list_notes`, `get_note`, `list_todos`,
`list_notetaker_chats`, `get_notetaker_chat`, `list_calendar_events`

**Diagnostics:** `get_database_statistics`, `get_datasource_inventory`

Meeting transcripts are read from disk, not the database. `get_meeting_transcript`
defaults to `format="text"` (speaker-attributed plain text) because a full
structured transcript can be tens of thousands of tokens; use `format="json"` with
`max_entries` when you need timings, and `source="live"` for raw uncoalesced
utterances instead of the refined pass.

`list_meetings` and `get_meeting_transcript` each additionally serve an interactive
`ui://` view on hosts that support MCP Apps — see
[MCP App views](#-mcp-app-views-sep-1865).

### Example MCP Usage in Claude

```
"Show me my Slack conversations from the last week"
→ Uses list_transcripts with app=Slack and since=1w

"Search for mentions of 'project deadline' in my transcripts"
→ Uses search_transcripts with query="project deadline"

"What are my most used apps for voice transcription?"
→ Uses get_app_statistics sorted by usage

"Export my Obsidian transcripts from last month to JSON"
→ Uses export_transcripts with filters
```

## Library Usage

### Basic Usage

```python
from wispr_mcp import WisprParser, TranscriptEntry, Conversation

# Initialize parser
parser = WisprParser()

# Get recent transcripts
entries = parser.get_entries(limit=10)

# Search for text
transcript = parser.search_text("hello world")

# Get conversations
conversations = parser.get_conversations(limit=5)

# Get statistics
stats = parser.get_statistics()
```

### Advanced Filtering

```python
from datetime import datetime, timedelta
from wispr_mcp.utils.date_parser import DateParser

# Date range filtering
start_date = DateParser.parse_date("1w")  # 1 week ago
end_date = datetime.now()

entries = parser.get_entries(
    start_date=start_date,
    end_date=end_date,
    app="com.tinyspeck.slackmacgap",  # Slack
    status="formatted",
    limit=100
)

# Process entries
for entry in entries:
    print(f"{entry.app_name}: {entry.display_text}")
    print(f"Quality: {entry.quality_score}")
    print(f"Duration: {entry.duration}s")
```

### Working with Conversations

```python
# Get conversations
conversations = parser.get_conversations(limit=10)

for conv in conversations:
    print(f"Conversation: {conv.conversation_id}")
    print(f"App: {conv.app_name}")
    print(f"Duration: {conv.duration}s")
    print(f"Entries: {conv.entry_count}")
    print(f"Summary: {conv.summary}")

    # Export to markdown
    markdown = conv.to_markdown()
    with open(f"conversation_{conv.conversation_id[:8]}.md", "w") as f:
        f.write(markdown)
```

## Database Schema

WisprMCP works with Wispr Flow's SQLite database schema:

### Main Tables

- **History**: Dictation entries with ASR, formatted, and edited text
- **Dictionary**: Custom vocabulary and snippet entries
- **Meetings**: Recorded meetings with AI `summary`, user `notes`, and `speakerMap`
- **TranscriptCorrections**: User edits to individual meeting transcript entries
- **Notes** / **NoteVersions** / **NoteImages**: Standalone notes and their history
- **Todos**: Action items, optionally linked to a meeting
- **NotetakerChats** / **NotetakerChatMessages**: AI chat threads about a meeting
- **CalendarEvents**: Synced events with AI pre-read briefings
- **SharedNotes**: Notes shared by slug

### On-Disk Meeting Artifacts

Meeting transcript text is **not** in the database. It lives beside it:

```
~/Library/Application Support/Wispr Flow/meetings/<meetingId>/
    live.ndjson      raw diarized utterances
    refined.ndjson   server-refined, coalesced utterances
    upload.ogg       recorded audio (never read by this connector)
```

`Meetings.speakerMap` maps the NDJSON numeric `speaker.id` to a person name; see
`wispr_flow_database_schema.md` for the resolution precedence and line formats.

### Key Fields

- `transcriptEntityId`: Unique transcript identifier
- `asrText`: Raw speech recognition output
- `formattedText`: AI-formatted text
- `editedText`: User-edited text
- `timestamp`: Creation timestamp
- `app`: Application bundle ID
- `duration`: Recording duration in seconds
- `numWords`: Word count
- `conversationId`: Conversation grouping
- `additionalContext`: JSON context data

## Data Privacy and Security

- **Local Access Only**: WisprMCP only accesses your local Wispr Flow database
- **YOUR Words Only**: The `collect` command extracts only YOUR spoken words (transcripts)
- **No File Access**: Does NOT access your Obsidian vault, documents, or personal files
- **No Network Requests**: Zero external dependencies, no data transmission
- **Read-Only Access**: Database is accessed in read-only mode
- **App Context Only**: When you see "Obsidian" it means you were speaking into that app
- **Respect User Privacy**: All processing happens locally on your machine

**What WisprMCP sees:**
- ✅ YOUR voice transcripts from Wispr Flow
- ✅ Which app you were speaking into (e.g., "Obsidian", "Slack")
- ✅ When you spoke and for how long

**What WisprMCP does NOT see:**
- ❌ Your actual Obsidian notes or vault content
- ❌ Your documents, files, or personal data
- ❌ Anything outside the Wispr Flow database

## Architecture

### Project Structure

```
wispr_mcp/
├── core/                      # Core business logic
│   ├── parser.py             # Database access and parsing
│   ├── transcript.py         # Transcript data models
│   ├── conversation.py       # Conversation data models
│   ├── meeting.py            # Meeting, summary and speaker-map models
│   ├── notes.py              # Notes, todos, chats, calendar models
│   └── artifacts.py          # On-disk NDJSON transcript artifacts
├── utils/                     # Utility functions
│   ├── config.py             # Configuration management
│   └── date_parser.py        # Date parsing utilities
├── cli/                       # Command-line interface
│   ├── main.py               # CLI entry point
│   ├── commands/             # CLI command implementations
│   └── formatters/           # Output formatting
└── mcp/                      # MCP server implementation
    ├── server.py             # JSON-RPC 2.0 server, content-block envelope
    ├── tools.py              # MCP tool definitions
    ├── apps.py               # ui:// resource registry (MCP Apps, SEP-1865)
    └── ui/                   # Self-contained view HTML, zero dependencies
        ├── meetings.html     # Meeting index + summary drill-down
        └── transcript.html   # Speaker-attributed transcript timeline

tests/                         # Stdlib unittest, no dependencies
├── test_server_envelope.py   # Content-block shape and server round-trips
└── test_ui_resources.py      # ui:// registry and tool<->view bindings
```

### Design Principles

- **Zero Dependencies**: Pure Python standard library implementation
- **Live Data Access**: Always reads from current database state
- **Graceful Error Handling**: Robust error handling throughout
- **Flexible Filtering**: Comprehensive search and filter options
- **Multiple Interfaces**: Library, CLI, and MCP server from single codebase

## Contributing

### Development Setup

```bash
# Clone repository
git clone https://github.com/d-fay/WisprMCP.git
cd WisprMCP

# Install in editable mode
pip install -e .

# Run tests (stdlib unittest -- no test dependencies)
python3 -m unittest discover -s tests -v
```

### Running Tests

The suite is plain `unittest` from the standard library, matching the project's
zero-dependency principle. It drives the real `mcp_server.py` over stdio and reads
the real Wispr Flow database, so tests that need data skip cleanly on a machine
with an empty database rather than failing.

```bash
# Run all tests
python3 -m unittest discover -s tests -v

# Run one module
python3 -m unittest tests.test_ui_resources -v

# Run one test
python3 -m unittest tests.test_server_envelope.ContentBlockShape -v
```

To check a `ui://` view's own behaviour without a browser, run its script against
a stub host that replays the MCP Apps bridge (`ui/initialize` → `initialized` →
`tool-input` → `tool-result`, plus the app-initiated `tools/call` path). A headless
browser is a poor oracle here: a screenshot can land mid-handshake and show an
empty frame that is actually fine.

## Troubleshooting

### Database Not Found

```bash
# Check if Wispr Flow is installed
ls ~/Library/Application\ Support/Wispr\ Flow/

# Set custom database path
export WISPR_DATABASE_PATH="/path/to/flow.sqlite"

# Verify database access
wispr stats
```

### Permission Issues

```bash
# Check database permissions
ls -la ~/Library/Application\ Support/Wispr\ Flow/flow.sqlite

# Ensure Wispr Flow isn't running exclusively
pkill "Wispr Flow"
```

### CLI Output Issues

```bash
# Disable colors if terminal doesn't support them
export NO_COLOR=1
wispr list

# Force colors
export FORCE_COLOR=1
wispr list --no-color
```

### MCP Server Issues

```bash
# Test MCP server directly
python wispr_mcp/mcp/server.py --debug

# Check Claude Desktop logs
# macOS: ~/Library/Logs/Claude/
# Look for WisprMCP related errors
```

## Performance

- **Database Size**: Handles databases with 100,000+ entries efficiently
- **Memory Usage**: Minimal memory footprint with lazy loading
- **Query Speed**: Optimized queries with strategic indexing
- **CLI Responsiveness**: Fast command execution with pagination

## License

MIT License - see LICENSE file for details.

## Changelog

### Unreleased
- **NEW**: `ui://wispr/meetings` — meeting index MCP App view with a lazy summary
  drill-down over the host's `serverTools` capability
- **NEW**: `tests/` — stdlib `unittest` suite covering the content-block envelope,
  the `ui://` registry, and the tool↔view bindings
- **FIX**: large results lead with a digest content block, so a host that appends
  control metadata to the first block and scans only a truncated prefix does not
  lose it (this silently prevented `ui://` views from mounting)
- **FIX**: `setup.py` version now matches `__version__` (was 0.1.0 vs 0.2.0)

### v0.2.0 (2026-08-27)
- **NEW**: Meetings surface — `list_meetings`, `get_meeting`, `get_meeting_summary`,
  `get_meeting_transcript`, `search_meetings`
- **NEW**: Notes, todos, notetaker chats and calendar pre-reads
- **NEW**: `get_datasource_inventory` — every table, row count, and read coverage,
  so a Wispr Flow update that adds a table is visible instead of silently unread
- **NEW**: `ui://wispr/transcript` — first MCP App view (SEP-1865)
- **NEW**: Speaker-name resolution from `speakerMap`, and user corrections applied
  to transcript text
- **IMPROVEMENT**: Database opened read-only (`mode=ro`)
- **IMPROVEMENT**: Summary normalisation repairs glued headings and collapses
  duplicated sections in a locally cached summary
- **FIX**: `get_dictionary_entries` no longer raises `no such column:
  frequencySeen`; columns resolve at runtime
- 10 tools → 22

### v0.1.0 (2025-07-04)
- **NEW**: Added `collect` command for extracting words by day (YYYY-MM-DD.txt files)
- **NEW**: Sane defaults - `wispr list` now defaults to last 2 days instead of all entries
- **IMPROVEMENT**: Fixed timestamp parsing for proper date filtering and display
- **IMPROVEMENT**: Enhanced CLI help with better examples and date format info
- Initial release with core library, complete CLI (7 commands), and MCP server (10 tools)
- Zero external dependencies implementation
- Comprehensive documentation and examples

## Related Projects

- **Upstream**: [pedramamini/WisprMCP](https://github.com/pedramamini/WisprMCP) — this
  repository is a fork; the meetings surface, the `ui://` MCP App views and the
  test suite were added here
- **Wispr Flow**: AI-powered voice transcription app
- **Claude Desktop**: AI assistant with MCP support
- **Model Context Protocol**: Standard for AI tool integration
- **MCP Apps (SEP-1865)**: The `io.modelcontextprotocol/ui` extension the `ui://`
  views implement

## Support

- **Issues**: [GitHub Issues](https://github.com/d-fay/WisprMCP/issues)
- **Documentation**: This README and inline code documentation

## Quick Reference

### Most Common Commands
```bash
# List recent transcripts (last 2 days)
wispr list

# Collect YOUR spoken words for analysis
wispr collect ./my-words

# Search YOUR transcripts
wispr search "project"

# Show database stats
wispr stats

# Get app usage breakdown
wispr apps
```

### Word Collection (Key Feature)
```bash
# Extract YOUR raw spoken words by day → ./my-words/2025-07-04.txt
wispr collect ./my-words                    # Last 7 days, raw format
wispr collect ./words --since 1m            # Last month
wispr collect ./clean --exclude-apps "ChatGPT"  # Exclude certain apps
```

### MCP Integration
Add to Claude Desktop config:
```json
{
  "mcpServers": {
    "WisprMCP": {
      "command": "python",
      "args": ["/path/to/WisprMCP/mcp_server.py"],
      "cwd": "/path/to/WisprMCP"
    }
  }
}
```