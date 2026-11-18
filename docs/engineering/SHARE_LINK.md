# Share links (`latris link`): known issue and fix

*Status: **open issue**, found 2026-11-15. No code change yet. The goal is a
link that is a faithful copy of the model, or one that says plainly what it
left behind.*

## The issue

A `latris link` copy of a model can say things about its evidence that the
copy itself contradicts.

`export_spec` in `src/latris/operations/share_link.py` packs the project as a
build spec. It keeps the model's free text and drops the evidence record that
text describes:

| Carried in the link | Dropped |
|---|---|
| Interpretation prose, verbatim | Source checks: verdict, who checked, source access, quote, quote location, quote verified |
| Finding statements and details | Source extracts (the text quotes are looked up in) |
| Citations (which source on which attribute, for or against) | Finding maturity: approved and reviewed findings arrive as proposed |
| Open challenges | Resolved challenges and their outcomes |
| | Sign-offs and the git history |

On import (`latris build --spec`, or the app opening `/open#…`), the prose is
written fresh, so the "prose out of date" mechanism (`interpret
refresh-claims`, the `stale` flag) doesn't fire. Nothing compares what the
prose says about the evidence with what the record holds.

**Seen in practice.** The river-health example on latris.app was shared as a
`latris link`. Its Evidence coverage section said every supporting citation
had been "checked against the text Latris holds, each with the checked quote on
record", and its Confidence section said each high-confidence link was
"checked against a government source with the quote on record". In the copy
the link opened, all 12 citations were unchecked and all 4 findings
unapproved. The report contradicted itself on the one thing Latris exists to
get right, and a reviewer clicking an arrow would have seen it.

Two weaknesses combine:

1. **The link is lossy.** It drops the evidence trail but keeps the
   conclusions drawn from it.
2. **Prose isn't checked against the record.** Interpretation prose and
   finding details are free text. They can assert checks, quotes or
   approvals the data doesn't hold, from a link or from an AI writing
   interpretation directly. `write_interpretation` asks the writer to stick
   to the claims; nothing enforces it.

## Fix: make the link a proper copy

The main fix is a lossless link. The rest makes sure that whatever can't be
carried is never silently claimed.

1. **Carry the evidence trail.** Add to the payload (bump `PAYLOAD_VERSION`)
   each evidence link's check (verdict, by, source access, quote, quote
   location), each source's extract and extract kind, finding maturity,
   resolved challenges with their outcome, and sign-offs. Schema first:
   extend `BuildSpec` and round-trip-test it before `share_link.py` or
   `build` use the new fields.
2. **Don't trust what arrives.** Anyone can hand-craft a link. On import:
   - look every quote up again in the carried extract, and drop the check
     (back to unchecked) if it isn't found;
   - label carried checks as *carried over from the original model*, not as
     checked by whoever opened the link, and say so in the report;
   - never import an approval or sign-off as one: record "approved in the
     original" for a person to confirm.
3. **Mark prose stale when its evidence changed.** Carry with each
   interpretation section a fingerprint of the facts it was written against
   (citations checked, findings approved, open challenges; the inputs to its
   claims). On import, recompute it. If it differs, mark the section stale so
   the report, `interpret list` and `check handover` say it was written
   against a different version. This also catches any future path that
   changes evidence under existing prose.
4. **Flag prose that claims more than the record.** A `check handover` (and
   connector `check_model`) warning when a section's prose or a finding's
   detail uses verification language ("checked against", "verified", "quote
   on record", "approved", "signed off") while the matching counts are lower.
   It's a heuristic, so a warning rather than a block. It also covers AI-written
   prose in general.
5. **Print the numbers next to the prose.** In Evidence coverage and Confidence,
   the report shows the computed figures (for example "0 of 12 citations
   checked") beside the prose, so a reader sees the record even when the
   prose is wrong.
6. **Size.** Extracts can be up to 4,000 characters each, so links get longer.
   `MAX_PAYLOAD_BYTES` stays the limit; past it, `latris link` should say what
   it left out and point to `latris sync share` instead of dropping it silently.

**Tests.** A round-trip test: build a model with checks, extracts, approved
findings, a resolved challenge and interpretation prose; `latris link`; rebuild
from the link; assert that the trail survives with the labels above, or that
the affected prose is marked stale. Add the round trip to the worked example.

**Beyond this repo.** The app's `/open` import and the connector server (both
in the private app repo) need the same treatment: re-verify carried quotes,
label carried checks, never import approvals, and run the same prose checks.

## Results and model types in a link (built)

A link carries the model, not its results: opening it re-runs every
analysis the sender's report shows (`analysis_replay.definitions`, stale
ones left out), so the numbers are computed, never pasted.

Analyses that read a dataset (`needs_dataset` on the result kind: effect
estimation, impact estimation) can't be re-run, because links don't carry
data. Rather than show less than the sender's report, the link carries
those results as the sender's (`BuildSpec.carried_results`,
`operations/carried_results.py`): the recorded payload with factor and link
ids written as labels, the datasets it read (name and content hash), and
its summary. The build records it in the opened project marked as carried,
and the report says it was computed by the sender from that data and can't
be re-run there. It ages like any result when the model changes, and
re-sharing the opened model carries it again.

`LinkPayload.model_types` lists every model type the project uses when
there is more than one (a bow-tie with its event trees), so the opened model
selects them all. Single-type links leave it empty and stay as they were.

## Until it's fixed

- Treat a `latris link` copy as unchecked. Re-check sources in the copy, or
  share the original with `latris sync share` and `latris sync link on`, which
  shares the project itself rather than a copy.
- Don't publish a link copy whose prose mentions checks or approvals.
