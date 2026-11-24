# Elicitation sessions in reports: known issue

*Status: **open issue**, found 2026-11-24 while adding tests to the app's Word
exporter. No code change yet: expert elicitation isn't a finished feature,
so nothing depends on this today. Fix it when elicitation is built out.*

## The issue

A recorded elicitation session never appears in a report. The Elicitation
Sessions section always says "None", however many sessions the project has.

`start_session` (`src/latris/operations/elicitation.py`) writes each session
to `provenance/elicitations/<date>-<protocol>-<slug>.yaml` and records its
path in the index, `provenance/elicitations.yaml`, **relative to the project
root**:

```yaml
entries:
  - id: elicitation_01M86HC87HATX12FGT4SFPMQSN
    file_path: provenance/elicitations/2026-03-09-shelf-description.yaml
```

The exporters read the index and join `file_path` onto the **elicitations
folder** instead of the project root, so they look for
`provenance/elicitations/provenance/elicitations/…`, find nothing there, and
skip the session without a word (`if session_path.exists()`):

| Where | Line |
|---|---|
| Markdown report, `src/latris/exporters/markdown.py` (`_load`) | `paths.elicitations_dir / entry.file_path` |
| Word report, in the app: `src/latris_present/exporters/word.py` (`_load`) | `paths.elicitations_dir / entry.file_path` |

`latris elicit` itself reads sessions correctly (`_find_session` uses
`paths.root / entry.file_path`), so the sessions are there; only the reports
miss them.

## The fix

In both exporters, resolve the path against the project root, as
`elicitation.py` does: `paths.root / entry.file_path`. Better, give
`elicitation.py` one function that loads a session from its index entry, and
have the exporters call it, so the path is resolved in one place.

Add a test to each that records a session and finds it in the report. The
app's `tests/latris_present/full_project.py` already records one (SHELF,
facilitated by Ada Field): today its Word test expects the section to be
empty of sessions, so that test changes with the fix.

## Seen alongside it (the app's reports, not latris)

Two smaller things in how challenges are written up, found the same day:

- In the Word report, a challenge about the whole model (no target) reads
  `[open] None: …`; the review pack writes `target: Project`.
- In both the Word report and the review pack, a challenge about a **link**
  shows the link's raw ID (`edge_01M8…`) where a name should be: the labels
  they look targets up in hold nodes only. The Markdown report has the same
  lookup.
