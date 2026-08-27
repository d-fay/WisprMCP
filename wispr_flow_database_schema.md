# Wispr Flow Database Schema

Verified against Wispr Flow on macOS, 2026-08-27 (26 tables, 149 applied Sequelize
migrations). Row counts are omitted deliberately -- they are machine-specific and
drift immediately. Use the `get_datasource_inventory` MCP tool for live counts and
to spot tables this connector does not yet read.

## Storage layout

```
~/Library/Application Support/Wispr Flow/
├── flow.sqlite                      main database (Sequelize/SQLite)
├── flow.sqlite-shm / -wal           WAL sidecars (app may hold these open)
├── backups/                         timestamped automated backups
└── meetings/
    └── <meetingId>/
        ├── live.ndjson              raw diarized utterances (recording time)
        ├── refined.ndjson           server-refined, coalesced utterances
        └── upload.ogg               recorded audio
```

**Meeting transcript text is not in the database.** The `Meetings` row holds the
title, AI summary, user notes, and speaker map; the utterances live in the NDJSON
artifacts above. Anything that renders a meeting transcript must read both.

Connections should be opened read-only (`file:...?mode=ro`) -- the app writes to
this database concurrently and this connector never mutates it.

## Dictation surface

### History
Speech-to-text dictation entries -- the original WisprMCP surface.

Key fields: `transcriptEntityId` (PK), `asrText`, `formattedText`, `editedText`,
`serverFinalizedText`, `timestamp`, `app`, `url`, `duration`, `numWords`, `status`,
`language`, `detectedLanguage`, `conversationId`, `isArchived`, `additionalContext`
(JSON), `averageLogProb`, `e2eLatency`.

Also present: `audio`/`builtInAudio`/`screenshot` BLOBs, fallback-pipeline columns
(`fallbackAsrText`, `usedFallbackAsr`, `fallbackLevel`, divergence scores),
accessibility capture (`axText`, `axHTML`), `toneMatchedText`, `opusChunks`,
`personalizationStyleSettings`, `numDictionaryReplacements`, `editedTextUnbounded`.

### Dictionary
Custom phrases and snippet replacements.

Fields: `id` (PK), `phrase`, `replacement`, `replacementHtml`, `frequencyUsed`,
`remoteFrequencyUsed`, `lastUsed`, `manualEntry`, `source`, `observedSource`,
`isSnippet`, `isStarred`, `teamDictionaryId`, `createdAt`, `modifiedAt`,
`isDeleted`. Unique on (`phrase`, `teamDictionaryId`).

> **Schema drift, load-bearing:** `frequencySeen` and `lastSeen` were documented by
> earlier versions of this file and **no longer exist**. A hardcoded SELECT naming
> them fails with `no such column`. Queries in `parser.py` resolve columns at
> runtime via `PRAGMA table_info` for exactly this reason.

### Polish, InstructHistory, InstructChatSession, FlowLensHistory
Text-transform features (polish/instruct/lens). `Polish` carries
`polishInitialText`, `polishedText`, `instruction`, `promptName`, `modelVersion`,
`diffCount`, `polishUndone`. Not yet surfaced by this connector.

## Meetings surface

### Meetings
One row per recorded meeting.

Identity and lifecycle: `id` (PK), `title`, `createdAt`, `modifiedAt`,
`endedAt` (**epoch ms**), `finalized`, `isDeleted`, `isTourDemo`, `importSource`,
`refineStatus` (`complete` when the server refine pipeline finished),
`refineRetries`, `refineUploadFailureReason`, `transcriptDeletedAt`.

Content:
- `summary` (TEXT) -- **the AI-generated meeting summary, markdown**, stored
  locally. This is the same summary the app shows; it does not require the hosted
  API.
- `notes` (TEXT) -- the user's own "My Thoughts" text.
- `speakerMap` (JSON) -- see below.
- `participantNames` (TEXT) -- often NULL; prefer `speakerMap`.

Sharing and sync: `shareSlug`, `shareVisibility`, `audioUploadedAt`,
`liveTranscriptUploadedAt`, `speakerArtifactUploadedAt`, `serverRefinedUploadedAt`,
`refinedFetchedThroughAt`, and the `*PendingPush` flags.

Calendar link: `calendarEventExternalId`, `calendarOccurrenceStartAtUtc`.

#### speakerMap
Resolves the numeric diarization ids in the NDJSON to people:

```json
{
  "people": {
    "<personId>": {"name": "Dustin Fay", "origin": "self",
                   "platform": null, "participantId": null, "contactId": null}
  },
  "assignments": {
    "1": {"consensus": null, "user": "<personId>",
          "mic": null, "dom": null, "llm": null}
  }
}
```

`assignments` is keyed by the NDJSON `speaker.id`. Resolution precedence is
`consensus` → `user` → `mic` → `dom` → `llm`; unresolved ids fall back to
`Speaker N`. `people` can contain entries with no assignment (a solo recording may
have one `origin: "self"` person and an empty `assignments`).

### MeetingVersions / NoteVersions
Revision history for meeting notes and standalone notes: `content`, `source`,
`transformId`, `transformPrompt`, `createdAt`.

### TranscriptCorrections
User edits to individual meeting transcript entries.

Fields: `id` (PK), `meetingId` (FK, cascade), `entryId` (matches an NDJSON entry
`id`), `originalText`, `editedText`, `artifactRevision`, `artifactDigest`.

`entryId` is pinned to a specific artifact revision, so a correction usually
matches the `refined.ndjson` entry ids rather than `live.ndjson`.

### NDJSON artifact format

`live.ndjson` opens with a meta line, then mixes utterances and markers:

```json
{"meta":{"v":3,"clock":"recording_active_ms"}}
{"id":"0b34b1fc-…","timestamp":"0:01","text":"There's, like, more nuance here.",
 "speaker":{"id":1,"source":"mic","name":null},
 "startEpochMs":1787760388534,"endEpochMs":1787760389614,
 "startRecordingMs":2578,"endRecordingMs":3658,"segment":0}
{"id":"marker-1787761185364-paused","timestamp":"10:19 AM",
 "marker":"paused","epochMs":1787761185364,"segment":0}
```

`refined.ndjson` has no meta line, no epoch fields, and coalesces utterances:

```json
{"id":"022cb3cf-…","timestamp":"00:00",
 "text":"There's, like, more nuance here. There are some endpoints that are more clear.",
 "speaker":{"id":1,"source":"refined","name":null}}
```

Consequences for readers:
- `speaker.name` is always null in practice; names come from `speakerMap`.
- Refined entries carry only a `mm:ss` (or `h:mm:ss`) display offset, so duration
  must be derived from those offsets rather than epoch fields.
- Marker `timestamp` values are wall-clock (`"10:19 AM"`), not offsets.
- Line kinds must be dispatched on shape (`meta` / `marker` / `text`); unknown
  kinds should be skipped, not guessed at.

## Notes, todos, chats, calendar

### Notes
Standalone notes: `id` (PK), `title`, `content`, `contentPreview`,
`searchableContent`, `createdAt`, `modifiedAt`, `pinned`, `finalized`, `synced`,
`isDeleted`.

### NoteImages
Images embedded in notes: `data` (BLOB), `width`, `height`, `sizeBytes`, `s3Key`,
`contentType`, `uploadedToS3`, `presignedGetUrl`, `urlExpiresAt`. This connector
reports image counts only and never reads the BLOBs or the presigned URLs.

### SharedNotes
Notes shared by slug: `slug` (PK), `title`, `notes`, `summary`,
`searchableContent`, `ownerEmail`, `ownerFirstName`, `ownerLastName`,
`ownerAvatarUrl`, `callerRole` (`viewer` by default).

### Todos
Action items: `id` (PK), `meetingId` (nullable, no FK constraint), `title`,
`status` (default `open`), `isDeleted`, `isArchived`, `sortOrder`, `synced`.

### NotetakerChats / NotetakerChatMessages / NotetakerChatAgentStates
AI chat threads about a meeting.

`NotetakerChats`: `id` (PK), `userId`, `kind` (e.g. `meeting_chat`), `meetingId`,
`title` (first user turn, truncated), `uploadState`, `lastAccessedAt`, `deletedAt`,
`shareNote`.

`NotetakerChatMessages`: `id` (PK), `chatId` (FK, cascade), `role`
(`user`/`assistant`), `status` (e.g. `succeeded`), `localOrder`, `serverSequence`,
`turnId`, `content` (JSON), `metadata` (JSON), `feedback` (JSON).

`content` shape -- text lives in a block list, so it must be walked, not read as a
string:

```json
{"type":"message","role":"assistant",
 "content":[{"type":"text","text":"…"}]}
```

`metadata` carries `{"kind":"meeting","model":"gpt-5.6-sol","latency_ms":8355}`.

`NotetakerChatAgentStates` holds the agent `trajectory` (JSON) per chat; not
surfaced by this connector.

### CalendarEvents
Synced calendar entries with AI pre-read briefings.

Fields: `externalId` (PK), `title`, `startAtUtc`/`endAtUtc` (**epoch ms**),
`conferenceUrl`, `status`, `participantNames`, `participants`, `prereadTitle`,
`prereadContent`, `prereadSummary`, `prereadDispatchedAt`, `selfResponseStatus`,
`colorId`, `connectorKey` (default `calendar`), `updatedAt`, `syncedAt`.

## Other tables

| Table | Purpose | Read by connector |
|-------|---------|-------------------|
| `Links` | Copied-URL history with title enrichment | No |
| `Automations` | Automation rules keyed by `entityKind`/`entityId` | No |
| `UserContext` | Writing samples and polish prompts | No |
| `UserVoicePreferences` | Voice/style preferences | No |
| `RemoteNotifications` | In-app notifications from the service | No |
| `GranolaImportRun`, `GranolaTranscriptQueue` | Granola import pipeline | No |
| `SequelizeMeta` | Migration ledger | No (excluded from drift checks) |

## Timestamp formats

Three different conventions coexist -- mixing them silently produces wrong results:

| Form | Example | Where |
|------|---------|-------|
| Text, UTC-suffixed | `2026-08-27 18:00:28.160 +00:00` | `createdAt`, `modifiedAt`, `timestamp`, `deletedAt` |
| Epoch milliseconds | `1787853631865` | `endedAt`, `startAtUtc`, `endAtUtc`, `*EpochMs`, `submitAcceptedAt` |
| Display offset | `"0:01"`, `"00:07"`, `"1:02:33"` | NDJSON `timestamp` |

Two consequences the parser handles explicitly:

1. **Naive/aware mixing.** Epoch-ms values decoded naively and text values decoded
   as UTC-aware cannot be subtracted. All datetimes are normalized to UTC-aware.
2. **Date-bound comparisons.** Text timestamps are space-separated, so comparing
   them against `datetime.isoformat()` (`T`-separated) is not a valid lexicographic
   comparison -- `"T"` sorts above `" "`. Bounds are emitted as
   `%Y-%m-%d %H:%M:%S` so the comparison is a correct prefix compare.

## Sample queries

Meetings that have an AI summary, newest first:

```sql
SELECT id, title, createdAt, refineStatus, length(summary) AS summary_len
FROM Meetings
WHERE (isDeleted = 0 OR isDeleted IS NULL)
  AND summary IS NOT NULL AND TRIM(summary) != ''
ORDER BY createdAt DESC;
```

Chat threads with their meeting title and turn count:

```sql
SELECT c.id, c.title, m.title AS meeting, COUNT(msg.id) AS turns
FROM NotetakerChats c
LEFT JOIN Meetings m ON m.id = c.meetingId
LEFT JOIN NotetakerChatMessages msg ON msg.chatId = c.id
WHERE c.deletedAt IS NULL
GROUP BY c.id
ORDER BY c.lastAccessedAt DESC;
```

Open action items with their source meeting:

```sql
SELECT t.title, t.status, m.title AS meeting
FROM Todos t
LEFT JOIN Meetings m ON m.id = t.meetingId
WHERE t.status = 'open'
  AND (t.isDeleted = 0 OR t.isDeleted IS NULL)
  AND (t.isArchived = 0 OR t.isArchived IS NULL)
ORDER BY t.sortOrder;
```

Dictionary entries (runtime-safe column set):

```sql
SELECT phrase, replacement, frequencyUsed, lastUsed, isSnippet, isStarred
FROM Dictionary
WHERE isDeleted = 0 OR isDeleted IS NULL
ORDER BY frequencyUsed DESC, lastUsed DESC;
```

## Privacy notes

The database holds audio and screenshot BLOBs, accessibility text captured from
whatever app was focused, note images, and presigned S3 URLs. Meeting directories
hold full recorded audio. This connector reads text and metadata only: it never
returns BLOB contents, audio bytes, or presigned URLs, and it reports audio merely
as an availability flag.
