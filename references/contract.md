# Evidence Contract v1

## Configuration

Python 3.9+ with system IANA timezone data is required. No package installation,
network, App launch or migrations are needed by the query helper. Installation
configures defaults automatically. To change settings or resume disabled reading,
run from the installed Skill directory:

```sh
python3 scripts/evidence.py setup
```

Setup runs without interaction or an additional approval step; `--yes` remains
accepted for compatibility. It does not open the database. It stores configuration
in `~/Library/Application Support/TimeMuseSkill/consent.json` with mode 0600.
`--database` overrides the standard `~/Library/Application Support/TimeMuse/timemuse.sqlite`;
`--profile` defaults to `local-profile`. The IANA timezone defaults to `TZ`, or
the `/etc/localtime` zoneinfo link. `--timezone Asia/Shanghai` overrides it;
an undetectable timezone needs that override, never a guessed fixed UTC offset.
Default materials are blocks, block_notes, thoughts, reviews, todos and
weekly_contexts. `--types blocks,block_notes` is an optional narrower scope;
activity is opt-in. No choice is required for the default installation.
These settings apply across history, not only a single date range. Host access
controls still apply; the Skill does not introduce its own authorization process.

Use `status` to inspect active material classes/timezone without reading records;
use `revoke` to persist a disabled state. Rerun setup for a deliberate scope change. The
global `--state PATH` option exists for alternate installations and isolated
fixtures, not to bypass the user's selected scope. Revocation takes effect on
subsequent queries, not already returned data or an in-flight read.

## Installation And Maintenance

`python3 scripts/install.py` installs into `${CODEX_HOME:-$HOME/.codex}/skills/timemuse-skill`.
The default command installs and configures reading, including without a terminal.
`--install-only` skips configuration on a fresh install. Existing configuration
is always preserved, including disabled reading and narrower
material selections, even when new install flags differ. Use setup explicitly
to change it. Older installations without configuration receive defaults on
update; legacy consent files remain supported unchanged. No installation path
reads the database.

Repeat the install command to update. Recognized existing installs are backed
up under the client root's `skill-backups/`; `--update` remains accepted for
compatibility. Unrecognized directories and symlinks are left unchanged.
To uninstall, run `revoke`, then remove the installed Skill directory. This does
not delete TimeMuse records. Configuration lives outside the package and must not be
committed or published. Fixture checks: `python3 -m unittest discover -s tests`.

## Read Boundary

The query helper checks configured material classes before opening SQLite.
It opens SQLite `mode=ro`, sets `query_only`, uses a read transaction and never
runs schema migrations. Normal WAL reading is supported; do not use immutable
mode on an active database. SQLite may require accessible WAL/shared-memory
sidecars. There is no raw SQL option. No content cache, telemetry, network,
automatic reports or outgoing message action exists. This is a helper-level
boundary, not OS isolation from other programs that can already read the files.

## Materials

| Type | Projection and authority |
| --- | --- |
| `blocks` | Visible Time Blocks, semantic title/label/status/origin and Project allocation; recorded semantic time, not proof of results |
| `block_notes` | Only metadata `userNote`, user prose linked to Block interval; never transient `note` or nested evidence |
| `thoughts` | Current morning-thought text at its calendar date address |
| `reviews` | Saved Daily Review progress/signal text and provided flags at the review's Evidence Day; not drafts or reconstructed original text |
| `todos` | Current title/note/state and day/week address; intent, even when current state is completed |
| `weekly_contexts` | Current Project goal and time reference at a Monday calendar-week address; intent, not a grade |
| `activity` | App name/bundle, event type and interval only; optional material setting, no window/browser title, URL or metadata |

No screenshots, OCR, Muse conversations, raw title/URL columns, JSON metadata
dump or nested recoverable blocks are returned. User-authored prose can contain
sensitive text or URLs typed by the user; material selection is not automatic
content anonymization. Unsupported materials are enumerated in every response.

## Query Semantics

`--from` and `--to` are required inclusive ISO dates, maximum 93 dates.
`--types` is explicit; `--limit` is 1-200 rows per type (default 40).
`--text` is literal Unicode case-insensitive substring of projected prose/name
fields, maximum 200 characters; it does not search hidden metadata or OCR.
`--project` is an exact current Project name or ID; ambiguous names fail.
Project filtering for thoughts/reviews/activity is explicitly unsupported rather
than guessing a link from prose. Query these separately with a text term when useful.

Blocks and app intervals overlap `[first date 03:00, day after last 03:00)` in
the configured IANA timezone, converted to UTC instants for duration arithmetic.
Closed intervals are clipped. DST days can be 23 or 25 hours. An open interval
is returned only if its start is in range and its duration stays null. No current
time or updated timestamp is substituted for an unknown end.

Calendar-addressed Todo/thought/weekly context dates are not shifted by 03:00.
Week addresses intersect the requested calendar dates. Reviews retain their
saved Evidence Day key. Date assignment does not establish when editable prose
was first written; `updated_at` is only last modification.

Split Block allocation follows current primary/secondary fractions (valid
secondary values clamped to 0.01-0.99); skipped Blocks are omitted. Totals sum
only returned closed Block allocations after filters. They are not whole-range
totals when evidence is truncated, nor deduplicated proof of attention. Activity
and Block durations overlap and must never be added together.

## Output and Failure

Versioned JSON includes `generated_at`, `query`, `items`, per-type `coverage`, `allocation`, and
`limitations`. Each item carries `source_table`, stable `source_id`, profile,
authority, date semantics and applicable modification time. Source IDs are
labels, not app deep links. `mutable: true` disclaims historical snapshots.

Each type scans at most 2,000 time-bounded candidates (recent first), returns
at most its requested limit and clips long top-level strings at 4,000 characters
with `truncated_fields`. Coverage separately reports scan/result/text truncation,
invalid rows and missing/incompatible tables. Literal search occurs before text
clipping, so a matched term can lie past the excerpt. Narrow queries if coverage
is incomplete; never claim exhaustive retrieval.

Errors have a content-free machine code and nonzero exit status; no SQL/path or
record content appears in error messages. Missing source schema fails that type
explicitly. SQLite/open failures fail the whole read. The helper never repairs
the database. Empty results do not certify capture completeness.

## Acceptance Prompts

Evaluate routing with ordinary prompts, not only explicit Skill calls:

- "Help me recall why I changed direction last week." Retrieve scoped prose and
  time facts; identify an inference rather than inventing motive.
- "Draft this week's progress." Keep effort distinct from delivered results.
- "Have I written this idea down before?" Search prose and report scope/gaps.
- "Explain Swift concurrency." Do not read personal evidence.

Fixture checks exercise the helper, not guaranteed model routing or real-user
data quality. No live-database access is part of the implementation test suite.
