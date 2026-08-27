"""
On-disk meeting artifact access for WisprMCP.

Meeting transcripts are NOT in ``flow.sqlite`` -- they are newline-delimited JSON
files next to the database::

    <app support>/Wispr Flow/meetings/<meetingId>/
        live.ndjson      raw diarized utterances captured during recording
        refined.ndjson   server-refined, coalesced utterances (cleaner text)
        upload.ogg       recorded audio

``live.ndjson`` opens with a meta line (``{"meta": {"v": 3, "clock": ...}}``) and
may contain recording markers (``{"marker": "paused", ...}``) interleaved with
utterance lines. ``refined.ndjson`` carries utterances only, with a coarser
shape (no epoch timestamps).

Nothing here writes to disk; the reader is read-only by construction.
"""

import json
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Union

from .meeting import (
    MeetingMarker,
    MeetingTranscript,
    MeetingTranscriptEntry,
    SpeakerMap,
)

LIVE_ARTIFACT = "live.ndjson"
REFINED_ARTIFACT = "refined.ndjson"
AUDIO_ARTIFACT = "upload.ogg"

# Artifact label -> filename. "audio" is listed for availability reporting only;
# WisprMCP never reads or transports the audio bytes.
ARTIFACT_FILES = {
    "live": LIVE_ARTIFACT,
    "refined": REFINED_ARTIFACT,
    "audio": AUDIO_ARTIFACT,
}


class MeetingArtifactStore:
    """Read-only accessor for the per-meeting NDJSON artifact directory."""

    def __init__(self, meetings_dir: Optional[Union[str, Path]] = None):
        if meetings_dir is None:
            from ..utils.config import config

            meetings_dir = config.wispr_meetings_dir
        self.meetings_dir = Path(meetings_dir)

    @property
    def exists(self) -> bool:
        return self.meetings_dir.is_dir()

    def meeting_dir(self, meeting_id: str) -> Path:
        return self.meetings_dir / meeting_id

    def available_artifacts(self, meeting_id: str) -> List[str]:
        """Artifact labels present on disk for a meeting, e.g. ``["live", "audio"]``."""
        directory = self.meeting_dir(meeting_id)
        if not directory.is_dir():
            return []
        return [
            label
            for label, filename in ARTIFACT_FILES.items()
            if (directory / filename).is_file()
        ]

    def available_meeting_ids(self) -> List[str]:
        """Meeting ids that have an artifact directory on disk."""
        if not self.exists:
            return []
        return sorted(
            path.name for path in self.meetings_dir.iterdir() if path.is_dir()
        )

    def artifact_path(self, meeting_id: str, source: str) -> Optional[Path]:
        """Resolve a source label to a file path, honouring ``auto`` preference.

        ``auto`` prefers ``refined`` (cleaner, coalesced text) and falls back to
        ``live``.
        """
        directory = self.meeting_dir(meeting_id)
        if not directory.is_dir():
            return None

        if source == "auto":
            candidates = [REFINED_ARTIFACT, LIVE_ARTIFACT]
        else:
            filename = ARTIFACT_FILES.get(source)
            if not filename or filename == AUDIO_ARTIFACT:
                return None
            candidates = [filename]

        for filename in candidates:
            path = directory / filename
            if path.is_file():
                return path
        return None

    @staticmethod
    def _iter_ndjson(path: Path) -> Iterator[Dict[str, Any]]:
        """Yield parsed objects, skipping blank and malformed lines."""
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    parsed = json.loads(line)
                except json.JSONDecodeError:
                    yield {"__malformed__": True}
                    continue
                if isinstance(parsed, dict):
                    yield parsed

    def load_transcript(
        self,
        meeting_id: str,
        source: str = "auto",
        speaker_map: Optional[SpeakerMap] = None,
        corrections: Optional[Dict[str, str]] = None,
        apply_corrections: bool = True,
    ) -> Optional[MeetingTranscript]:
        """Load a meeting transcript from disk.

        Args:
            meeting_id: Meeting UUID.
            source: ``auto`` (refined then live), ``refined``, or ``live``.
            speaker_map: Speaker map from the ``Meetings`` row, used to turn
                numeric diarization ids into names.
            corrections: ``entryId -> editedText`` from ``TranscriptCorrections``.
            apply_corrections: Substitute corrected text, keeping the original
                on the entry as ``original_text``.

        Returns:
            A ``MeetingTranscript``, or ``None`` when no artifact exists.
        """
        path = self.artifact_path(meeting_id, source)
        if not path:
            return None

        speaker_map = speaker_map or SpeakerMap()
        corrections = corrections or {}

        resolved_source = "refined" if path.name == REFINED_ARTIFACT else "live"
        transcript = MeetingTranscript(
            meeting_id=meeting_id,
            source=resolved_source,
            artifact_path=str(path),
        )

        for record in self._iter_ndjson(path):
            if record.get("__malformed__"):
                transcript.malformed_lines += 1
                continue

            if "meta" in record and "text" not in record:
                meta = record.get("meta")
                transcript.meta = meta if isinstance(meta, dict) else {"meta": meta}
                continue

            if "marker" in record:
                transcript.markers.append(
                    MeetingMarker(
                        marker=str(record.get("marker")),
                        entry_id=record.get("id"),
                        timestamp=record.get("timestamp"),
                        epoch_ms=record.get("epochMs"),
                        segment=record.get("segment"),
                    )
                )
                continue

            if "text" not in record:
                # Unknown line kind: ignore rather than guess at its meaning.
                continue

            entry = self._build_entry(record, speaker_map)

            if apply_corrections and entry.entry_id in corrections:
                corrected = corrections[entry.entry_id]
                if corrected is not None and corrected != entry.text:
                    entry.original_text = entry.text
                    entry.text = corrected
                    transcript.corrections_applied += 1

            transcript.entries.append(entry)

        return transcript

    @staticmethod
    def _build_entry(
        record: Dict[str, Any], speaker_map: SpeakerMap
    ) -> MeetingTranscriptEntry:
        speaker = record.get("speaker")
        speaker_id = None
        speaker_source = None
        embedded_name = None
        if isinstance(speaker, dict):
            speaker_id = speaker.get("id")
            speaker_source = speaker.get("source")
            embedded_name = speaker.get("name")

        return MeetingTranscriptEntry(
            entry_id=str(record.get("id") or ""),
            text=record.get("text") or "",
            timestamp=record.get("timestamp"),
            speaker_id=speaker_id,
            speaker_name=embedded_name or speaker_map.display_name_for(speaker_id),
            speaker_source=speaker_source,
            start_epoch_ms=record.get("startEpochMs"),
            end_epoch_ms=record.get("endEpochMs"),
            start_recording_ms=record.get("startRecordingMs"),
            end_recording_ms=record.get("endRecordingMs"),
            segment=record.get("segment"),
        )

    def artifact_summary(self, meeting_id: str) -> Dict[str, Any]:
        """File-level metadata for a meeting's artifacts (no content read)."""
        directory = self.meeting_dir(meeting_id)
        summary: Dict[str, Any] = {
            "meeting_id": meeting_id,
            "directory": str(directory),
            "exists": directory.is_dir(),
            "artifacts": {},
        }
        if not directory.is_dir():
            return summary

        for label, filename in ARTIFACT_FILES.items():
            path = directory / filename
            if path.is_file():
                summary["artifacts"][label] = {
                    "filename": filename,
                    "size_bytes": path.stat().st_size,
                }
        return summary
