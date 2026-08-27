"""
Meeting data models for WisprMCP.

Wispr Flow stores meetings across two locations:

* the ``Meetings`` table in ``flow.sqlite`` (title, AI ``summary``, user ``notes``,
  ``speakerMap``, lifecycle flags), and
* per-meeting NDJSON artifacts on disk under
  ``<app support>/Wispr Flow/meetings/<meetingId>/`` (``live.ndjson``,
  ``refined.ndjson``, ``upload.ogg``).

The transcript text itself is only in the NDJSON artifacts, so a Meeting is
assembled from both sources. See :mod:`wispr_mcp.core.artifacts`.
"""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# Order in which a speakerMap assignment is trusted when resolving a numeric
# diarization speaker id to a person. "consensus" is the app's final answer;
# "user" is a manual label, which we honour ahead of the automatic signals.
SPEAKER_ASSIGNMENT_PRECEDENCE = ("consensus", "user", "mic", "dom", "llm")

# AI summaries reference speakers as "<@speaker:2>".
SPEAKER_TOKEN_RE = re.compile(r"<@speaker:(\d+)>")

# Markdown section heading, e.g. "### Next Steps".
SECTION_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def _repair_glued_headings(text: str) -> Tuple[str, int]:
    """Re-separate a heading that lost its "### " prefix onto the previous line.

    A retried refine-fetch can append a second copy of a section whose heading
    marker is dropped, producing "...reply to invite with deliverablesNext Steps".
    Only titles that also appear as a real heading elsewhere are candidates.
    """
    titles = {
        match.group(2).strip()
        for line in text.split("\n")
        if (match := SECTION_HEADING_RE.match(line))
    }
    if not titles:
        return text, 0

    repairs = 0
    # Longest first so "Next Steps" wins over a hypothetical "Steps".
    for title in sorted(titles, key=len, reverse=True):
        pattern = re.compile(
            r"(?<=\S)(" + re.escape(title) + r")[ \t]*$", re.MULTILINE
        )

        def substitute(match: "re.Match[str]") -> str:
            nonlocal repairs
            repairs += 1
            return "\n\n### " + match.group(1)

        text = pattern.sub(substitute, text)

    return text, repairs


def _collapse_duplicate_sections(text: str) -> Tuple[str, int]:
    """Collapse a section that exactly repeats the section immediately before it.

    Only ADJACENT duplicates are collapsed: a document that legitimately reuses a
    heading later on is left alone. Comparison ignores blank lines and trailing
    whitespace, since the duplicated copy's spacing differs.
    """
    lines = text.split("\n")
    heading_indexes = [
        index for index, line in enumerate(lines) if SECTION_HEADING_RE.match(line)
    ]
    if not heading_indexes:
        return text, 0

    bounds = heading_indexes + [len(lines)]
    preamble = lines[: heading_indexes[0]]
    sections = [lines[start:end] for start, end in zip(bounds, bounds[1:])]

    def signature(section: List[str]) -> List[str]:
        return [line.rstrip() for line in section if line.strip()]

    kept: List[List[str]] = []
    collapsed = 0
    for section in sections:
        if kept and signature(section) == signature(kept[-1]):
            collapsed += 1
            continue
        kept.append(section)

    if not collapsed:
        return text, 0

    rebuilt = preamble + [line for section in kept for line in section]
    return "\n".join(rebuilt), collapsed


def normalize_summary(text: Optional[str]) -> Tuple[Optional[str], int]:
    """Repair duplicated sections in a cached AI summary.

    Wispr Flow's local ``Meetings.summary`` is a cache of a server-refined
    summary, and a retried fetch can leave a section stored twice. The app
    renders the server copy and looks correct, so a reader of the cache -- which
    is what this connector is -- has to repair it or it double-counts action
    items.

    Returns:
        (normalized_text, sections_collapsed).
    """
    if not text:
        return text, 0

    repaired, repairs = _repair_glued_headings(text)
    collapsed, count = _collapse_duplicate_sections(repaired)

    if repairs and count == 0:
        # The speculative heading split unlocked nothing, so don't invent a
        # heading the stored text never had.
        return _collapse_duplicate_sections(text)

    return collapsed, count


@dataclass
class SpeakerMap:
    """Resolves NDJSON numeric speaker ids to human names.

    ``Meetings.speakerMap`` is JSON shaped like::

        {"people": {"<personId>": {"name": "Dustin Fay", "origin": "self", ...}},
         "assignments": {"1": {"consensus": null, "user": "<personId>",
                               "mic": null, "dom": null, "llm": null}}}
    """

    people: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    assignments: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def from_raw(cls, raw: Optional[Any]) -> "SpeakerMap":
        """Build from the raw DB column (JSON string, dict, or None)."""
        if not raw:
            return cls()

        data = raw
        if isinstance(raw, (str, bytes)):
            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, UnicodeDecodeError):
                return cls()

        if not isinstance(data, dict):
            return cls()

        people = data.get("people") or {}
        assignments = data.get("assignments") or {}
        return cls(
            people=people if isinstance(people, dict) else {},
            assignments=assignments if isinstance(assignments, dict) else {},
        )

    def person_id_for(self, speaker_id: Any) -> Optional[str]:
        """Resolve a numeric speaker id to a person id, honouring precedence."""
        if speaker_id is None:
            return None

        assignment = self.assignments.get(str(speaker_id))
        if not isinstance(assignment, dict):
            return None

        for key in SPEAKER_ASSIGNMENT_PRECEDENCE:
            person_id = assignment.get(key)
            if person_id:
                return person_id
        return None

    def name_for(self, speaker_id: Any) -> Optional[str]:
        """Resolve a numeric speaker id to a display name, if one is known."""
        person_id = self.person_id_for(speaker_id)
        if not person_id:
            return None

        person = self.people.get(person_id)
        if isinstance(person, dict):
            name = person.get("name")
            if name:
                return name
        return None

    def display_name_for(self, speaker_id: Any) -> str:
        """Name for a speaker id, falling back to ``Speaker N`` / ``Unknown``."""
        name = self.name_for(speaker_id)
        if name:
            return name
        if speaker_id is None:
            return "Unknown speaker"
        return f"Speaker {speaker_id}"

    @property
    def speaker_names(self) -> List[str]:
        """Names of speakers that have a diarization assignment.

        Falls back to every named person in the map when the meeting has people
        but no assignments yet -- a solo or not-yet-diarized recording still
        knows who was present.
        """
        names: List[str] = []
        for speaker_id in sorted(self.assignments.keys(), key=_sort_key):
            name = self.name_for(speaker_id)
            if name and name not in names:
                names.append(name)

        if names:
            return names

        for person in self.people.values():
            name = (person or {}).get("name") if isinstance(person, dict) else None
            if name and name not in names:
                names.append(name)
        return names

    @property
    def all_people(self) -> List[Dict[str, Any]]:
        """Every person in the map, including ones not assigned to a speaker."""
        assigned = {self.person_id_for(sid) for sid in self.assignments}
        return [
            {
                "person_id": person_id,
                "name": (person or {}).get("name"),
                "origin": (person or {}).get("origin"),
                "assigned": person_id in assigned,
            }
            for person_id, person in self.people.items()
        ]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "speaker_names": self.speaker_names,
            "people": self.all_people,
            "assignments": {
                str(sid): self.display_name_for(sid) for sid in self.assignments
            },
        }

    def resolve_tokens(self, text: Optional[str]) -> Tuple[Optional[str], int]:
        """Replace ``<@speaker:N>`` placeholders with resolved display names.

        Wispr Flow's AI summaries reference speakers by their numeric diarization
        id (``(<@speaker:2>) Go back to Jeff...``), which is unreadable on its own.
        The same speakerMap that names transcript entries resolves them.

        Returns:
            (resolved_text, number_of_substitutions).
        """
        if not text:
            return text, 0

        count = 0

        def substitute(match: "re.Match[str]") -> str:
            nonlocal count
            speaker_id = match.group(1)
            name = self.name_for(speaker_id)
            if not name:
                # Leave an unresolvable token untouched rather than inventing a
                # "Speaker N" that the summary never claimed.
                return match.group(0)
            count += 1
            return name

        resolved = SPEAKER_TOKEN_RE.sub(substitute, text)
        return resolved, count


def _sort_key(value: Any) -> Any:
    """Sort numeric-looking speaker ids numerically, others lexically."""
    try:
        return (0, int(value))
    except (TypeError, ValueError):
        return (1, str(value))


def parse_offset_seconds(timestamp: Optional[str]) -> Optional[float]:
    """Parse an NDJSON display timestamp into seconds from recording start.

    ``live.ndjson`` writes offsets like ``"0:01"`` and ``refined.ndjson`` like
    ``"00:07"`` or ``"1:02:33"``. Wall-clock marker stamps (``"10:19 AM"``) are
    not offsets and return None.
    """
    if not timestamp:
        return None

    text = str(timestamp).strip()
    if not text or any(marker in text.upper() for marker in ("AM", "PM")):
        return None

    parts = text.split(":")
    if len(parts) < 2 or len(parts) > 3:
        return None

    try:
        values = [float(part) for part in parts]
    except ValueError:
        return None

    if len(values) == 2:
        minutes, seconds = values
        return minutes * 60 + seconds
    hours, minutes, seconds = values
    return hours * 3600 + minutes * 60 + seconds


@dataclass
class MeetingTranscriptEntry:
    """A single diarized utterance from a meeting NDJSON artifact."""

    entry_id: str
    text: str
    timestamp: Optional[str] = None  # display offset, e.g. "0:01" or "10:19 AM"
    speaker_id: Optional[Any] = None
    speaker_name: Optional[str] = None
    speaker_source: Optional[str] = None  # "mic", "refined", ...
    start_epoch_ms: Optional[int] = None
    end_epoch_ms: Optional[int] = None
    start_recording_ms: Optional[int] = None
    end_recording_ms: Optional[int] = None
    segment: Optional[int] = None
    original_text: Optional[str] = None  # pre-correction text, when corrected

    @property
    def is_corrected(self) -> bool:
        return self.original_text is not None

    @property
    def start_time(self) -> Optional[datetime]:
        if self.start_epoch_ms is None:
            return None
        return datetime.fromtimestamp(self.start_epoch_ms / 1000, tz=timezone.utc)

    @property
    def offset_seconds(self) -> Optional[float]:
        """Seconds from recording start, from epoch/recording ms or the stamp."""
        if self.start_recording_ms is not None:
            return self.start_recording_ms / 1000
        return parse_offset_seconds(self.timestamp)

    @property
    def duration(self) -> Optional[float]:
        """Utterance duration in seconds, when both bounds are known."""
        if self.start_epoch_ms is not None and self.end_epoch_ms is not None:
            return (self.end_epoch_ms - self.start_epoch_ms) / 1000
        if self.start_recording_ms is not None and self.end_recording_ms is not None:
            return (self.end_recording_ms - self.start_recording_ms) / 1000
        return None

    @property
    def num_words(self) -> int:
        return len(self.text.split()) if self.text else 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "timestamp": self.timestamp,
            "speaker_id": self.speaker_id,
            "speaker_name": self.speaker_name,
            "speaker_source": self.speaker_source,
            "text": self.text,
            "start_epoch_ms": self.start_epoch_ms,
            "end_epoch_ms": self.end_epoch_ms,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "offset_seconds": self.offset_seconds,
            "duration": self.duration,
            "num_words": self.num_words,
            "segment": self.segment,
            "is_corrected": self.is_corrected,
            "original_text": self.original_text,
        }


@dataclass
class MeetingMarker:
    """A recording lifecycle marker (``paused``/``resumed``) in the NDJSON."""

    marker: str
    entry_id: Optional[str] = None
    timestamp: Optional[str] = None
    epoch_ms: Optional[int] = None
    segment: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "marker": self.marker,
            "entry_id": self.entry_id,
            "timestamp": self.timestamp,
            "epoch_ms": self.epoch_ms,
            "segment": self.segment,
        }


@dataclass
class MeetingTranscript:
    """A meeting transcript loaded from one NDJSON artifact."""

    meeting_id: str
    source: str  # "refined" or "live"
    entries: List[MeetingTranscriptEntry] = field(default_factory=list)
    markers: List[MeetingMarker] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)
    corrections_applied: int = 0
    artifact_path: Optional[str] = None
    malformed_lines: int = 0

    @property
    def entry_count(self) -> int:
        return len(self.entries)

    @property
    def total_words(self) -> int:
        return sum(entry.num_words for entry in self.entries)

    @property
    def duration(self) -> Optional[float]:
        """Wall-clock span of the transcript in seconds."""
        starts = [e.start_epoch_ms for e in self.entries if e.start_epoch_ms is not None]
        ends = [e.end_epoch_ms for e in self.entries if e.end_epoch_ms is not None]
        if starts and ends:
            return (max(ends) - min(starts)) / 1000

        rec_starts = [
            e.start_recording_ms for e in self.entries if e.start_recording_ms is not None
        ]
        rec_ends = [
            e.end_recording_ms for e in self.entries if e.end_recording_ms is not None
        ]
        if rec_starts and rec_ends:
            return (max(rec_ends) - min(rec_starts)) / 1000

        # refined.ndjson carries no epoch fields, only display offsets, so the
        # last utterance's start offset is the best available span.
        offsets = [
            offset
            for offset in (e.offset_seconds for e in self.entries)
            if offset is not None
        ]
        if offsets:
            return max(offsets) - min(offsets)
        return None

    @property
    def speakers(self) -> List[str]:
        names: List[str] = []
        for entry in self.entries:
            name = entry.speaker_name or "Unknown speaker"
            if name not in names:
                names.append(name)
        return names

    @property
    def speaker_breakdown(self) -> Dict[str, Dict[str, Any]]:
        """Per-speaker entry/word/duration totals.

        ``duration`` is None rather than 0.0 when the artifact carries no per-entry
        timing -- refined.ndjson has no epoch fields, and a hard zero would read as
        "this speaker talked for no time".
        """
        breakdown: Dict[str, Dict[str, Any]] = {}
        for entry in self.entries:
            name = entry.speaker_name or "Unknown speaker"
            stats = breakdown.setdefault(
                name, {"entries": 0, "words": 0, "duration": None}
            )
            stats["entries"] += 1
            stats["words"] += entry.num_words
            if entry.duration is not None:
                stats["duration"] = (stats["duration"] or 0.0) + entry.duration
        return breakdown

    @property
    def full_text(self) -> str:
        """Speaker-attributed plain text."""
        return "\n".join(
            f"{entry.speaker_name or 'Unknown speaker'}: {entry.text}"
            for entry in self.entries
            if entry.text
        )

    def search_text(self, query: str) -> List[MeetingTranscriptEntry]:
        query_lower = query.lower()
        return [e for e in self.entries if e.text and query_lower in e.text.lower()]

    def to_dict(self, include_entries: bool = True) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "meeting_id": self.meeting_id,
            "source": self.source,
            "artifact_path": self.artifact_path,
            "entry_count": self.entry_count,
            "total_words": self.total_words,
            "duration": self.duration,
            "speakers": self.speakers,
            "speaker_breakdown": self.speaker_breakdown,
            "corrections_applied": self.corrections_applied,
            "meta": self.meta,
        }
        if self.malformed_lines:
            result["malformed_lines"] = self.malformed_lines
        if include_entries:
            result["entries"] = [entry.to_dict() for entry in self.entries]
            result["markers"] = [marker.to_dict() for marker in self.markers]
        return result

    def to_markdown(self) -> str:
        lines = [f"# Meeting transcript ({self.source})", ""]
        if self.duration:
            lines.append(f"**Duration:** {self.duration / 60:.1f} min")
        if self.speakers:
            lines.append(f"**Speakers:** {', '.join(self.speakers)}")
        lines.append("")
        for entry in self.entries:
            stamp = f"[{entry.timestamp}] " if entry.timestamp else ""
            speaker = entry.speaker_name or "Unknown speaker"
            lines.append(f"{stamp}**{speaker}:** {entry.text}")
        return "\n".join(lines)


@dataclass
class Meeting:
    """A meeting row from the ``Meetings`` table, plus artifact availability."""

    meeting_id: str
    title: Optional[str] = None
    created_at: Optional[datetime] = None
    modified_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    summary: Optional[str] = None
    notes: Optional[str] = None
    speaker_map: SpeakerMap = field(default_factory=SpeakerMap)
    participant_names_raw: Optional[str] = None
    finalized: bool = False
    is_deleted: bool = False
    refine_status: Optional[str] = None
    import_source: Optional[str] = None
    share_slug: Optional[str] = None
    share_visibility: Optional[str] = None
    calendar_event_external_id: Optional[str] = None
    transcript_deleted_at: Optional[datetime] = None
    is_tour_demo: bool = False
    available_artifacts: List[str] = field(default_factory=list)
    todo_count: int = 0
    chat_count: int = 0
    correction_count: int = 0

    @property
    def duration(self) -> Optional[float]:
        """Meeting duration in seconds, from creation to end."""
        if self.ended_at and self.created_at:
            delta = (self.ended_at - self.created_at).total_seconds()
            return delta if delta >= 0 else None
        return None

    @property
    def participants(self) -> List[str]:
        """Named speakers, preferring the speakerMap over the raw column."""
        names = self.speaker_map.speaker_names
        if names:
            return names

        raw = self.participant_names_raw
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return [part.strip() for part in str(raw).split(",") if part.strip()]

        if isinstance(parsed, list):
            return [str(item) for item in parsed if item]
        if isinstance(parsed, str):
            return [parsed]
        return []

    @property
    def has_summary(self) -> bool:
        return bool(self.summary and self.summary.strip())

    @property
    def has_notes(self) -> bool:
        return bool(self.notes and self.notes.strip())

    @property
    def summary_display(self) -> Optional[str]:
        """Summary with speaker placeholders resolved and cache duplication repaired."""
        resolved, _ = self.speaker_map.resolve_tokens(self.summary)
        normalized, _ = normalize_summary(resolved)
        return normalized

    @property
    def notes_display(self) -> Optional[str]:
        """Notes with ``<@speaker:N>`` placeholders resolved to names."""
        resolved, _ = self.speaker_map.resolve_tokens(self.notes)
        return resolved

    @property
    def speaker_tokens_resolved(self) -> int:
        """How many speaker placeholders were substituted across summary+notes."""
        _, summary_count = self.speaker_map.resolve_tokens(self.summary)
        _, notes_count = self.speaker_map.resolve_tokens(self.notes)
        return summary_count + notes_count

    @property
    def duplicate_sections_collapsed(self) -> int:
        """Sections removed from the summary because the cached copy repeated them."""
        resolved, _ = self.speaker_map.resolve_tokens(self.summary)
        _, count = normalize_summary(resolved)
        return count

    @property
    def has_transcript(self) -> bool:
        return any(a in ("live", "refined") for a in self.available_artifacts)

    @property
    def has_audio(self) -> bool:
        return "audio" in self.available_artifacts

    def to_dict(self, include_content: bool = True) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "meeting_id": self.meeting_id,
            "title": self.title,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "modified_at": self.modified_at.isoformat() if self.modified_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "duration": self.duration,
            "participants": self.participants,
            "finalized": self.finalized,
            "is_deleted": self.is_deleted,
            "refine_status": self.refine_status,
            "import_source": self.import_source,
            "share_slug": self.share_slug,
            "share_visibility": self.share_visibility,
            "calendar_event_external_id": self.calendar_event_external_id,
            "transcript_deleted_at": (
                self.transcript_deleted_at.isoformat()
                if self.transcript_deleted_at
                else None
            ),
            "is_tour_demo": self.is_tour_demo,
            "has_summary": self.has_summary,
            "has_notes": self.has_notes,
            "has_transcript": self.has_transcript,
            "has_audio": self.has_audio,
            "available_artifacts": self.available_artifacts,
            "todo_count": self.todo_count,
            "chat_count": self.chat_count,
            "correction_count": self.correction_count,
        }
        if include_content:
            result["summary"] = self.summary_display
            result["notes"] = self.notes_display
            result["speaker_tokens_resolved"] = self.speaker_tokens_resolved
            result["duplicate_sections_collapsed"] = self.duplicate_sections_collapsed
            result["speaker_map"] = self.speaker_map.to_dict()
        return result

    def to_markdown(self) -> str:
        lines = [f"# {self.title or 'Untitled meeting'}", ""]
        if self.created_at:
            lines.append(f"**Date:** {self.created_at.isoformat()}")
        if self.duration:
            lines.append(f"**Duration:** {self.duration / 60:.1f} min")
        if self.participants:
            lines.append(f"**Participants:** {', '.join(self.participants)}")
        lines.append("")
        if self.has_summary:
            lines.extend(["## Summary", "", (self.summary_display or "").strip(), ""])
        if self.has_notes:
            lines.extend(["## My Thoughts", "", (self.notes_display or "").strip(), ""])
        return "\n".join(lines)
