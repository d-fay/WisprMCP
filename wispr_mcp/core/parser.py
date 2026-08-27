"""
Database parser for WisprMCP - handles SQLite database access.
"""

import sqlite3
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict, Any, Union
from contextlib import contextmanager

from ..utils.config import config
from .transcript import TranscriptEntry, Transcript
from .conversation import Conversation
from .artifacts import MeetingArtifactStore
from .meeting import Meeting, MeetingTranscript, SpeakerMap
from .notes import (
    CalendarEvent,
    Note,
    NoteVersion,
    NotetakerChat,
    NotetakerChatMessage,
    SharedNote,
    Todo,
    TranscriptCorrection,
    extract_message_text,
)


def _parse_db_datetime(value: Any) -> Optional[datetime]:
    """Parse the datetime formats Wispr Flow writes into SQLite.

    Handles "2026-08-27 18:00:28.160 +00:00", ISO-8601, and plain
    "YYYY-MM-DD HH:MM:SS[.ffffff]". Returns None when unparseable rather than
    raising, so one odd row cannot fail a whole query. Results are always
    timezone-aware UTC: Wispr Flow stores UTC, and mixing naive and aware
    datetimes downstream raises on subtraction.
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return _ensure_utc(value)
    if isinstance(value, (int, float)):
        return _from_epoch_ms(value)

    text = str(value).strip()
    normalized = text.replace(" +00:00", "+00:00").replace(" Z", "Z")
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    try:
        return _ensure_utc(datetime.fromisoformat(normalized))
    except ValueError:
        pass

    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return _ensure_utc(datetime.strptime(text, fmt))
        except ValueError:
            continue
    return None


def _ensure_utc(value: datetime) -> datetime:
    """Treat a naive datetime as UTC; convert an aware one to UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _from_epoch_ms(value: Any) -> Optional[datetime]:
    """Convert epoch milliseconds to a timezone-aware UTC datetime."""
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(float(value) / 1000, tz=timezone.utc)
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def _db_datetime_bound(value: datetime) -> str:
    """Render a filter datetime in the DB's own textual format.

    Wispr Flow stores "2026-08-27 18:00:28.160 +00:00". Comparing that against
    an ISO string ("...T18:00:28") is not a valid lexicographic comparison
    because "T" sorts above " ", so bounds are emitted space-separated and
    second-truncated, which is a correct prefix comparison. A naive input is
    interpreted as local time, matching DateParser's output.
    """
    return _ensure_utc(value).strftime("%Y-%m-%d %H:%M:%S")


def _as_bool(value: Any, default: bool = False) -> bool:
    """Coerce SQLite's TINYINT(1) columns to bool."""
    if value is None:
        return default
    return bool(value)


def _load_json(value: Any) -> Optional[Any]:
    """Parse a JSON column, tolerating already-decoded values and bad JSON."""
    if value is None or value == "":
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
        return None


class WisprParser:
    """Parser for Wispr Flow SQLite database."""
    
    def __init__(self, db_path: Optional[Union[str, Path]] = None,
                 meetings_dir: Optional[Union[str, Path]] = None):
        """
        Initialize the parser.
        
        Args:
            db_path: Path to the SQLite database. If None, uses config default.
            meetings_dir: Path to the per-meeting NDJSON artifact directory.
                If None, uses config default (a sibling of the database).
        """
        self.db_path = Path(db_path) if db_path else config.wispr_database_path
        
        if not self.db_path.exists():
            raise FileNotFoundError(f"Database not found at {self.db_path}")
        
        if meetings_dir is None:
            # Keep artifacts next to whichever database we were pointed at, so a
            # custom --db-path still resolves its own meetings directory.
            meetings_dir = (
                config.wispr_meetings_dir
                if self.db_path == config.wispr_database_path
                else self.db_path.parent / "meetings"
            )
        self.artifacts = MeetingArtifactStore(meetings_dir)
        self._column_cache: Dict[str, set] = {}
        self._table_cache: Optional[set] = None
    
    @contextmanager
    def get_connection(self):
        """Get a database connection with proper cleanup."""
        # Read-only URI: this tool never mutates Wispr Flow's database, and the
        # app may hold it open concurrently.
        conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row  # Enable dict-like access
        try:
            yield conn
        finally:
            conn.close()
    
    def _tables(self, conn: sqlite3.Connection) -> set:
        """Set of table names present in the database (cached)."""
        if self._table_cache is None:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            self._table_cache = {row["name"] for row in cursor.fetchall()}
        return self._table_cache
    
    def has_table(self, table: str) -> bool:
        """Check whether a table exists, for graceful degradation on old apps."""
        with self.get_connection() as conn:
            return table in self._tables(conn)
    
    def _columns(self, conn: sqlite3.Connection, table: str) -> set:
        """Set of column names for a table (cached).
        
        Wispr Flow migrates its schema frequently and has dropped columns that
        earlier versions had, so queries are built against what actually exists
        rather than a hardcoded list.
        """
        if table not in self._column_cache:
            if table not in self._tables(conn):
                self._column_cache[table] = set()
            else:
                cursor = conn.execute(f'PRAGMA table_info("{table}")')
                self._column_cache[table] = {row["name"] for row in cursor.fetchall()}
        return self._column_cache[table]
    
    def _existing_columns(self, conn: sqlite3.Connection, table: str,
                          wanted: List[str]) -> List[str]:
        """Filter a wanted-column list down to those the table actually has."""
        available = self._columns(conn, table)
        return [column for column in wanted if column in available]
    
    @staticmethod
    def _get(row: sqlite3.Row, key: str, default: Any = None) -> Any:
        """Read a column from a row that may not include it."""
        try:
            value = row[key]
        except (IndexError, KeyError):
            return default
        return default if value is None else value
    
    def _row_to_transcript_entry(self, row: sqlite3.Row) -> TranscriptEntry:
        """Convert a database row to a TranscriptEntry object."""
        # Parse timestamp
        timestamp = None
        if row["timestamp"]:
            try:
                # Handle format like "2025-06-20 04:34:15.319 +00:00"
                timestamp_str = row["timestamp"]
                if " +00:00" in timestamp_str:
                    timestamp_str = timestamp_str.replace(" +00:00", "+00:00")
                timestamp = datetime.fromisoformat(timestamp_str)
            except ValueError:
                try:
                    # Try without timezone
                    timestamp = datetime.strptime(row["timestamp"], "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    try:
                        # Try with microseconds
                        timestamp = datetime.strptime(row["timestamp"], "%Y-%m-%d %H:%M:%S.%f")
                    except ValueError:
                        pass
        
        # Parse additional context
        additional_context = None
        if row["additionalContext"]:
            try:
                additional_context = json.loads(row["additionalContext"])
            except json.JSONDecodeError:
                pass
        
        return TranscriptEntry(
            transcript_id=row["transcriptEntityId"],
            asr_text=row["asrText"],
            formatted_text=row["formattedText"],
            edited_text=row["editedText"],
            timestamp=timestamp,
            app=row["app"],
            url=row["url"],
            duration=row["duration"],
            num_words=row["numWords"],
            status=row["status"],
            language=row["language"],
            conversation_id=row["conversationId"],
            e2e_latency=row["e2eLatency"],
            confidence=row["averageLogProb"],
            is_archived=bool(row["isArchived"]) if row["isArchived"] is not None else False,
            additional_context=additional_context,
        )
    
    def get_entries(self, 
                   limit: Optional[int] = None,
                   offset: Optional[int] = None,
                   start_date: Optional[datetime] = None,
                   end_date: Optional[datetime] = None,
                   app: Optional[str] = None,
                   status: Optional[str] = None,
                   conversation_id: Optional[str] = None,
                   include_archived: bool = False) -> List[TranscriptEntry]:
        """
        Get transcript entries from the database.
        
        Args:
            limit: Maximum number of entries to return
            offset: Number of entries to skip
            start_date: Start date filter
            end_date: End date filter
            app: App filter
            status: Status filter
            conversation_id: Conversation ID filter
            include_archived: Whether to include archived entries
            
        Returns:
            List of TranscriptEntry objects
        """
        query = """
        SELECT 
            transcriptEntityId, asrText, formattedText, editedText, 
            timestamp, app, url, duration, numWords, status, language,
            conversationId, e2eLatency, averageLogProb, isArchived, 
            additionalContext
        FROM History
        WHERE 1=1
        """
        params = []
        
        if not include_archived:
            query += " AND (isArchived = 0 OR isArchived IS NULL)"
        
        if start_date:
            query += " AND timestamp >= ? AND timestamp IS NOT NULL"
            params.append(start_date.isoformat())
        
        if end_date:
            query += " AND timestamp <= ? AND timestamp IS NOT NULL"
            params.append(end_date.isoformat())
        
        if app:
            query += " AND app = ?"
            params.append(app)
        
        if status:
            query += " AND status = ?"
            params.append(status)
        
        if conversation_id:
            query += " AND conversationId = ?"
            params.append(conversation_id)
        
        query += " ORDER BY timestamp DESC"
        
        if limit:
            query += " LIMIT ?"
            params.append(limit)
        
        if offset:
            query += " OFFSET ?"
            params.append(offset)
        
        with self.get_connection() as conn:
            cursor = conn.execute(query, params)
            return [self._row_to_transcript_entry(row) for row in cursor.fetchall()]
    
    def get_entry_by_id(self, transcript_id: str) -> Optional[TranscriptEntry]:
        """Get a specific transcript entry by ID."""
        query = """
        SELECT 
            transcriptEntityId, asrText, formattedText, editedText, 
            timestamp, app, url, duration, numWords, status, language,
            conversationId, e2eLatency, averageLogProb, isArchived, 
            additionalContext
        FROM History
        WHERE transcriptEntityId = ?
        """
        
        with self.get_connection() as conn:
            cursor = conn.execute(query, (transcript_id,))
            row = cursor.fetchone()
            return self._row_to_transcript_entry(row) if row else None
    
    def get_transcript(self, **kwargs) -> Transcript:
        """Get a Transcript object containing filtered entries."""
        entries = self.get_entries(**kwargs)
        return Transcript(entries=entries)
    
    def search_text(self, query: str, **kwargs) -> Transcript:
        """Search for text in transcript entries."""
        # Get base entries
        entries = self.get_entries(**kwargs)
        
        # Filter by text search
        query_lower = query.lower()
        filtered_entries = [
            entry for entry in entries 
            if (entry.asr_text and query_lower in entry.asr_text.lower()) or
               (entry.formatted_text and query_lower in entry.formatted_text.lower()) or
               (entry.edited_text and query_lower in entry.edited_text.lower())
        ]
        
        return Transcript(entries=filtered_entries)
    
    def get_conversations(self, **kwargs) -> List[Conversation]:
        """Get conversations (grouped transcript entries)."""
        entries = self.get_entries(**kwargs)
        
        # Group by conversation ID
        conversations_dict = {}
        for entry in entries:
            conv_id = entry.conversation_id or f"single_{entry.transcript_id}"
            if conv_id not in conversations_dict:
                conversations_dict[conv_id] = []
            conversations_dict[conv_id].append(entry)
        
        # Create Conversation objects
        conversations = []
        for conv_id, conv_entries in conversations_dict.items():
            conversation = Conversation(
                conversation_id=conv_id,
                entries=conv_entries
            )
            conversations.append(conversation)
        
        # Sort by start time
        conversations.sort(key=lambda c: c.start_time or datetime.min, reverse=True)
        
        return conversations
    
    def get_conversation_by_id(self, conversation_id: str) -> Optional[Conversation]:
        """Get a specific conversation by ID."""
        entries = self.get_entries(conversation_id=conversation_id)
        if not entries:
            return None
        
        return Conversation(conversation_id=conversation_id, entries=entries)
    
    def get_apps(self) -> List[Dict[str, Any]]:
        """Get list of apps with usage statistics."""
        query = """
        SELECT 
            app,
            COUNT(*) as total_entries,
            SUM(duration) as total_duration,
            SUM(numWords) as total_words,
            AVG(e2eLatency) as avg_latency,
            MAX(timestamp) as last_used
        FROM History
        WHERE app IS NOT NULL AND app != ''
        GROUP BY app
        ORDER BY total_entries DESC
        """
        
        with self.get_connection() as conn:
            cursor = conn.execute(query)
            apps = []
            for row in cursor.fetchall():
                # Get human-readable app name
                app_mappings = {
                    "com.tinyspeck.slackmacgap": "Slack",
                    "md.obsidian": "Obsidian",
                    "com.apple.MobileSMS": "Messages",
                    "com.microsoft.VSCode": "VS Code",
                    "com.google.Chrome": "Chrome",
                    "com.electron.wispr-flow": "Wispr Flow",
                    "com.openai.chat": "ChatGPT",
                    "com.apple.Safari": "Safari",
                    "com.apple.mail": "Mail",
                    "com.apple.Notes": "Notes",
                    "com.apple.TextEdit": "TextEdit",
                }
                
                app_name = app_mappings.get(row["app"], row["app"])
                
                apps.append({
                    "app_id": row["app"],
                    "app_name": app_name,
                    "total_entries": row["total_entries"],
                    "total_duration": row["total_duration"] or 0,
                    "total_words": row["total_words"] or 0,
                    "avg_latency": row["avg_latency"] or 0,
                    "last_used": row["last_used"],
                })
            
            return apps
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get database statistics."""
        with self.get_connection() as conn:
            # Basic counts
            cursor = conn.execute("SELECT COUNT(*) FROM History")
            total_entries = cursor.fetchone()[0]
            
            cursor = conn.execute("SELECT COUNT(*) FROM History WHERE isArchived = 0")
            active_entries = cursor.fetchone()[0]
            
            # Duration and word stats
            cursor = conn.execute("""
                SELECT 
                    SUM(duration) as total_duration,
                    SUM(numWords) as total_words,
                    AVG(duration) as avg_duration,
                    AVG(numWords) as avg_words
                FROM History
                WHERE duration IS NOT NULL AND numWords IS NOT NULL
            """)
            stats_row = cursor.fetchone()
            
            # Status breakdown
            cursor = conn.execute("""
                SELECT status, COUNT(*) as count
                FROM History
                GROUP BY status
                ORDER BY count DESC
            """)
            status_breakdown = {row["status"] or "unknown": row["count"] for row in cursor.fetchall()}
            
            # Date range
            cursor = conn.execute("""
                SELECT MIN(timestamp) as first_entry, MAX(timestamp) as last_entry
                FROM History
                WHERE timestamp IS NOT NULL
            """)
            date_row = cursor.fetchone()
            
            # Counts for the newer surfaces. Each is guarded so an older Wispr
            # Flow database without these tables still returns transcript stats.
            surface_counts: Dict[str, Any] = {}
            surface_tables = {
                "meetings": ("Meetings", "isDeleted"),
                "notes": ("Notes", "isDeleted"),
                "todos": ("Todos", "isDeleted"),
                "notetaker_chats": ("NotetakerChats", None),
                "notetaker_chat_messages": ("NotetakerChatMessages", None),
                "calendar_events": ("CalendarEvents", None),
                "shared_notes": ("SharedNotes", None),
                "transcript_corrections": ("TranscriptCorrections", None),
                "dictionary_entries": ("Dictionary", "isDeleted"),
            }
            for label, (table, deleted_flag) in surface_tables.items():
                if table not in self._tables(conn):
                    continue
                query = f'SELECT COUNT(*) FROM "{table}"'
                if deleted_flag and deleted_flag in self._columns(conn, table):
                    query += f" WHERE {deleted_flag} = 0 OR {deleted_flag} IS NULL"
                surface_counts[label] = conn.execute(query).fetchone()[0]
            
            meeting_dates = {}
            if "Meetings" in self._tables(conn):
                row = conn.execute(
                    "SELECT MIN(createdAt) AS first, MAX(createdAt) AS last "
                    "FROM Meetings WHERE createdAt IS NOT NULL"
                ).fetchone()
                meeting_dates = {
                    "first_meeting": row["first"],
                    "last_meeting": row["last"],
                }
            
            return {
                "total_entries": total_entries,
                "active_entries": active_entries,
                "archived_entries": total_entries - active_entries,
                "total_duration": stats_row["total_duration"] or 0,
                "total_words": stats_row["total_words"] or 0,
                "avg_duration": stats_row["avg_duration"] or 0,
                "avg_words": stats_row["avg_words"] or 0,
                "status_breakdown": status_breakdown,
                "first_entry": date_row["first_entry"],
                "last_entry": date_row["last_entry"],
                "surface_counts": surface_counts,
                **meeting_dates,
                "meetings_with_transcripts": len(
                    self.artifacts.available_meeting_ids()
                ),
                "database_path": str(self.db_path),
                "meetings_dir": str(self.artifacts.meetings_dir),
            }
    
    def get_dictionary_entries(self) -> List[Dict[str, Any]]:
        """Get custom dictionary entries.
        
        Columns are resolved at runtime: Wispr Flow dropped `frequencySeen` and
        `lastSeen` and added `isSnippet`/`isStarred`/`replacementHtml`, so a
        fixed SELECT raises "no such column" on current databases.
        """
        wanted = [
            "id", "phrase", "replacement", "replacementHtml",
            "frequencyUsed", "remoteFrequencyUsed", "frequencySeen",
            "lastUsed", "lastSeen", "manualEntry", "observedSource", "source",
            "isSnippet", "isStarred", "teamDictionaryId",
            "createdAt", "modifiedAt",
        ]
        
        with self.get_connection() as conn:
            columns = self._existing_columns(conn, "Dictionary", wanted)
            if not columns:
                return []
            
            select_list = ", ".join(f'"{column}"' for column in columns)
            query = f"SELECT {select_list} FROM Dictionary"
            
            available = self._columns(conn, "Dictionary")
            if "isDeleted" in available:
                query += " WHERE isDeleted = 0 OR isDeleted IS NULL"
            
            order_terms = []
            if "frequencyUsed" in available:
                order_terms.append("frequencyUsed DESC")
            if "lastUsed" in available:
                order_terms.append("lastUsed DESC")
            if order_terms:
                query += " ORDER BY " + ", ".join(order_terms)
            
            cursor = conn.execute(query)
            return [dict(row) for row in cursor.fetchall()]
    
    # ------------------------------------------------------------------
    # Meetings
    # ------------------------------------------------------------------
    
    MEETING_COLUMNS = [
        "id", "title", "createdAt", "modifiedAt", "endedAt", "summary", "notes",
        "speakerMap", "participantNames", "finalized", "isDeleted", "refineStatus",
        "importSource", "shareSlug", "shareVisibility", "calendarEventExternalId",
        "transcriptDeletedAt", "isTourDemo",
    ]
    
    def _row_to_meeting(self, row: sqlite3.Row,
                        include_artifacts: bool = True) -> Meeting:
        """Convert a Meetings row to a Meeting, adding on-disk artifact state."""
        meeting_id = row["id"]
        
        meeting = Meeting(
            meeting_id=meeting_id,
            title=self._get(row, "title"),
            created_at=_parse_db_datetime(self._get(row, "createdAt")),
            modified_at=_parse_db_datetime(self._get(row, "modifiedAt")),
            ended_at=_from_epoch_ms(self._get(row, "endedAt")),
            summary=self._get(row, "summary"),
            notes=self._get(row, "notes"),
            speaker_map=SpeakerMap.from_raw(self._get(row, "speakerMap")),
            participant_names_raw=self._get(row, "participantNames"),
            finalized=_as_bool(self._get(row, "finalized")),
            is_deleted=_as_bool(self._get(row, "isDeleted")),
            refine_status=self._get(row, "refineStatus"),
            import_source=self._get(row, "importSource"),
            share_slug=self._get(row, "shareSlug"),
            share_visibility=self._get(row, "shareVisibility"),
            calendar_event_external_id=self._get(row, "calendarEventExternalId"),
            transcript_deleted_at=_parse_db_datetime(
                self._get(row, "transcriptDeletedAt")
            ),
            is_tour_demo=_as_bool(self._get(row, "isTourDemo")),
        )
        
        if include_artifacts:
            meeting.available_artifacts = self.artifacts.available_artifacts(meeting_id)
        
        return meeting
    
    def get_meetings(self,
                     limit: Optional[int] = None,
                     offset: Optional[int] = None,
                     start_date: Optional[datetime] = None,
                     end_date: Optional[datetime] = None,
                     include_deleted: bool = False,
                     finalized_only: bool = False,
                     with_summary_only: bool = False,
                     include_related_counts: bool = False) -> List[Meeting]:
        """Get meetings, newest first.
        
        Args:
            limit: Maximum number of meetings to return
            offset: Number of meetings to skip
            start_date: Only meetings created on/after this time
            end_date: Only meetings created on/before this time
            include_deleted: Include soft-deleted meetings
            finalized_only: Only meetings the app has finalized
            with_summary_only: Only meetings that carry an AI summary
            include_related_counts: Also count todos, chats, and corrections
        """
        with self.get_connection() as conn:
            if "Meetings" not in self._tables(conn):
                return []
            
            columns = self._existing_columns(conn, "Meetings", self.MEETING_COLUMNS)
            if not columns:
                return []
            
            select_list = ", ".join(f'"{column}"' for column in columns)
            query = f"SELECT {select_list} FROM Meetings WHERE 1=1"
            params: List[Any] = []
            available = self._columns(conn, "Meetings")
            
            if not include_deleted and "isDeleted" in available:
                query += " AND (isDeleted = 0 OR isDeleted IS NULL)"
            
            if finalized_only and "finalized" in available:
                query += " AND finalized = 1"
            
            if with_summary_only and "summary" in available:
                query += " AND summary IS NOT NULL AND TRIM(summary) != ''"
            
            if start_date and "createdAt" in available:
                query += " AND createdAt >= ?"
                params.append(_db_datetime_bound(start_date))
            
            if end_date and "createdAt" in available:
                query += " AND createdAt <= ?"
                params.append(_db_datetime_bound(end_date))
            
            if "createdAt" in available:
                query += " ORDER BY createdAt DESC"
            
            if limit:
                query += " LIMIT ?"
                params.append(limit)
            
            if offset:
                if not limit:
                    query += " LIMIT -1"
                query += " OFFSET ?"
                params.append(offset)
            
            cursor = conn.execute(query, params)
            meetings = [self._row_to_meeting(row) for row in cursor.fetchall()]
            
            if include_related_counts:
                self._attach_related_counts(conn, meetings)
            
            return meetings
    
    def _attach_related_counts(self, conn: sqlite3.Connection,
                               meetings: List[Meeting]) -> None:
        """Populate todo/chat/correction counts for the given meetings."""
        if not meetings:
            return
        
        ids = [meeting.meeting_id for meeting in meetings]
        placeholders = ", ".join("?" for _ in ids)
        by_id = {meeting.meeting_id: meeting for meeting in meetings}
        
        count_sources = [
            ("Todos", "meetingId", "todo_count", "isDeleted"),
            ("NotetakerChats", "meetingId", "chat_count", None),
            ("TranscriptCorrections", "meetingId", "correction_count", None),
        ]
        
        for table, fk, attribute, deleted_flag in count_sources:
            available = self._columns(conn, table)
            if fk not in available:
                continue
            
            query = (
                f'SELECT "{fk}" AS mid, COUNT(*) AS n FROM "{table}" '
                f'WHERE "{fk}" IN ({placeholders})'
            )
            if deleted_flag and deleted_flag in available:
                query += f' AND ({deleted_flag} = 0 OR {deleted_flag} IS NULL)'
            query += f' GROUP BY "{fk}"'
            
            for row in conn.execute(query, ids).fetchall():
                meeting = by_id.get(row["mid"])
                if meeting:
                    setattr(meeting, attribute, row["n"])
    
    def get_meeting_by_id(self, meeting_id: str,
                          include_related_counts: bool = True) -> Optional[Meeting]:
        """Get a meeting by full id, or by unique id prefix."""
        with self.get_connection() as conn:
            if "Meetings" not in self._tables(conn):
                return None
            
            columns = self._existing_columns(conn, "Meetings", self.MEETING_COLUMNS)
            if not columns:
                return None
            
            select_list = ", ".join(f'"{column}"' for column in columns)
            cursor = conn.execute(
                f"SELECT {select_list} FROM Meetings WHERE id = ?", (meeting_id,)
            )
            row = cursor.fetchone()
            
            if not row:
                cursor = conn.execute(
                    f"SELECT {select_list} FROM Meetings WHERE id LIKE ? LIMIT 2",
                    (f"{meeting_id}%",),
                )
                matches = cursor.fetchall()
                if len(matches) != 1:
                    return None
                row = matches[0]
            
            meeting = self._row_to_meeting(row)
            if include_related_counts:
                self._attach_related_counts(conn, [meeting])
            return meeting
    
    def get_transcript_corrections(
        self, meeting_id: Optional[str] = None
    ) -> List[TranscriptCorrection]:
        """Get user edits made to meeting transcript entries."""
        with self.get_connection() as conn:
            if "TranscriptCorrections" not in self._tables(conn):
                return []
            
            query = (
                "SELECT id, meetingId, entryId, originalText, editedText, "
                "artifactRevision, artifactDigest, createdAt, updatedAt "
                "FROM TranscriptCorrections"
            )
            params: List[Any] = []
            if meeting_id:
                query += " WHERE meetingId = ?"
                params.append(meeting_id)
            
            return [
                TranscriptCorrection(
                    correction_id=row["id"],
                    meeting_id=row["meetingId"],
                    entry_id=row["entryId"],
                    original_text=row["originalText"],
                    edited_text=row["editedText"],
                    artifact_revision=row["artifactRevision"],
                    artifact_digest=row["artifactDigest"],
                    created_at=_parse_db_datetime(row["createdAt"]),
                    updated_at=_parse_db_datetime(row["updatedAt"]),
                )
                for row in conn.execute(query, params).fetchall()
            ]
    
    def get_meeting_transcript(self, meeting_id: str, source: str = "auto",
                               apply_corrections: bool = True
                               ) -> Optional[MeetingTranscript]:
        """Load a meeting's transcript from its on-disk NDJSON artifact.
        
        Args:
            meeting_id: Meeting UUID (full, or a unique prefix)
            source: "auto" (refined, else live), "refined", or "live"
            apply_corrections: Substitute user-corrected text where present
        
        Returns:
            A MeetingTranscript, or None when the meeting or artifact is absent.
        """
        meeting = self.get_meeting_by_id(meeting_id, include_related_counts=False)
        if not meeting:
            return None
        
        corrections: Dict[str, str] = {}
        if apply_corrections:
            corrections = {
                correction.entry_id: correction.edited_text
                for correction in self.get_transcript_corrections(meeting.meeting_id)
                if correction.edited_text is not None
            }
        
        return self.artifacts.load_transcript(
            meeting.meeting_id,
            source=source,
            speaker_map=meeting.speaker_map,
            corrections=corrections,
            apply_corrections=apply_corrections,
        )
    
    def search_meetings(self, query: str,
                        search_transcripts: bool = False,
                        limit: Optional[int] = None,
                        start_date: Optional[datetime] = None,
                        end_date: Optional[datetime] = None,
                        include_deleted: bool = False) -> List[Dict[str, Any]]:
        """Search meeting title, AI summary, and user notes; optionally transcripts.
        
        Transcript search reads NDJSON from disk, so it is opt-in.
        
        Returns:
            A list of {meeting, matched_fields, transcript_matches} dicts.
        """
        query_lower = query.lower()
        
        meetings = self.get_meetings(
            start_date=start_date,
            end_date=end_date,
            include_deleted=include_deleted,
        )
        
        results: List[Dict[str, Any]] = []
        for meeting in meetings:
            matched_fields = []
            if meeting.title and query_lower in meeting.title.lower():
                matched_fields.append("title")
            if meeting.summary and query_lower in meeting.summary.lower():
                matched_fields.append("summary")
            if meeting.notes and query_lower in meeting.notes.lower():
                matched_fields.append("notes")
            
            transcript_matches: List[Dict[str, Any]] = []
            if search_transcripts and meeting.has_transcript:
                transcript = self.get_meeting_transcript(meeting.meeting_id)
                if transcript:
                    hits = transcript.search_text(query)
                    if hits:
                        matched_fields.append("transcript")
                        transcript_matches = [entry.to_dict() for entry in hits]
            
            if matched_fields:
                results.append({
                    "meeting": meeting,
                    "matched_fields": matched_fields,
                    "transcript_matches": transcript_matches,
                })
            
            if limit and len(results) >= limit:
                break
        
        return results
    
    # ------------------------------------------------------------------
    # Notes
    # ------------------------------------------------------------------
    
    def _row_to_note(self, row: sqlite3.Row) -> Note:
        return Note(
            note_id=row["id"],
            title=self._get(row, "title"),
            content=self._get(row, "content"),
            content_preview=self._get(row, "contentPreview"),
            searchable_content=self._get(row, "searchableContent"),
            created_at=_parse_db_datetime(self._get(row, "createdAt")),
            modified_at=_parse_db_datetime(self._get(row, "modifiedAt")),
            pinned=_as_bool(self._get(row, "pinned")),
            finalized=_as_bool(self._get(row, "finalized")),
            synced=_as_bool(self._get(row, "synced"), default=True),
            is_deleted=_as_bool(self._get(row, "isDeleted")),
        )
    
    def get_notes(self, limit: Optional[int] = None, offset: Optional[int] = None,
                  start_date: Optional[datetime] = None,
                  end_date: Optional[datetime] = None,
                  search: Optional[str] = None,
                  pinned_only: bool = False,
                  include_deleted: bool = False) -> List[Note]:
        """Get standalone notes, most recently modified first."""
        with self.get_connection() as conn:
            if "Notes" not in self._tables(conn):
                return []
            
            wanted = [
                "id", "title", "content", "contentPreview", "searchableContent",
                "createdAt", "modifiedAt", "pinned", "finalized", "synced",
                "isDeleted",
            ]
            columns = self._existing_columns(conn, "Notes", wanted)
            if not columns:
                return []
            
            select_list = ", ".join(f'"{column}"' for column in columns)
            query = f"SELECT {select_list} FROM Notes WHERE 1=1"
            params: List[Any] = []
            available = self._columns(conn, "Notes")
            
            if not include_deleted and "isDeleted" in available:
                query += " AND (isDeleted = 0 OR isDeleted IS NULL)"
            if pinned_only and "pinned" in available:
                query += " AND pinned = 1"
            if start_date and "createdAt" in available:
                query += " AND createdAt >= ?"
                params.append(_db_datetime_bound(start_date))
            if end_date and "createdAt" in available:
                query += " AND createdAt <= ?"
                params.append(_db_datetime_bound(end_date))
            
            if search:
                clauses = [f"{column} LIKE ?" for column in
                           ("title", "content", "searchableContent")
                           if column in available]
                if clauses:
                    query += " AND (" + " OR ".join(clauses) + ")"
                    params.extend([f"%{search}%"] * len(clauses))
            
            order_column = "modifiedAt" if "modifiedAt" in available else None
            if order_column:
                query += f" ORDER BY {order_column} DESC"
            
            if limit:
                query += " LIMIT ?"
                params.append(limit)
            if offset:
                if not limit:
                    query += " LIMIT -1"
                query += " OFFSET ?"
                params.append(offset)
            
            notes = [self._row_to_note(row) for row in conn.execute(query, params)]
            self._attach_note_counts(conn, notes)
            return notes
    
    def _attach_note_counts(self, conn: sqlite3.Connection,
                            notes: List[Note]) -> None:
        """Populate version and image counts for the given notes."""
        if not notes:
            return
        
        ids = [note.note_id for note in notes]
        placeholders = ", ".join("?" for _ in ids)
        by_id = {note.note_id: note for note in notes}
        
        for table, attribute in (("NoteVersions", "version_count"),
                                 ("NoteImages", "image_count")):
            if "noteId" not in self._columns(conn, table):
                continue
            rows = conn.execute(
                f'SELECT noteId AS nid, COUNT(*) AS n FROM "{table}" '
                f"WHERE noteId IN ({placeholders}) GROUP BY noteId",
                ids,
            ).fetchall()
            for row in rows:
                note = by_id.get(row["nid"])
                if note:
                    setattr(note, attribute, row["n"])
    
    def get_note_by_id(self, note_id: str) -> Optional[Note]:
        """Get a note by full id, or by unique id prefix."""
        notes = self.get_notes(include_deleted=True)
        for note in notes:
            if note.note_id == note_id:
                return note
        
        matches = [note for note in notes if note.note_id.startswith(note_id)]
        return matches[0] if len(matches) == 1 else None
    
    def get_note_versions(self, note_id: str) -> List[NoteVersion]:
        """Get the transform/edit history for a note, newest first."""
        with self.get_connection() as conn:
            if "NoteVersions" not in self._tables(conn):
                return []
            
            rows = conn.execute(
                "SELECT id, noteId, content, source, transformId, transformPrompt, "
                "createdAt FROM NoteVersions WHERE noteId = ? ORDER BY createdAt DESC",
                (note_id,),
            ).fetchall()
            
            return [
                NoteVersion(
                    version_id=row["id"],
                    note_id=row["noteId"],
                    content=row["content"],
                    source=row["source"],
                    transform_id=row["transformId"],
                    transform_prompt=row["transformPrompt"],
                    created_at=_parse_db_datetime(row["createdAt"]),
                )
                for row in rows
            ]
    
    def get_shared_notes(self, limit: Optional[int] = None) -> List[SharedNote]:
        """Get notes shared by or with the user, newest first."""
        with self.get_connection() as conn:
            if "SharedNotes" not in self._tables(conn):
                return []
            
            query = (
                "SELECT slug, title, notes, summary, ownerEmail, ownerFirstName, "
                "ownerLastName, callerRole, createdAt, modifiedAt "
                "FROM SharedNotes ORDER BY modifiedAt DESC"
            )
            params: List[Any] = []
            if limit:
                query += " LIMIT ?"
                params.append(limit)
            
            return [
                SharedNote(
                    slug=row["slug"],
                    title=row["title"],
                    notes=row["notes"],
                    summary=row["summary"],
                    owner_email=row["ownerEmail"],
                    owner_first_name=row["ownerFirstName"],
                    owner_last_name=row["ownerLastName"],
                    caller_role=row["callerRole"],
                    created_at=_parse_db_datetime(row["createdAt"]),
                    modified_at=_parse_db_datetime(row["modifiedAt"]),
                )
                for row in conn.execute(query, params).fetchall()
            ]
    
    # ------------------------------------------------------------------
    # Todos
    # ------------------------------------------------------------------
    
    def get_todos(self, limit: Optional[int] = None, status: Optional[str] = None,
                  meeting_id: Optional[str] = None,
                  include_archived: bool = False,
                  include_deleted: bool = False) -> List[Todo]:
        """Get action items, optionally scoped to one meeting."""
        with self.get_connection() as conn:
            if "Todos" not in self._tables(conn):
                return []
            
            available = self._columns(conn, "Todos")
            has_meetings = "Meetings" in self._tables(conn)
            
            select_list = (
                't.id, t.meetingId, t.title, t.status, t.isDeleted, t.isArchived, '
                't.createdAt, t.modifiedAt, t.synced, t.sortOrder'
            )
            if has_meetings:
                query = (
                    f"SELECT {select_list}, m.title AS meetingTitle FROM Todos t "
                    "LEFT JOIN Meetings m ON m.id = t.meetingId WHERE 1=1"
                )
            else:
                query = f"SELECT {select_list} FROM Todos t WHERE 1=1"
            
            params: List[Any] = []
            if not include_deleted and "isDeleted" in available:
                query += " AND (t.isDeleted = 0 OR t.isDeleted IS NULL)"
            if not include_archived and "isArchived" in available:
                query += " AND (t.isArchived = 0 OR t.isArchived IS NULL)"
            if status:
                query += " AND t.status = ?"
                params.append(status)
            if meeting_id:
                query += " AND t.meetingId = ?"
                params.append(meeting_id)
            
            query += " ORDER BY t.sortOrder ASC, t.createdAt DESC"
            if limit:
                query += " LIMIT ?"
                params.append(limit)
            
            return [
                Todo(
                    todo_id=row["id"],
                    meeting_id=self._get(row, "meetingId"),
                    meeting_title=self._get(row, "meetingTitle"),
                    title=self._get(row, "title"),
                    status=self._get(row, "status"),
                    is_deleted=_as_bool(self._get(row, "isDeleted")),
                    is_archived=_as_bool(self._get(row, "isArchived")),
                    synced=_as_bool(self._get(row, "synced"), default=True),
                    sort_order=self._get(row, "sortOrder"),
                    created_at=_parse_db_datetime(self._get(row, "createdAt")),
                    modified_at=_parse_db_datetime(self._get(row, "modifiedAt")),
                )
                for row in conn.execute(query, params).fetchall()
            ]
    
    # ------------------------------------------------------------------
    # Notetaker chats
    # ------------------------------------------------------------------
    
    def get_notetaker_chats(self, limit: Optional[int] = None,
                            meeting_id: Optional[str] = None,
                            kind: Optional[str] = None,
                            include_messages: bool = False,
                            include_deleted: bool = False) -> List[NotetakerChat]:
        """Get AI notetaker chat threads, most recently accessed first."""
        with self.get_connection() as conn:
            if "NotetakerChats" not in self._tables(conn):
                return []
            
            has_meetings = "Meetings" in self._tables(conn)
            select_list = (
                "c.id, c.kind, c.meetingId, c.title, c.uploadState, c.shareNote, "
                "c.createdAt, c.modifiedAt, c.lastAccessedAt, c.deletedAt"
            )
            if has_meetings:
                query = (
                    f"SELECT {select_list}, m.title AS meetingTitle "
                    "FROM NotetakerChats c "
                    "LEFT JOIN Meetings m ON m.id = c.meetingId WHERE 1=1"
                )
            else:
                query = f"SELECT {select_list} FROM NotetakerChats c WHERE 1=1"
            
            params: List[Any] = []
            if not include_deleted:
                query += " AND c.deletedAt IS NULL"
            if meeting_id:
                query += " AND c.meetingId = ?"
                params.append(meeting_id)
            if kind:
                query += " AND c.kind = ?"
                params.append(kind)
            
            query += " ORDER BY c.lastAccessedAt DESC"
            if limit:
                query += " LIMIT ?"
                params.append(limit)
            
            chats = [
                NotetakerChat(
                    chat_id=row["id"],
                    kind=self._get(row, "kind"),
                    meeting_id=self._get(row, "meetingId"),
                    meeting_title=self._get(row, "meetingTitle"),
                    title=self._get(row, "title"),
                    upload_state=self._get(row, "uploadState"),
                    share_note=_as_bool(self._get(row, "shareNote")),
                    created_at=_parse_db_datetime(self._get(row, "createdAt")),
                    modified_at=_parse_db_datetime(self._get(row, "modifiedAt")),
                    last_accessed_at=_parse_db_datetime(
                        self._get(row, "lastAccessedAt")
                    ),
                    deleted_at=_parse_db_datetime(self._get(row, "deletedAt")),
                )
                for row in conn.execute(query, params).fetchall()
            ]
            
            if not chats:
                return chats
            
            if "NotetakerChatMessages" in self._tables(conn):
                ids = [chat.chat_id for chat in chats]
                placeholders = ", ".join("?" for _ in ids)
                by_id = {chat.chat_id: chat for chat in chats}
                
                counts = conn.execute(
                    "SELECT chatId, COUNT(*) AS n FROM NotetakerChatMessages "
                    f"WHERE chatId IN ({placeholders}) GROUP BY chatId",
                    ids,
                ).fetchall()
                for row in counts:
                    chat = by_id.get(row["chatId"])
                    if chat:
                        chat.message_count = row["n"]
                
                if include_messages:
                    for chat in chats:
                        chat.messages = self.get_notetaker_chat_messages(chat.chat_id)
            
            return chats
    
    def get_notetaker_chat_messages(self, chat_id: str
                                    ) -> List[NotetakerChatMessage]:
        """Get the turns of one notetaker chat, in conversation order."""
        with self.get_connection() as conn:
            if "NotetakerChatMessages" not in self._tables(conn):
                return []
            
            rows = conn.execute(
                "SELECT id, chatId, role, status, content, metadata, turnId, "
                "localOrder, serverSequence, createdAt, modifiedAt "
                "FROM NotetakerChatMessages WHERE chatId = ? "
                "ORDER BY localOrder ASC, createdAt ASC",
                (chat_id,),
            ).fetchall()
            
            return [
                NotetakerChatMessage(
                    message_id=row["id"],
                    chat_id=row["chatId"],
                    role=row["role"],
                    status=row["status"],
                    text=extract_message_text(row["content"]),
                    local_order=row["localOrder"],
                    server_sequence=row["serverSequence"],
                    turn_id=row["turnId"],
                    metadata=_load_json(row["metadata"]),
                    created_at=_parse_db_datetime(row["createdAt"]),
                    modified_at=_parse_db_datetime(row["modifiedAt"]),
                )
                for row in rows
            ]
    
    def get_notetaker_chat_by_id(self, chat_id: str,
                                 include_messages: bool = True
                                 ) -> Optional[NotetakerChat]:
        """Get one notetaker chat by full id or unique id prefix."""
        chats = self.get_notetaker_chats(include_deleted=True)
        match = next((chat for chat in chats if chat.chat_id == chat_id), None)
        
        if not match:
            prefixed = [chat for chat in chats if chat.chat_id.startswith(chat_id)]
            if len(prefixed) != 1:
                return None
            match = prefixed[0]
        
        if include_messages:
            match.messages = self.get_notetaker_chat_messages(match.chat_id)
        return match
    
    # ------------------------------------------------------------------
    # Calendar
    # ------------------------------------------------------------------
    
    def get_calendar_events(self, limit: Optional[int] = None,
                            start_date: Optional[datetime] = None,
                            end_date: Optional[datetime] = None,
                            with_preread_only: bool = False
                            ) -> List[CalendarEvent]:
        """Get synced calendar events, soonest-first by start time."""
        with self.get_connection() as conn:
            if "CalendarEvents" not in self._tables(conn):
                return []
            
            wanted = [
                "externalId", "title", "startAtUtc", "endAtUtc", "conferenceUrl",
                "status", "updatedAt", "syncedAt", "prereadTitle", "prereadContent",
                "prereadSummary", "participantNames", "participants", "colorId",
                "selfResponseStatus", "connectorKey",
            ]
            columns = self._existing_columns(conn, "CalendarEvents", wanted)
            if not columns:
                return []
            
            select_list = ", ".join(f'"{column}"' for column in columns)
            query = f"SELECT {select_list} FROM CalendarEvents WHERE 1=1"
            params: List[Any] = []
            
            # startAtUtc / endAtUtc are epoch milliseconds.
            if start_date:
                query += " AND startAtUtc >= ?"
                params.append(int(start_date.timestamp() * 1000))
            if end_date:
                query += " AND startAtUtc <= ?"
                params.append(int(end_date.timestamp() * 1000))
            if with_preread_only:
                query += (
                    " AND (prereadContent IS NOT NULL OR prereadSummary IS NOT NULL)"
                )
            
            query += " ORDER BY startAtUtc DESC"
            if limit:
                query += " LIMIT ?"
                params.append(limit)
            
            events = []
            for row in conn.execute(query, params).fetchall():
                names = _load_json(self._get(row, "participantNames"))
                if isinstance(names, str):
                    names = [names]
                elif not isinstance(names, list):
                    raw_names = self._get(row, "participantNames")
                    names = (
                        [part.strip() for part in str(raw_names).split(",") if part.strip()]
                        if raw_names
                        else []
                    )
                
                events.append(CalendarEvent(
                    external_id=row["externalId"],
                    title=self._get(row, "title"),
                    start_at=_from_epoch_ms(self._get(row, "startAtUtc")),
                    end_at=_from_epoch_ms(self._get(row, "endAtUtc")),
                    status=self._get(row, "status"),
                    conference_url=self._get(row, "conferenceUrl"),
                    participant_names=[str(name) for name in names],
                    participants=_load_json(self._get(row, "participants")),
                    preread_title=self._get(row, "prereadTitle"),
                    preread_content=self._get(row, "prereadContent"),
                    preread_summary=self._get(row, "prereadSummary"),
                    self_response_status=self._get(row, "selfResponseStatus"),
                    connector_key=self._get(row, "connectorKey"),
                    updated_at=self._get(row, "updatedAt"),
                    synced_at=self._get(row, "syncedAt"),
                ))
            
            return events
    
    # ------------------------------------------------------------------
    # Inventory
    # ------------------------------------------------------------------
    
    def get_datasource_inventory(self) -> Dict[str, Any]:
        """Report every table, its row count, and whether WisprMCP reads it.
        
        Use this to detect schema drift after a Wispr Flow update: a populated
        table marked as unsupported is a new datasource worth wiring up.
        """
        supported = {
            "History": "transcripts",
            "Dictionary": "dictionary",
            "Meetings": "meetings",
            "MeetingVersions": "meetings",
            "TranscriptCorrections": "meetings",
            "Notes": "notes",
            "NoteVersions": "notes",
            "NoteImages": "notes",
            "SharedNotes": "notes",
            "Todos": "todos",
            "NotetakerChats": "notetaker_chats",
            "NotetakerChatMessages": "notetaker_chats",
            "CalendarEvents": "calendar",
        }
        
        with self.get_connection() as conn:
            tables = sorted(self._tables(conn))
            inventory = []
            for table in tables:
                if table.startswith("sqlite_"):
                    continue
                try:
                    count = conn.execute(
                        f'SELECT COUNT(*) FROM "{table}"'
                    ).fetchone()[0]
                except sqlite3.Error:
                    count = None
                
                inventory.append({
                    "table": table,
                    "row_count": count,
                    "supported": table in supported,
                    "surface": supported.get(table),
                    "column_count": len(self._columns(conn, table)),
                })
            
            unsupported_with_data = [
                item["table"] for item in inventory
                if not item["supported"] and (item["row_count"] or 0) > 0
                and item["table"] != "SequelizeMeta"
            ]
            
            return {
                "database_path": str(self.db_path),
                "meetings_dir": str(self.artifacts.meetings_dir),
                "meetings_dir_exists": self.artifacts.exists,
                "artifact_meeting_ids": self.artifacts.available_meeting_ids(),
                "tables": inventory,
                "table_count": len(inventory),
                "unsupported_tables_with_data": unsupported_with_data,
            }
