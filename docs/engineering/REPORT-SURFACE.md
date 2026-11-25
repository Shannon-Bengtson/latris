# Report surface: how models reach the report

Status: agreed direction (2026-11-17), implementation in progress.
Tracking: latris#5 (charts hook), latris#4 (aggregate diagrams), latris#3
(legacy migration); app half: latris-app#3.

## The split

Reports have two surfaces, and the boundary between them is deliberate:

- **The library (this repo) owns the contract.** The Markdown report
  (`exporters/markdown.py`), the Mermaid sketch (`exporters/mermaid.py`),
  recorded results (`exporters/results.py`), interpretation claims, the
  methods registry (`operations/foundations.py`), and the `latris-chart`
  markers that name a run and a chart kind. Everything here is plain text
  and renders anywhere.
- **The app (`latris-app`, `latris_present`) owns the glossy surface.** The
  typeset SVG figure (`figure/`), the SVG chart renderers (`charts/`), both
  dispatched per model type through `presenters/` (one module per type),
  the hosted report page and the Word export. Anything that isn't Markdown
  or Mermaid happens there, reached through the share link — the link is
  the hook that brings the reader into the app.

The rule this doc enforces: **the approach CLD has always had — backend
contract, app-side picture — applies to every formalism**, and every
formalism, old or new, declares its report surface through the plugin
registry (`operations/formalisms/`), not through branches in shared code.

## What a formalism declares for the report

| Hook | Where it lands |
|---|---|
| `ResultKind.render` | Results section tables (Markdown) |
| `ResultKind.charts` | `latris-chart` markers → app SVG charts |
| `ResultKind.claims` | Interpretation sections from recorded runs |
| `Formalism.claims` | Interpretation sections from the live model |
| `Formalism.mermaid` / `mermaid_groups` | The diagram in the Markdown report |
| foundations registry entry | Methods and foundations section |
| `Formalism.spec_export` | What travels inside the share link |

Chart kinds are namespaced per formalism (`mcda-swing`, not generic
`tornado`) so each app-side renderer owns its contract. Unknown kinds
degrade to the table — backend and app can ship in either order.

## Charts

`ResultKind.charts(payload) -> list[(chart_kind, extra)]` replaces the
hardcoded `_charts` switch in `exporters/results.py`. The legacy sd/bn
mapping stays in `_charts` until those types migrate (see below), then
moves into their plugins.

Markers per result kind:

| Result kind | Charts |
|---|---|
| `mcda-analysis` | `mcda-contributions` (stacked bars), `mcda-swing` (weight-reversal tornado) |
| `ach-analysis` | `ach-matrix` (hypothesis × evidence grid) |
| `dt-analysis` | `dt-ev` (expected-value bars) |
| `markov-analysis` | `markov-trace` (state occupancy per cycle), `markov-ce` (cost-effectiveness plane) |
| `toc-impact` | `impact-its` (observed / fitted / counterfactual) or `impact-did` (before/after slopes) |
| `dag-estimate` | `estimate-forest` (adjusted vs unadjusted CI) |
| `toc-process-trace` | `trace-dumbbell` (prior → posterior per link) |
| `ft-analysis` | `ft-importance` |
| `et-analysis` | `et-endstates` |
| `ft/bt/et-monte-carlo` | `mc-strip` (percentile strips) |

Markov and ITS payloads already record the series these charts need; no
payload changes for them.

Each `ResultKind` with a `charts` hook also **declares** `chart_kinds` —
every kind the hook may emit — and `needs_dataset` when the run reads a
dataset. Registration refuses a `charts` hook without `chart_kinds`, and
`tests/testing/test_examples.py` checks the declaration against what the
`latris.testing` example projects actually emit, both ways. `analysis_results.result_surfaces()` lists every kind, all from the registry
(SD's included, since it became a plugin).

## The contract apps test against

The app doesn't copy lists or payloads from here:

- **`latris capabilities --surface`** (`build_surface_manifest()`): per
  stable model type, whether it's a plugin, its outcome role, its
  build-spec block and that block's JSON schema, its CLI group, and its
  result kinds with their analysis, chart kinds and `needs_dataset`.
  `manifest_version` changes only when a key is removed or changes meaning.
- **`latris.testing`**: one example project per model type, shipped in the
  wheel (`examples/*.json` build specs plus small CSVs).
  `build_example(name, root)` builds one; `example_payloads(workdir)`
  builds all and returns every recorded payload by result kind. Together
  they record every result kind (tested), so the app can render each one
  against the pinned release instead of copies that drift.
- **`exporters.markdown.diagram_sections(paths, model_type=None)`**: what
  each diagram in the report's Diagram section draws (model type, or
  `WHOLE_MODEL`, and its `###` heading), in order. `render` composes the
  section from the same function, so a surface that draws its own figure
  per diagram (hosted page, Word, review pack) shows exactly the report's
  diagrams.

## The aggregate report

`latris export md` with no `--model-type` renders the whole project. Its
diagram section composes **one subsection per used formalism** (selected in
`project.yaml` or with mapped view members), each drawn by that formalism's
Mermaid hook, in model-type-registry order, with per-type loop legends
where they apply. The whole-substrate sketch is kept only when edges exist
outside every used view (an unmapped node alone draws as an unconnected
box, which tells the reader nothing). The share link under the diagram
stays project-wide.

## Migrating the legacy five

CLD, DAG, FCM, BN and SD predate the registry; their report surface is
special-cased (`interpret.py` branches, `_TITLES`, `_charts`,
`result_claims.py` dispatch, the generic Mermaid sketch). One PR per type,
ordered **bn → sd → cld/dag/fcm**, moves each into
`operations/formalisms/`:

- result kinds registered as `ResultKind`s — **kind strings unchanged**, so
  recorded runs, staleness and share links keep working;
- claims moved out of `interpret.py` / `result_claims.py`;
- spec hooks around the existing `SpecBN` / `SpecSD` blocks (FCM gains a
  weights block);
- proper Mermaid hooks: BN shows states, observed evidence and the target
  (numbers stay in Results); SD shows stocks/flows with polarity; CLD keeps
  the polarity sketch, now owned by its plugin.

After each migration the hardcoded lists shrink: `KIND_ORDER` /
`KIND_MODEL_TYPE` derive from the registry alone, and
`tests/operations/test_formalisms.py::LEGACY` empties — the full-wiring
guard then covers every stable type.

Watch points: `build.py` (sd outcome special-case), `handover.py`,
`share_link.py`, `ai/context/`, `view_roles.py`, `REPORT_LIMIT` for
`bn-query`, and `tests/latris_present/test_figure.py` in the app (the
Mermaid/figure loop-numbering agreement).

## Out of scope (for now)

- DOT views beyond `system_map` / `cld` / `dag`.
- Interactive diagram semantics in the gui canvas (unchanged — the figure
  registry reuses its layout data).
