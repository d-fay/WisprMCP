"""
MCP tools for WisprMCP server.
"""

from typing import Dict, Any, List, Optional
import json

from ..core.parser import WisprParser
from ..utils.date_parser import DateParser


class WisprTools:
    """MCP tools for Wispr Flow database access."""
    
    def __init__(self, db_path: Optional[str] = None):
        self.parser = WisprParser(db_path)
    
    def get_tools_schema(self) -> List[Dict[str, Any]]:
        """Get the schema for all available tools."""
        return [
            {
                "name": "get_recent_transcripts",
                "description": "Get the most recent transcript entries regardless of date",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of transcripts to return",
                            "default": 10,
                            "minimum": 1,
                            "maximum": 100
                        },
                        "app": {
                            "type": "string",
                            "description": "Filter by app (bundle ID or name like 'Slack', 'Obsidian')"
                        },
                        "status": {
                            "type": "string",
                            "description": "Filter by status (formatted, empty, no_audio, etc.)"
                        },
                        "include_archived": {
                            "type": "boolean",
                            "description": "Include archived entries",
                            "default": False
                        }
                    }
                }
            },
            {
                "name": "list_transcripts",
                "description": "List transcript entries with date and app filters",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "since": {
                            "type": "string",
                            "description": "Show entries since this date/time (e.g. '3d', '1w', '2024-01-01')"
                        },
                        "until": {
                            "type": "string",
                            "description": "Show entries until this date/time"
                        },
                        "app": {
                            "type": "string",
                            "description": "Filter by app (bundle ID or name)"
                        },
                        "status": {
                            "type": "string",
                            "description": "Filter by status"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of entries",
                            "default": 20,
                            "minimum": 1,
                            "maximum": 100
                        },
                        "include_archived": {
                            "type": "boolean",
                            "description": "Include archived entries",
                            "default": False
                        }
                    }
                }
            },
            {
                "name": "search_transcripts",
                "description": "Search transcript entries for specific text",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Text to search for"
                        },
                        "since": {
                            "type": "string",
                            "description": "Search entries since this date/time"
                        },
                        "until": {
                            "type": "string",
                            "description": "Search entries until this date/time"
                        },
                        "app": {
                            "type": "string",
                            "description": "Filter by app"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of results",
                            "default": 50,
                            "minimum": 1,
                            "maximum": 100
                        }
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "get_transcript",
                "description": "Get a specific transcript entry by ID",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "transcript_id": {
                            "type": "string",
                            "description": "Transcript ID (full UUID or first 8 characters)"
                        },
                        "include_context": {
                            "type": "boolean",
                            "description": "Include additional context information",
                            "default": False
                        }
                    },
                    "required": ["transcript_id"]
                }
            },
            {
                "name": "get_conversations",
                "description": "Get conversations (grouped transcript entries)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "since": {
                            "type": "string",
                            "description": "Show conversations since this date/time"
                        },
                        "until": {
                            "type": "string",
                            "description": "Show conversations until this date/time"
                        },
                        "app": {
                            "type": "string",
                            "description": "Filter by app"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of conversations",
                            "default": 10,
                            "minimum": 1,
                            "maximum": 50
                        }
                    }
                }
            },
            {
                "name": "get_conversation",
                "description": "Get a specific conversation by ID",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "conversation_id": {
                            "type": "string",
                            "description": "Conversation ID"
                        },
                        "format": {
                            "type": "string",
                            "description": "Output format (json or markdown)",
                            "enum": ["json", "markdown"],
                            "default": "json"
                        }
                    },
                    "required": ["conversation_id"]
                }
            },
            {
                "name": "get_app_statistics",
                "description": "Get usage statistics for apps",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of apps to return",
                            "default": 20,
                            "minimum": 1,
                            "maximum": 100
                        },
                        "sort_by": {
                            "type": "string",
                            "description": "Sort apps by field",
                            "enum": ["entries", "words", "duration", "latency", "last_used"],
                            "default": "entries"
                        },
                        "min_entries": {
                            "type": "integer",
                            "description": "Minimum number of entries to include app",
                            "default": 1,
                            "minimum": 1
                        }
                    }
                }
            },
            {
                "name": "get_database_statistics",
                "description": "Get overall database statistics",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "since": {
                            "type": "string",
                            "description": "Calculate stats since this date/time"
                        },
                        "until": {
                            "type": "string",
                            "description": "Calculate stats until this date/time"
                        },
                        "app": {
                            "type": "string",
                            "description": "Filter by app"
                        }
                    }
                }
            },
            {
                "name": "export_transcripts",
                "description": "Export transcript data in various formats",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "format": {
                            "type": "string",
                            "description": "Export format",
                            "enum": ["json", "csv", "markdown", "text"],
                            "default": "json"
                        },
                        "since": {
                            "type": "string",
                            "description": "Export entries since this date/time"
                        },
                        "until": {
                            "type": "string",
                            "description": "Export entries until this date/time"
                        },
                        "app": {
                            "type": "string",
                            "description": "Filter by app"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of entries to export",
                            "minimum": 1,
                            "maximum": 1000
                        },
                        "group_by_conversation": {
                            "type": "boolean",
                            "description": "Group entries by conversation",
                            "default": False
                        }
                    }
                }
            },
            {
                "name": "get_dictionary_entries",
                "description": "Get custom dictionary entries used for speech recognition corrections",
                "inputSchema": {
                    "type": "object",
                    "properties": {}
                }
            },
            {
                "name": "list_meetings",
                "description": "List recorded meetings with their AI summary availability, participants, and artifacts. Meetings are separate from dictation transcripts.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "since": {
                            "type": "string",
                            "description": "Only meetings since this date/time (e.g. '7d', '1w', '2026-08-01')"
                        },
                        "until": {
                            "type": "string",
                            "description": "Only meetings until this date/time"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of meetings to return",
                            "default": 20,
                            "minimum": 1,
                            "maximum": 200
                        },
                        "with_summary_only": {
                            "type": "boolean",
                            "description": "Only meetings that have an AI-generated summary",
                            "default": False
                        },
                        "finalized_only": {
                            "type": "boolean",
                            "description": "Only meetings the app has finalized",
                            "default": False
                        },
                        "include_deleted": {
                            "type": "boolean",
                            "description": "Include soft-deleted meetings",
                            "default": False
                        },
                        "include_content": {
                            "type": "boolean",
                            "description": "Include full summary and notes text for each meeting (larger response)",
                            "default": False
                        }
                    }
                }
            },
            {
                "name": "get_meeting",
                "description": "Get one meeting including its AI summary, user notes ('My Thoughts'), participants, and artifact availability",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "meeting_id": {
                            "type": "string",
                            "description": "Meeting ID (full UUID or unique prefix)"
                        },
                        "include_transcript": {
                            "type": "boolean",
                            "description": "Also load the transcript from disk (can be large)",
                            "default": False
                        },
                        "transcript_source": {
                            "type": "string",
                            "description": "Which transcript artifact to read when include_transcript is set",
                            "enum": ["auto", "refined", "live"],
                            "default": "auto"
                        },
                        "format": {
                            "type": "string",
                            "description": "Output format",
                            "enum": ["json", "markdown"],
                            "default": "json"
                        }
                    },
                    "required": ["meeting_id"]
                }
            },
            {
                "name": "get_meeting_summary",
                "description": "Get just the AI-generated summary and user notes for a meeting, without the transcript. Cheapest way to learn what a meeting was about. Speaker placeholders are resolved to names and duplicated sections in the cached summary are collapsed.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "meeting_id": {
                            "type": "string",
                            "description": "Meeting ID (full UUID or unique prefix)"
                        },
                        "raw": {
                            "type": "boolean",
                            "description": "Return the stored text untouched: no speaker resolution, no duplicate-section repair. Use this when writing text back into Wispr Flow, so the round-trip stays faithful.",
                            "default": False
                        }
                    },
                    "required": ["meeting_id"]
                }
            },
            {
                "name": "get_meeting_transcript",
                "description": "Get a meeting's speaker-attributed transcript, read from its on-disk NDJSON artifact. Speaker names are resolved via the meeting's speaker map and user corrections are applied by default.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "meeting_id": {
                            "type": "string",
                            "description": "Meeting ID (full UUID or unique prefix)"
                        },
                        "source": {
                            "type": "string",
                            "description": "'auto' prefers the refined artifact and falls back to live; 'refined' is cleaner coalesced text; 'live' is raw per-utterance capture",
                            "enum": ["auto", "refined", "live"],
                            "default": "auto"
                        },
                        "format": {
                            "type": "string",
                            "description": "'text' is speaker-attributed plain text (most compact), 'markdown' adds timestamps and a header, 'json' returns structured entries with timings",
                            "enum": ["text", "markdown", "json"],
                            "default": "text"
                        },
                        "apply_corrections": {
                            "type": "boolean",
                            "description": "Substitute user-corrected text where it exists",
                            "default": True
                        },
                        "max_entries": {
                            "type": "integer",
                            "description": "Cap the number of entries returned in json format",
                            "minimum": 1,
                            "maximum": 2000
                        }
                    },
                    "required": ["meeting_id"]
                }
            },
            {
                "name": "search_meetings",
                "description": "Search meetings by title, AI summary, and user notes. Set search_transcripts to also search transcript text from disk (slower).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Text to search for"
                        },
                        "search_transcripts": {
                            "type": "boolean",
                            "description": "Also search the on-disk transcript artifacts",
                            "default": False
                        },
                        "since": {
                            "type": "string",
                            "description": "Only meetings since this date/time"
                        },
                        "until": {
                            "type": "string",
                            "description": "Only meetings until this date/time"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of matching meetings",
                            "default": 20,
                            "minimum": 1,
                            "maximum": 100
                        },
                        "max_matches_per_meeting": {
                            "type": "integer",
                            "description": "Cap transcript match snippets returned per meeting",
                            "default": 10,
                            "minimum": 1,
                            "maximum": 200
                        }
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "list_notes",
                "description": "List standalone notes (not meeting notes) with previews",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "since": {
                            "type": "string",
                            "description": "Only notes created since this date/time"
                        },
                        "until": {
                            "type": "string",
                            "description": "Only notes created until this date/time"
                        },
                        "search": {
                            "type": "string",
                            "description": "Filter to notes containing this text"
                        },
                        "pinned_only": {
                            "type": "boolean",
                            "description": "Only pinned notes",
                            "default": False
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of notes",
                            "default": 20,
                            "minimum": 1,
                            "maximum": 200
                        },
                        "include_content": {
                            "type": "boolean",
                            "description": "Include full note bodies rather than previews",
                            "default": False
                        },
                        "include_deleted": {
                            "type": "boolean",
                            "description": "Include soft-deleted notes",
                            "default": False
                        }
                    }
                }
            },
            {
                "name": "get_note",
                "description": "Get one standalone note with its full content, and optionally its AI transform/edit history",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "note_id": {
                            "type": "string",
                            "description": "Note ID (full UUID or unique prefix)"
                        },
                        "include_versions": {
                            "type": "boolean",
                            "description": "Include prior versions of the note",
                            "default": False
                        },
                        "format": {
                            "type": "string",
                            "description": "Output format",
                            "enum": ["json", "markdown"],
                            "default": "json"
                        }
                    },
                    "required": ["note_id"]
                }
            },
            {
                "name": "list_todos",
                "description": "List action items / todos, optionally scoped to one meeting",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "meeting_id": {
                            "type": "string",
                            "description": "Only todos from this meeting"
                        },
                        "status": {
                            "type": "string",
                            "description": "Filter by status (e.g. 'open')"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of todos",
                            "default": 50,
                            "minimum": 1,
                            "maximum": 500
                        },
                        "include_archived": {
                            "type": "boolean",
                            "description": "Include archived todos",
                            "default": False
                        },
                        "include_deleted": {
                            "type": "boolean",
                            "description": "Include soft-deleted todos",
                            "default": False
                        }
                    }
                }
            },
            {
                "name": "list_notetaker_chats",
                "description": "List AI notetaker chat threads (questions asked about a meeting and the assistant's answers)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "meeting_id": {
                            "type": "string",
                            "description": "Only chats about this meeting"
                        },
                        "kind": {
                            "type": "string",
                            "description": "Filter by chat kind (e.g. 'meeting_chat')"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of chats",
                            "default": 20,
                            "minimum": 1,
                            "maximum": 100
                        },
                        "include_messages": {
                            "type": "boolean",
                            "description": "Include the full message turns of each chat",
                            "default": False
                        }
                    }
                }
            },
            {
                "name": "get_notetaker_chat",
                "description": "Get one AI notetaker chat thread with all of its message turns",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "chat_id": {
                            "type": "string",
                            "description": "Chat ID (full UUID or unique prefix)"
                        },
                        "format": {
                            "type": "string",
                            "description": "Output format",
                            "enum": ["json", "markdown"],
                            "default": "json"
                        }
                    },
                    "required": ["chat_id"]
                }
            },
            {
                "name": "list_calendar_events",
                "description": "List synced calendar events, including any AI pre-read briefing generated before the meeting",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "since": {
                            "type": "string",
                            "description": "Only events starting on/after this date/time"
                        },
                        "until": {
                            "type": "string",
                            "description": "Only events starting on/before this date/time"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of events",
                            "default": 20,
                            "minimum": 1,
                            "maximum": 200
                        },
                        "with_preread_only": {
                            "type": "boolean",
                            "description": "Only events that have a pre-read briefing",
                            "default": False
                        },
                        "include_content": {
                            "type": "boolean",
                            "description": "Include full pre-read content and participant payloads",
                            "default": False
                        }
                    }
                }
            },
            {
                "name": "get_datasource_inventory",
                "description": "Report every table in the Wispr Flow database with its row count and whether this server reads it. Use to detect new datasources after a Wispr Flow update.",
                "inputSchema": {
                    "type": "object",
                    "properties": {}
                }
            }
        ]
    
    def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool and return the result."""
        try:
            if tool_name == "get_recent_transcripts":
                return self._get_recent_transcripts(**arguments)
            elif tool_name == "list_transcripts":
                return self._list_transcripts(**arguments)
            elif tool_name == "search_transcripts":
                return self._search_transcripts(**arguments)
            elif tool_name == "get_transcript":
                return self._get_transcript(**arguments)
            elif tool_name == "get_conversations":
                return self._get_conversations(**arguments)
            elif tool_name == "get_conversation":
                return self._get_conversation(**arguments)
            elif tool_name == "get_app_statistics":
                return self._get_app_statistics(**arguments)
            elif tool_name == "get_database_statistics":
                return self._get_database_statistics(**arguments)
            elif tool_name == "export_transcripts":
                return self._export_transcripts(**arguments)
            elif tool_name == "get_dictionary_entries":
                return self._get_dictionary_entries(**arguments)
            elif tool_name == "list_meetings":
                return self._list_meetings(**arguments)
            elif tool_name == "get_meeting":
                return self._get_meeting(**arguments)
            elif tool_name == "get_meeting_summary":
                return self._get_meeting_summary(**arguments)
            elif tool_name == "get_meeting_transcript":
                return self._get_meeting_transcript(**arguments)
            elif tool_name == "search_meetings":
                return self._search_meetings(**arguments)
            elif tool_name == "list_notes":
                return self._list_notes(**arguments)
            elif tool_name == "get_note":
                return self._get_note(**arguments)
            elif tool_name == "list_todos":
                return self._list_todos(**arguments)
            elif tool_name == "list_notetaker_chats":
                return self._list_notetaker_chats(**arguments)
            elif tool_name == "get_notetaker_chat":
                return self._get_notetaker_chat(**arguments)
            elif tool_name == "list_calendar_events":
                return self._list_calendar_events(**arguments)
            elif tool_name == "get_datasource_inventory":
                return self._get_datasource_inventory(**arguments)
            else:
                return {"error": f"Unknown tool: {tool_name}"}
        except Exception as e:
            return {"error": f"Tool execution failed: {str(e)}"}
    
    def _resolve_app_filter(self, app: Optional[str]) -> Optional[str]:
        """Resolve app name to bundle ID if needed."""
        if not app:
            return None
        
        if "." in app:
            return app
        
        name_to_bundle = {
            "slack": "com.tinyspeck.slackmacgap",
            "obsidian": "md.obsidian",
            "messages": "com.apple.MobileSMS",
            "vscode": "com.microsoft.VSCode",
            "vs code": "com.microsoft.VSCode",
            "chrome": "com.google.Chrome",
            "wispr": "com.electron.wispr-flow",
            "wispr flow": "com.electron.wispr-flow",
            "chatgpt": "com.openai.chat",
            "safari": "com.apple.Safari",
            "mail": "com.apple.mail",
            "notes": "com.apple.Notes",
        }
        
        return name_to_bundle.get(app.lower(), app)
    
    def _get_recent_transcripts(self, limit: int = 10, app: Optional[str] = None, 
                              status: Optional[str] = None, include_archived: bool = False) -> Dict[str, Any]:
        """Get recent transcripts."""
        app_filter = self._resolve_app_filter(app)
        
        entries = self.parser.get_entries(
            limit=limit,
            app=app_filter,
            status=status,
            include_archived=include_archived
        )
        
        return {
            "transcripts": [entry.to_dict() for entry in entries],
            "count": len(entries)
        }
    
    def _list_transcripts(self, since: Optional[str] = None, until: Optional[str] = None,
                         app: Optional[str] = None, status: Optional[str] = None,
                         limit: int = 20, include_archived: bool = False) -> Dict[str, Any]:
        """List transcripts with filters."""
        start_date = DateParser.parse_date(since) if since else None
        end_date = DateParser.parse_date(until) if until else None
        app_filter = self._resolve_app_filter(app)
        
        if since and not start_date:
            return {"error": f"Invalid date format: {since}"}
        if until and not end_date:
            return {"error": f"Invalid date format: {until}"}
        
        entries = self.parser.get_entries(
            limit=limit,
            start_date=start_date,
            end_date=end_date,
            app=app_filter,
            status=status,
            include_archived=include_archived
        )
        
        return {
            "transcripts": [entry.to_dict() for entry in entries],
            "count": len(entries),
            "filters": {
                "since": since,
                "until": until,
                "app": app,
                "status": status
            }
        }
    
    def _search_transcripts(self, query: str, since: Optional[str] = None,
                           until: Optional[str] = None, app: Optional[str] = None,
                           limit: int = 50) -> Dict[str, Any]:
        """Search transcripts."""
        start_date = DateParser.parse_date(since) if since else None
        end_date = DateParser.parse_date(until) if until else None
        app_filter = self._resolve_app_filter(app)
        
        if since and not start_date:
            return {"error": f"Invalid date format: {since}"}
        if until and not end_date:
            return {"error": f"Invalid date format: {until}"}
        
        transcript = self.parser.search_text(
            query,
            limit=limit,
            start_date=start_date,
            end_date=end_date,
            app=app_filter
        )
        
        return {
            "transcripts": [entry.to_dict() for entry in transcript.entries],
            "count": len(transcript.entries),
            "query": query,
            "total_duration": transcript.total_duration,
            "total_words": transcript.total_words
        }
    
    def _get_transcript(self, transcript_id: str, include_context: bool = False) -> Dict[str, Any]:
        """Get specific transcript."""
        entry = self.parser.get_entry_by_id(transcript_id)
        
        if not entry:
            # Try partial ID search
            entries = self.parser.get_entries(limit=1000)
            matches = [e for e in entries if e.transcript_id.startswith(transcript_id)]
            
            if len(matches) == 1:
                entry = matches[0]
            elif len(matches) > 1:
                return {
                    "error": f"Multiple matches found for '{transcript_id}'",
                    "matches": [{"id": m.transcript_id, "app": m.app_name, "text": m.display_text[:50]} for m in matches[:10]]
                }
            else:
                return {"error": f"Transcript not found: {transcript_id}"}
        
        result = entry.to_dict()
        if include_context and entry.additional_context:
            result["additional_context"] = entry.additional_context
        
        return result
    
    def _get_conversations(self, since: Optional[str] = None, until: Optional[str] = None,
                          app: Optional[str] = None, limit: int = 10) -> Dict[str, Any]:
        """Get conversations."""
        start_date = DateParser.parse_date(since) if since else None
        end_date = DateParser.parse_date(until) if until else None
        app_filter = self._resolve_app_filter(app)
        
        if since and not start_date:
            return {"error": f"Invalid date format: {since}"}
        if until and not end_date:
            return {"error": f"Invalid date format: {until}"}
        
        conversations = self.parser.get_conversations(
            limit=limit * 10,  # Get more entries to group into conversations
            start_date=start_date,
            end_date=end_date,
            app=app_filter
        )
        
        # Limit conversations
        conversations = conversations[:limit]
        
        return {
            "conversations": [conv.to_dict() for conv in conversations],
            "count": len(conversations)
        }
    
    def _get_conversation(self, conversation_id: str, format: str = "json") -> Dict[str, Any]:
        """Get specific conversation."""
        conversation = self.parser.get_conversation_by_id(conversation_id)
        
        if not conversation:
            return {"error": f"Conversation not found: {conversation_id}"}
        
        if format == "markdown":
            return {"conversation": conversation.to_markdown()}
        else:
            return conversation.to_dict()
    
    def _get_app_statistics(self, limit: int = 20, sort_by: str = "entries",
                           min_entries: int = 1) -> Dict[str, Any]:
        """Get app statistics."""
        apps = self.parser.get_apps()
        
        # Filter by minimum entries
        apps = [app for app in apps if app["total_entries"] >= min_entries]
        
        # Sort apps
        sort_key_map = {
            "entries": "total_entries",
            "words": "total_words",
            "duration": "total_duration",
            "latency": "avg_latency",
            "last_used": "last_used"
        }
        
        sort_key = sort_key_map.get(sort_by, "total_entries")
        apps.sort(key=lambda x: x[sort_key] or 0, reverse=True)
        
        # Limit results
        apps = apps[:limit]
        
        return {
            "apps": apps,
            "count": len(apps),
            "sort_by": sort_by
        }
    
    def _get_database_statistics(self, since: Optional[str] = None,
                               until: Optional[str] = None, app: Optional[str] = None) -> Dict[str, Any]:
        """Get database statistics."""
        start_date = DateParser.parse_date(since) if since else None
        end_date = DateParser.parse_date(until) if until else None
        app_filter = self._resolve_app_filter(app)
        
        if since and not start_date:
            return {"error": f"Invalid date format: {since}"}
        if until and not end_date:
            return {"error": f"Invalid date format: {until}"}
        
        if start_date or end_date or app_filter:
            # Get filtered statistics
            entries = self.parser.get_entries(
                start_date=start_date,
                end_date=end_date,
                app=app_filter,
                include_archived=True
            )
            
            total_entries = len(entries)
            active_entries = len([e for e in entries if not e.is_archived])
            
            total_duration = sum(e.duration or 0 for e in entries)
            total_words = sum(e.num_words or 0 for e in entries)
            
            valid_entries = [e for e in entries if e.duration is not None and e.num_words is not None]
            avg_duration = sum(e.duration for e in valid_entries) / len(valid_entries) if valid_entries else 0
            avg_words = sum(e.num_words for e in valid_entries) / len(valid_entries) if valid_entries else 0
            
            status_breakdown = {}
            for entry in entries:
                status = entry.status or "unknown"
                status_breakdown[status] = status_breakdown.get(status, 0) + 1
            
            return {
                "total_entries": total_entries,
                "active_entries": active_entries,
                "archived_entries": total_entries - active_entries,
                "total_duration": total_duration,
                "total_words": total_words,
                "avg_duration": avg_duration,
                "avg_words": avg_words,
                "status_breakdown": status_breakdown,
                "filtered": True
            }
        else:
            # Get overall statistics
            return self.parser.get_statistics()
    
    def _export_transcripts(self, format: str = "json", since: Optional[str] = None,
                           until: Optional[str] = None, app: Optional[str] = None,
                           limit: Optional[int] = None, group_by_conversation: bool = False) -> Dict[str, Any]:
        """Export transcripts."""
        start_date = DateParser.parse_date(since) if since else None
        end_date = DateParser.parse_date(until) if until else None
        app_filter = self._resolve_app_filter(app)
        
        if since and not start_date:
            return {"error": f"Invalid date format: {since}"}
        if until and not end_date:
            return {"error": f"Invalid date format: {until}"}
        
        if group_by_conversation:
            conversations = self.parser.get_conversations(
                limit=limit,
                start_date=start_date,
                end_date=end_date,
                app=app_filter
            )
            data = [conv.to_dict() for conv in conversations]
        else:
            entries = self.parser.get_entries(
                limit=limit,
                start_date=start_date,
                end_date=end_date,
                app=app_filter
            )
            data = [entry.to_dict() for entry in entries]
        
        if format == "json":
            export_data = {
                "format": "wispr_mcp_export",
                "version": "1.0",
                "count": len(data),
                "grouped_by_conversation": group_by_conversation,
                "data": data
            }
            return {"export": json.dumps(export_data, indent=2, default=str)}
        else:
            return {"error": f"Format '{format}' not supported in MCP mode. Use 'json' format."}
    
    def _get_dictionary_entries(self) -> Dict[str, Any]:
        """Get dictionary entries."""
        entries = self.parser.get_dictionary_entries()
        
        return {
            "dictionary_entries": entries,
            "count": len(entries)
        }
    
    # ------------------------------------------------------------------
    # Meetings
    # ------------------------------------------------------------------
    
    def _parse_window(self, since: Optional[str], until: Optional[str]):
        """Parse a since/until pair, returning (start, end, error_dict)."""
        start_date = DateParser.parse_date(since) if since else None
        end_date = DateParser.parse_date(until) if until else None
        
        if since and not start_date:
            return None, None, {"error": f"Invalid date format: {since}"}
        if until and not end_date:
            return None, None, {"error": f"Invalid date format: {until}"}
        
        return start_date, end_date, None
    
    def _list_meetings(self, since: Optional[str] = None, until: Optional[str] = None,
                       limit: int = 20, with_summary_only: bool = False,
                       finalized_only: bool = False, include_deleted: bool = False,
                       include_content: bool = False) -> Dict[str, Any]:
        """List meetings."""
        start_date, end_date, error = self._parse_window(since, until)
        if error:
            return error
        
        meetings = self.parser.get_meetings(
            limit=limit,
            start_date=start_date,
            end_date=end_date,
            with_summary_only=with_summary_only,
            finalized_only=finalized_only,
            include_deleted=include_deleted,
            include_related_counts=True,
        )
        
        return {
            "meetings": [
                meeting.to_dict(include_content=include_content)
                for meeting in meetings
            ],
            "count": len(meetings),
            "filters": {
                "since": since,
                "until": until,
                "with_summary_only": with_summary_only,
                "finalized_only": finalized_only,
            },
        }
    
    def _get_meeting(self, meeting_id: str, include_transcript: bool = False,
                     transcript_source: str = "auto",
                     format: str = "json") -> Dict[str, Any]:
        """Get one meeting."""
        meeting = self.parser.get_meeting_by_id(meeting_id)
        if not meeting:
            return {"error": f"Meeting not found: {meeting_id}"}
        
        if format == "markdown":
            markdown = meeting.to_markdown()
            if include_transcript:
                transcript = self.parser.get_meeting_transcript(
                    meeting.meeting_id, source=transcript_source
                )
                if transcript:
                    markdown += "\n\n" + transcript.to_markdown()
            return {"meeting": markdown}
        
        result = meeting.to_dict()
        if include_transcript:
            transcript = self.parser.get_meeting_transcript(
                meeting.meeting_id, source=transcript_source
            )
            result["transcript"] = transcript.to_dict() if transcript else None
        
        return result
    
    def _get_meeting_summary(self, meeting_id: str,
                             raw: bool = False) -> Dict[str, Any]:
        """Get a meeting's AI summary and user notes only."""
        meeting = self.parser.get_meeting_by_id(meeting_id,
                                                include_related_counts=False)
        if not meeting:
            return {"error": f"Meeting not found: {meeting_id}"}
        
        result: Dict[str, Any] = {
            "meeting_id": meeting.meeting_id,
            "title": meeting.title,
            "created_at": meeting.created_at.isoformat() if meeting.created_at else None,
            "duration": meeting.duration,
            "participants": meeting.participants,
            "has_summary": meeting.has_summary,
            "has_notes": meeting.has_notes,
            "refine_status": meeting.refine_status,
            "raw": raw,
        }
        
        if raw:
            # Stored bytes, untouched: no speaker resolution, no duplicate repair.
            # This is the form to use when writing text back into Wispr Flow.
            result["summary"] = meeting.summary
            result["notes"] = meeting.notes
            return result
        
        result["summary"] = meeting.summary_display
        result["notes"] = meeting.notes_display
        result["speaker_tokens_resolved"] = meeting.speaker_tokens_resolved
        result["duplicate_sections_collapsed"] = meeting.duplicate_sections_collapsed
        return result
    
    def _get_meeting_transcript(self, meeting_id: str, source: str = "auto",
                                format: str = "text",
                                apply_corrections: bool = True,
                                max_entries: Optional[int] = None) -> Dict[str, Any]:
        """Get a meeting transcript from disk."""
        meeting = self.parser.get_meeting_by_id(meeting_id,
                                                include_related_counts=False)
        if not meeting:
            return {"error": f"Meeting not found: {meeting_id}"}
        
        transcript = self.parser.get_meeting_transcript(
            meeting.meeting_id,
            source=source,
            apply_corrections=apply_corrections,
        )
        
        if not transcript:
            readable = [
                artifact for artifact in meeting.available_artifacts
                if artifact in ("live", "refined")
            ]
            detail = (
                f"; readable sources for this meeting: {', '.join(readable)}"
                if readable else "; no transcript artifact exists on disk"
            )
            return {
                "error": (
                    f"No '{source}' transcript artifact for meeting "
                    f"{meeting.meeting_id}{detail}"
                ),
                "meeting_id": meeting.meeting_id,
                "title": meeting.title,
                "requested_source": source,
                "available_artifacts": meeting.available_artifacts,
                "readable_sources": readable,
                "transcript_deleted_at": (
                    meeting.transcript_deleted_at.isoformat()
                    if meeting.transcript_deleted_at
                    else None
                ),
            }
        
        header = {
            "meeting_id": meeting.meeting_id,
            "title": meeting.title,
            "source": transcript.source,
            "entry_count": transcript.entry_count,
            "total_words": transcript.total_words,
            "duration": transcript.duration,
            "speakers": transcript.speakers,
            "corrections_applied": transcript.corrections_applied,
        }
        
        if format == "text":
            return {**header, "transcript": transcript.full_text}
        
        if format == "markdown":
            return {
                **header,
                "transcript": f"# {meeting.title or 'Untitled meeting'}\n\n"
                              + transcript.to_markdown(),
            }
        
        payload = transcript.to_dict()
        if max_entries and len(payload.get("entries", [])) > max_entries:
            payload["entries"] = payload["entries"][:max_entries]
            payload["truncated"] = True
            payload["entries_returned"] = max_entries
        
        return {**header, "title": meeting.title, **payload}
    
    def _search_meetings(self, query: str, search_transcripts: bool = False,
                         since: Optional[str] = None, until: Optional[str] = None,
                         limit: int = 20,
                         max_matches_per_meeting: int = 10) -> Dict[str, Any]:
        """Search meetings."""
        start_date, end_date, error = self._parse_window(since, until)
        if error:
            return error
        
        results = self.parser.search_meetings(
            query,
            search_transcripts=search_transcripts,
            limit=limit,
            start_date=start_date,
            end_date=end_date,
        )
        
        return {
            "results": [
                {
                    "meeting": result["meeting"].to_dict(include_content=False),
                    "matched_fields": result["matched_fields"],
                    "transcript_matches": (
                        result["transcript_matches"][:max_matches_per_meeting]
                    ),
                    "transcript_match_count": len(result["transcript_matches"]),
                }
                for result in results
            ],
            "count": len(results),
            "query": query,
            "searched_transcripts": search_transcripts,
        }
    
    # ------------------------------------------------------------------
    # Notes, todos, chats, calendar
    # ------------------------------------------------------------------
    
    def _list_notes(self, since: Optional[str] = None, until: Optional[str] = None,
                    search: Optional[str] = None, pinned_only: bool = False,
                    limit: int = 20, include_content: bool = False,
                    include_deleted: bool = False) -> Dict[str, Any]:
        """List standalone notes."""
        start_date, end_date, error = self._parse_window(since, until)
        if error:
            return error
        
        notes = self.parser.get_notes(
            limit=limit,
            start_date=start_date,
            end_date=end_date,
            search=search,
            pinned_only=pinned_only,
            include_deleted=include_deleted,
        )
        
        return {
            "notes": [note.to_dict(include_content=include_content) for note in notes],
            "count": len(notes),
        }
    
    def _get_note(self, note_id: str, include_versions: bool = False,
                  format: str = "json") -> Dict[str, Any]:
        """Get one note."""
        note = self.parser.get_note_by_id(note_id)
        if not note:
            return {"error": f"Note not found: {note_id}"}
        
        if format == "markdown":
            return {"note": note.to_markdown()}
        
        result = note.to_dict()
        if include_versions:
            versions = self.parser.get_note_versions(note.note_id)
            result["versions"] = [version.to_dict() for version in versions]
        
        return result
    
    def _list_todos(self, meeting_id: Optional[str] = None,
                    status: Optional[str] = None, limit: int = 50,
                    include_archived: bool = False,
                    include_deleted: bool = False) -> Dict[str, Any]:
        """List todos."""
        todos = self.parser.get_todos(
            limit=limit,
            status=status,
            meeting_id=meeting_id,
            include_archived=include_archived,
            include_deleted=include_deleted,
        )
        
        return {
            "todos": [todo.to_dict() for todo in todos],
            "count": len(todos),
            "open_count": len([todo for todo in todos if todo.is_open]),
        }
    
    def _list_notetaker_chats(self, meeting_id: Optional[str] = None,
                              kind: Optional[str] = None, limit: int = 20,
                              include_messages: bool = False) -> Dict[str, Any]:
        """List notetaker chats."""
        chats = self.parser.get_notetaker_chats(
            limit=limit,
            meeting_id=meeting_id,
            kind=kind,
            include_messages=include_messages,
        )
        
        return {
            "chats": [
                chat.to_dict(include_messages=include_messages) for chat in chats
            ],
            "count": len(chats),
        }
    
    def _get_notetaker_chat(self, chat_id: str, format: str = "json") -> Dict[str, Any]:
        """Get one notetaker chat."""
        chat = self.parser.get_notetaker_chat_by_id(chat_id)
        if not chat:
            return {"error": f"Notetaker chat not found: {chat_id}"}
        
        if format == "markdown":
            return {"chat": chat.to_markdown()}
        
        return chat.to_dict()
    
    def _list_calendar_events(self, since: Optional[str] = None,
                              until: Optional[str] = None, limit: int = 20,
                              with_preread_only: bool = False,
                              include_content: bool = False) -> Dict[str, Any]:
        """List calendar events."""
        start_date, end_date, error = self._parse_window(since, until)
        if error:
            return error
        
        events = self.parser.get_calendar_events(
            limit=limit,
            start_date=start_date,
            end_date=end_date,
            with_preread_only=with_preread_only,
        )
        
        return {
            "events": [
                event.to_dict(include_content=include_content) for event in events
            ],
            "count": len(events),
        }
    
    def _get_datasource_inventory(self) -> Dict[str, Any]:
        """Report all tables, row counts, and read coverage."""
        return self.parser.get_datasource_inventory()