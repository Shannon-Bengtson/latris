# Replications

Textbook models rebuilt in Latris, each with the numbers it must reproduce. One folder per model:

- `spec.json`: the model as a build spec (`latris build --spec` reads it), citing the original work.
- `replication.yaml`: what it is, where it comes from, and its checks (schema: `latris/schema/replication.py`).

`latris replicate check` builds each model, runs its analyses and compares the results with the expected
values; `latris replicate build <id> <folder>` gives you the project to inspect. The test suite runs every
check, and recomputes each `exact` and `closed_form` value independently of Latris.

A check's `basis` says where its expected value comes from (`published`, `closed_form` or `exact`), and
`checked` whether a person has compared it with the original. Add a model: a new folder here, then the
independent recomputation of its values in `tests/operations/test_replications.py`.
