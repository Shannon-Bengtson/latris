# CLI reference

Current command catalogue for the `latris` CLI. The GUI is now the
primary product surface, but the CLI remains the scriptable interface over
the same project format and operations layer.

For exact flags, run:

```bash
latris --help
latris <group> --help
```

## Global

```bash
latris --version
latris --help
latris doctor
latris capabilities [--json]
```

## Project

```bash
latris init <name> [--question "..."]
latris project show
latris project set-question "..."
latris project select-models <model-types>
```

## Substrate: Nodes And Edges

```bash
latris node add <label> [--kind concept|variable|event|actor|state|decision|hazard]
latris node list
latris node show <id>
latris node rename <id> <new-label>
latris node remove <id>

latris edge add <from-id> <to-id> [--kind causal|temporal|decomposition|conditional|informational|flow|support|logical|association]
latris edge list
latris edge remove <id>
```

## Attributes, References, Evidence

```bash
latris attr set <target-id> <attribute> <value>

latris ref add <bibkey> --title "..." --author "..." --year ...
latris ref list
latris ref import <bibfile>

latris evidence add <target-id> <attribute> <bibkey>
```

## Maturity

Maturity is a separate top-level `mature` group (the ladder
proposed → reviewed → approved applies to entities, edges, findings,
mappings, lineage nodes, and milestones). `approve` atomically writes a
`Signoff` row.

```bash
latris mature propose <target-id>
latris mature review <target-id>
latris mature approve <target-id>
```

## Provenance Logs

```bash
latris assumption add "..."
latris decision log "..."
latris signoff record --reviewer "..." --role "..." --scope "..."
latris session record --attendees "..." --notes-file ...
latris question add "..."
latris exclusion add "..."
latris prediction add "..." --horizon ...
```

## Challenges

```bash
latris challenge open <edge-id> "argument..."
latris challenge turn <challenge-id> "..."
latris challenge resolve <challenge-id> --state retained|retained-caveat|modified|split|removed|unresolved
latris challenge list
latris challenge show <challenge-id>
```

## Views, Mappings, Lineage

```bash
latris mapping add <conceptual-id> <view-id> --view cld|dag|conceptual
latris mapping remove <mapping-id>
latris mapping list
latris mapping approve <mapping-id>

latris view project cld|dag|conceptual
latris view auto-project cld|dag|conceptual

latris version milestone "..."
latris version alternative "..."
latris version restore <milestone-id>
latris version switch <version-id>
latris version tree
latris version preferred <version-id>
latris version update <version-id>
```

## Elicitation

```bash
latris elicit start ...
latris elicit round ...
latris elicit aggregate ...
latris elicit finalise ...
latris elicit list
latris elicit show <session-id>
```

The generic elicitation workflow is built. Protocol-specific helpers for
SHELF, Delphi, IDEA, Cooke, AHP, and related methods remain future work.

## Export

```bash
latris export md [--pack client|audit|review|workshop|publication]
latris export word [--pack client|audit|review|workshop|publication]
latris export dot --view cld|dag|conceptual
latris export review [--pack client|audit|review|workshop|publication]
```

Markdown, Word, DOT, and self-contained HTML review-pack exports are
built. PDF export is not yet built.

## Review Import

```bash
latris review import <completed-review.html>
```

Imports structured feedback from a completed review pack and creates the
corresponding challenges, questions, and sign-offs.

## Graph Analysis

```bash
latris analyse loops
latris analyse propagate <variable>
latris analyse d-sep <x> <y> [--given <z1,z2,...>]
latris analyse blanket <variable>
latris analyse paths <from-variable> <to-variable>
latris analyse adjustment-sets <treatment> <outcome>
```

Qualitative computation on the existing stable views. `loops` finds all
feedback loops with R/B classification (CLD polarity). `propagate` traces
qualitative effects of a hypothetical increase. `d-sep` tests d-separation
(conditional independence) given a conditioning set. `blanket` computes
the Markov blanket (parents + children + co-parents). `paths` enumerates
all paths between two variables with node classification
(chain/fork/collider). `adjustment-sets` finds valid adjustment sets via
the backdoor criterion. Variables resolve by ID, label, or prefix.

## FCM (Fuzzy Cognitive Maps)

```bash
latris fcm set-weight <edge> <value>     # set weight in [-1, +1]
latris fcm weights                       # list all edge weights
latris fcm infer [--clamp entity=value]  # run inference to steady state
```

## BN (Bayesian Networks)

The discrete Bayesian Network engine: state spaces + CPTs with per-cell
provenance, exact inference (pgmpy), Noisy-OR canonical models, parameter
learning from data, and sensitivity analysis. Runs are logged as
`AnalysisRun` records in `analysis/runs.jsonl`.

```bash
latris bn set-state-space <node> <states...>   # define a node's discrete states
latris bn set-cpt <node> ...                   # set a conditional probability table cell/column
latris bn set-noisy-or <node> ...              # define a Noisy-OR canonical CPT
latris bn learn <dataset>                      # learn parameters from data (provenance-protecting merge)
latris bn state-spaces                         # list defined state spaces
latris bn cpts                                 # list defined CPTs
latris bn check                                # validate state-space / CPT completeness
latris bn marginals                            # compute prior marginals
latris bn query <node> [--given node=state]    # posterior query under evidence
latris bn sensitivity <target>                 # provenance-aware sensitivity analysis
```

## SD (System Dynamics)

Stock-and-flow models on the shared substrate: SD meaning is a view role,
material moves along `flow` edges (`stock → flow → stock`), and `causal`
edges are information links. Every stock, constant and equation carries
units and per-parameter provenance; `sd check` enforces structure, the
diagram/equation correspondence, and full dimensional consistency.
Simulations are logged as `AnalysisRun` records (`purpose: simulation`).

```bash
latris sd set-role <node> <stock|flow|auxiliary|constant|source_sink>
latris sd set-initial-value <stock> <value> --units <u> [--non-negative]
latris sd set-constant <node> <value> --units <u>
latris sd set-equation <flow|aux> "<expression>" --units <u>   # names = slugified labels; TIME; MIN MAX ABS IF_THEN_ELSE STEP TABLE EXP LN SQRT
latris sd set-table <flow|aux> -p x:y -p x:y ... --x-units <u> --y-units <u> [--extrapolate clamp|linear]
latris sd roles | equations | stocks | constants | tables   # listings
latris sd check                                # readiness incl. dimensional consistency
latris sd simulate [--final-time T] [--dt DT] [--saveper S] [--method euler|rk2|rk4|adaptive] [--json] [--no-record]
```

## Check (coherence)

```bash
latris check coherence    # cross-artefact coherence checks over the project
```

## Completeness

Completeness gating for advancing a model through the workflow.

```bash
latris completeness check                # assess completeness against gate criteria
latris completeness list                 # list gate items + status
latris completeness override <item>      # override a gate item
latris completeness dismiss <item>       # dismiss a gate item
latris completeness mark-added <item>    # mark a flagged gap as addressed
```

## Findings

```bash
latris finding list
latris finding show <finding-id>
latris finding check-stale    # flag findings whose underlying state changed
```

## Interpret

Interpret-phase sections: template claims + AI-generated prose.

```bash
latris interpret initialise            # create section scaffold for the model type
latris interpret list                  # list interpretation sections
latris interpret refresh-claims        # refresh template-derived claims
latris interpret generate-prose <section>  # AI prose for one section
latris interpret generate-all          # AI prose for all sections
```

## Story (Communicate)

Self-contained scrollytelling HTML built from a versioned `Story` object.

```bash
latris story draft                 # scaffold a Story from the current model
latris story list
latris story show <story-id>
latris story generate-prose <beat> # AI prose for one beat (StoryBeatProse)
latris story generate-all          # AI prose for all beats
latris story set-prose <beat> ...  # set beat prose manually
latris story export                # export self-contained HTML
```

## Sync (collaboration)

Turn-based git push/pull through the Latris-native control plane +
invisible Gitea (see [`GIT_INTEGRATION.md`](GIT_INTEGRATION.md) →
"Remote collaboration").

```bash
latris sync login --email you@x.com            # request a one-time code
latris sync login --email you@x.com --code ... # finish signing in
latris sync share "Project name"                # create + push a remote project
latris sync remote      # configure / show the project's sync remote
latris sync push        # push local commits to the shared project
latris sync pull        # pull + integrate remote commits
latris sync fetch       # fetch remote state without integrating
latris sync status      # show local vs remote sync state
```

`login`/`share` are the bridge from a local project to the hosted app
(`https://app.latris.app`) — the only account/collaboration entry point
that previously existed was the desktop GUI's sync panel. `share` prints
the link to open the project in the hosted app once it's pushed.

## Semantic History

```bash
latris status
latris diff [--commits A..B]
latris log
```

## AI

```bash
latris ai prompts list
latris ai prompts show <prompt-name>
latris ai key set <provider>
latris ai key list
latris ai key unset <provider>
latris ai config show
latris ai config set default_model <model>

latris ai call explain <target-id>
latris ai call challenge <edge-id>
latris ai call draft
latris ai call attack
latris ai call scope-check
latris ai call find-connections
latris ai call suggest-citations <target-id> <attribute>
latris ai call peer-review
latris ai call research-gaps
latris ai call steelman
latris ai call project-view

latris ai task emit <prompt-name> --inputs '<json>' [--output task.json]  # self-contained task package for an external agent (no API key)
latris ai task apply --task task.json --from response.json [--actor NAME] [--yes]  # ingest the agent's answer through the standard approval pipeline

latris ai interactions list
latris ai interactions show <interaction-id>
```

All canonical AI operations are wired through structured response models and
the proposal/approval layer. Mutation prompts commit only after human
approval. `ai task emit`/`ai task apply` let an external terminal agent
answer any prompt without an API key — the answer flows through the same
approval pipeline and is attributed to `external-agent[:name]`.
