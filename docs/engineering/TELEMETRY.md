# Telemetry

What the `latris` library records about how it is used, where it goes, and
how to switch it off. The short version: events stay in a local file in your
project unless you (or whoever hosts the server you use) turn upload on, and
they never contain model content, prompt text or project data.

## What is recorded

Each event is one `TelemetryEvent` (`src/latris/schema/events.py`):

```
TelemetryEvent
  id            str          # evt_…
  at            datetime     # UTC
  surface       "cli" | "gui" | "mcp" | "server" | "broker" | "ci"
  event_type    str          # e.g. "ai.call.completed"
  type_version  int          # payload schema version for this event type
  actor_ref     str | None   # pseudonymous id, or None
  project_id    str | None
  session_id    str | None
  payload       dict         # validated against the registry entry
```

Every payload is checked against a registry of event types
(`register_event_type`, the same pattern as `ai.registry.register_prompt`);
an unknown type or a malformed payload is dropped, never written. The
registered types are:

| Event type | Payload | Emitted by |
|---|---|---|
| `ai.call.completed` | interaction id, prompt name, model id, adoption (pending / approved / rejected / failed), latency, token usage, cost, the rejection reason (a category plus the person's optional note) if one was given, error class | the library, when an AI call finishes (any surface) |
| `gui.feature` | a feature key and an action (opened / started / completed / abandoned), optional dwell time | a GUI, through the server's relay route |
| `session.lifecycle` | start / end, duration, event count | a GUI, through the relay |
| `mcp.tool`, `project.lifecycle`, `error.observed`, `ai.proposal.outcome` | tool name and outcome; project created / saved / shared / archived; error class and location; whether an applied proposal was later edited or reverted | registered for hosted services that use the same envelope; the library itself doesn't emit them |
| `cli.command` | registered, not emitted: the CLI sends no usage events | — |

Never recorded: prompt or response text, factor names, model values,
evidence, file contents or arguments to commands. Errors carry a class and a
location, not a traceback.

## Where it goes

- **Locally, always (unless switched off):** appended to
  `.graph-tooling/telemetry.jsonl` in the project. `latris init` adds it to
  the project's `.gitignore`: behavioural data doesn't belong in a model's
  shared history, so it is never committed.
- **Uploaded, only when turned on**, as a POST of `{"events": [...]}` to an
  ingest URL. Upload is off by default and nothing leaves the machine until
  one of these is set:
  - the project opts in, in `.graph-tooling/telemetry.yaml`:

    ```yaml
    enabled: true          # the local file (default true)
    upload_enabled: true   # opt in to upload (default false)
    endpoint_url: https://example.org/v1/events
    ```

  - or the environment, for whoever runs the server for others (a hosted
    deployment sets these on each session; an end user's own install sets
    none of them): `LATRIS_TELEMETRY_ENDPOINT` (turns upload on),
    `LATRIS_TELEMETRY_TOKEN` (sent as `Authorization: Bearer`; a secret, so
    an environment variable, never the committed config) and
    `LATRIS_TELEMETRY_ACTOR` (the pseudonymous `actor_ref` for events that
    carry none).

A failed upload drops the remote copy, never the local event, and never
breaks the command or request that produced it.

## The GUI relay

The server accepts batches from a GUI at `POST /api/telemetry/events`
(`src/latris/server/routes/telemetry.py`). It stamps `surface="gui"`,
validates every payload against the registry (one bad payload rejects the
batch) and writes them through the same emitter, so the same switches apply.
A server that predates the route answers 404, which a GUI should take as
"telemetry off".

## Switching it off

Set `enabled: false` in the project's `.graph-tooling/telemetry.yaml`. That
stops the local file and any upload, whatever the environment says.

## Extending it

A new feature registers its event type and payload model with
`register_event_type(name, version, model)` in `latris.schema.events`;
the envelope doesn't change. Bump the version when a payload's shape does.
