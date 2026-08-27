"""
Notes, todos, notetaker-chat, and calendar data models for WisprMCP.

These cover the non-dictation surfaces Wispr Flow added alongside meetings:

* ``Notes`` / ``NoteVersions`` -- standalone notes and their transform history
* ``Todos`` -- action items, optionally linked to a meeting
* ``NotetakerChats`` / ``NotetakerChatMessages`` -- AI chat threads about a meeting
* ``CalendarEvents`` -- synced calendar entries with pre-read briefings
* ``SharedNotes`` -- notes shared with (or by) other people via a slug
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


def extract_message_text(content: Any) -> str:
    """Pull plain text out of a notetaker chat message ``content`` payload.

    Stored shape is::

        {"type": "message", "role": "user",
         "content": [{"type": "text", "text": "..."}]}

    Unknown block types are skipped rather than guessed at, so a future block
    kind degrades to missing text instead of raising.
    """
    data = content
    if isinstance(data, (str, bytes)):
        try:
            data = json.loads(data)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return str(content)

    if isinstance(data, str):
        return data
    if not isinstance(data, dict):
        return ""

    blocks = data.get("content")
    if isinstance(blocks, str):
        return blocks
    if not isinstance(blocks, list):
        return ""

    parts: List[str] = []
    for block in blocks:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict):
            text = block.get("text")
            if isinstance(text, str) and text:
                parts.append(text)
    return "\n\n".join(parts)


@dataclass
class Note:
    """A standalone note from the ``Notes`` table."""

    note_id: str
    title: Optional[str] = None
    content: Optional[str] = None
    content_preview: Optional[str] = None
    searchable_content: Optional[str] = None
    created_at: Optional[datetime] = None
    modified_at: Optional[datetime] = None
    pinned: bool = False
    finalized: bool = False
    synced: bool = True
    is_deleted: bool = False
    version_count: int = 0
    image_count: int = 0

    @property
    def num_words(self) -> int:
        return len(self.content.split()) if self.content else 0

    def to_dict(self, include_content: bool = True) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "note_id": self.note_id,
            "title": self.title,
            "content_preview": self.content_preview,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "modified_at": self.modified_at.isoformat() if self.modified_at else None,
            "pinned": self.pinned,
            "finalized": self.finalized,
            "synced": self.synced,
            "is_deleted": self.is_deleted,
            "num_words": self.num_words,
            "version_count": self.version_count,
            "image_count": self.image_count,
        }
        if include_content:
            result["content"] = self.content
        return result

    def to_markdown(self) -> str:
        lines = [f"# {self.title or 'Untitled note'}", ""]
        if self.created_at:
            lines.append(f"**Created:** {self.created_at.isoformat()}")
            lines.append("")
        if self.content:
            lines.append(self.content.strip())
        return "\n".join(lines)


@dataclass
class NoteVersion:
    """A prior revision of a note, produced by an AI transform or manual edit."""

    version_id: str
    note_id: str
    content: Optional[str] = None
    source: Optional[str] = None
    transform_id: Optional[str] = None
    transform_prompt: Optional[str] = None
    created_at: Optional[datetime] = None

    def to_dict(self, include_content: bool = True) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "version_id": self.version_id,
            "note_id": self.note_id,
            "source": self.source,
            "transform_id": self.transform_id,
            "transform_prompt": self.transform_prompt,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_content:
            result["content"] = self.content
        return result


@dataclass
class Todo:
    """An action item, optionally tied to a meeting."""

    todo_id: str
    title: Optional[str] = None
    status: Optional[str] = None
    meeting_id: Optional[str] = None
    meeting_title: Optional[str] = None
    created_at: Optional[datetime] = None
    modified_at: Optional[datetime] = None
    is_deleted: bool = False
    is_archived: bool = False
    synced: bool = True
    sort_order: Optional[float] = None

    @property
    def is_open(self) -> bool:
        return (self.status or "open").lower() == "open"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "todo_id": self.todo_id,
            "title": self.title,
            "status": self.status,
            "is_open": self.is_open,
            "meeting_id": self.meeting_id,
            "meeting_title": self.meeting_title,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "modified_at": self.modified_at.isoformat() if self.modified_at else None,
            "is_deleted": self.is_deleted,
            "is_archived": self.is_archived,
            "synced": self.synced,
            "sort_order": self.sort_order,
        }


@dataclass
class NotetakerChatMessage:
    """One turn in an AI notetaker chat thread."""

    message_id: str
    chat_id: str
    role: Optional[str] = None
    status: Optional[str] = None
    text: Optional[str] = None
    local_order: Optional[int] = None
    server_sequence: Optional[int] = None
    turn_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None
    modified_at: Optional[datetime] = None

    @property
    def model(self) -> Optional[str]:
        if isinstance(self.metadata, dict):
            return self.metadata.get("model")
        return None

    @property
    def latency_ms(self) -> Optional[int]:
        if isinstance(self.metadata, dict):
            return self.metadata.get("latency_ms")
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "chat_id": self.chat_id,
            "role": self.role,
            "status": self.status,
            "text": self.text,
            "local_order": self.local_order,
            "server_sequence": self.server_sequence,
            "turn_id": self.turn_id,
            "model": self.model,
            "latency_ms": self.latency_ms,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "modified_at": self.modified_at.isoformat() if self.modified_at else None,
        }


@dataclass
class NotetakerChat:
    """An AI chat thread, usually scoped to one meeting."""

    chat_id: str
    kind: Optional[str] = None
    meeting_id: Optional[str] = None
    meeting_title: Optional[str] = None
    title: Optional[str] = None
    upload_state: Optional[str] = None
    share_note: bool = False
    created_at: Optional[datetime] = None
    modified_at: Optional[datetime] = None
    last_accessed_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
    messages: List[NotetakerChatMessage] = field(default_factory=list)
    message_count: int = 0

    def to_dict(self, include_messages: bool = True) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "chat_id": self.chat_id,
            "kind": self.kind,
            "meeting_id": self.meeting_id,
            "meeting_title": self.meeting_title,
            "title": self.title,
            "upload_state": self.upload_state,
            "share_note": self.share_note,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "modified_at": self.modified_at.isoformat() if self.modified_at else None,
            "last_accessed_at": (
                self.last_accessed_at.isoformat() if self.last_accessed_at else None
            ),
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None,
            "message_count": self.message_count or len(self.messages),
        }
        if include_messages:
            result["messages"] = [message.to_dict() for message in self.messages]
        return result

    def to_markdown(self) -> str:
        lines = [f"# {self.title or 'Notetaker chat'}", ""]
        if self.meeting_title:
            lines.append(f"**Meeting:** {self.meeting_title}")
            lines.append("")
        for message in self.messages:
            role = (message.role or "unknown").title()
            lines.append(f"## {role}")
            lines.append("")
            lines.append(message.text or "")
            lines.append("")
        return "\n".join(lines)


@dataclass
class CalendarEvent:
    """A synced calendar event, including any AI pre-read briefing."""

    external_id: str
    title: Optional[str] = None
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    status: Optional[str] = None
    conference_url: Optional[str] = None
    participant_names: List[str] = field(default_factory=list)
    participants: Optional[Any] = None
    preread_title: Optional[str] = None
    preread_content: Optional[str] = None
    preread_summary: Optional[str] = None
    self_response_status: Optional[str] = None
    connector_key: Optional[str] = None
    updated_at: Optional[str] = None
    synced_at: Optional[str] = None

    @property
    def duration(self) -> Optional[float]:
        if self.start_at and self.end_at:
            return (self.end_at - self.start_at).total_seconds()
        return None

    @property
    def has_preread(self) -> bool:
        return bool(self.preread_content or self.preread_summary)

    def to_dict(self, include_content: bool = True) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "external_id": self.external_id,
            "title": self.title,
            "start_at": self.start_at.isoformat() if self.start_at else None,
            "end_at": self.end_at.isoformat() if self.end_at else None,
            "duration": self.duration,
            "status": self.status,
            "conference_url": self.conference_url,
            "participant_names": self.participant_names,
            "self_response_status": self.self_response_status,
            "connector_key": self.connector_key,
            "has_preread": self.has_preread,
            "updated_at": self.updated_at,
            "synced_at": self.synced_at,
        }
        if include_content:
            result["preread_title"] = self.preread_title
            result["preread_summary"] = self.preread_summary
            result["preread_content"] = self.preread_content
            result["participants"] = self.participants
        return result


@dataclass
class SharedNote:
    """A note shared via slug, with owner metadata and caller role."""

    slug: str
    title: Optional[str] = None
    notes: Optional[str] = None
    summary: Optional[str] = None
    owner_email: Optional[str] = None
    owner_first_name: Optional[str] = None
    owner_last_name: Optional[str] = None
    caller_role: Optional[str] = None
    created_at: Optional[datetime] = None
    modified_at: Optional[datetime] = None

    @property
    def owner_name(self) -> Optional[str]:
        parts = [self.owner_first_name, self.owner_last_name]
        name = " ".join(part for part in parts if part).strip()
        return name or self.owner_email

    def to_dict(self, include_content: bool = True) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "slug": self.slug,
            "title": self.title,
            "owner_name": self.owner_name,
            "owner_email": self.owner_email,
            "caller_role": self.caller_role,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "modified_at": self.modified_at.isoformat() if self.modified_at else None,
        }
        if include_content:
            result["summary"] = self.summary
            result["notes"] = self.notes
        return result


@dataclass
class TranscriptCorrection:
    """A user edit applied to one meeting transcript entry."""

    correction_id: str
    meeting_id: str
    entry_id: str
    original_text: Optional[str] = None
    edited_text: Optional[str] = None
    artifact_revision: Optional[str] = None
    artifact_digest: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "correction_id": self.correction_id,
            "meeting_id": self.meeting_id,
            "entry_id": self.entry_id,
            "original_text": self.original_text,
            "edited_text": self.edited_text,
            "artifact_revision": self.artifact_revision,
            "artifact_digest": self.artifact_digest,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
