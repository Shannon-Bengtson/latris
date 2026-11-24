---
title: CLI and Developer Reference
category: developer
summary: Where the command-line tools fit with the GUI and how to find deeper developer docs.
---

## CLI and GUI share the same core

The GUI talks to a FastAPI server that uses the same operations layer as the `latris` CLI. The CLI remains useful for scripting, inspection, and project maintenance.

## Common CLI flow

```bash
latris init my-project --question "What drives X?"
cd my-project
latris node add "Pressure"
latris node add "Outcome"
latris edge add <source> <target> --kind causal
latris status
latris log
```

## Deeper docs

Use the repository docs for implementation detail:

- `docs/engineering/CLI_REFERENCE.md`
- `docs/engineering/ARCHITECTURE.md`
- `docs/engineering/SCHEMA_NOTES.md`
- `docs/engineering/AI_LAYER.md`
- `docs/engineering/VERSIONING.md`
- `docs/design/DATA_AND_ANALYSIS.md`
- `docs/design/ELICITATION.md`
