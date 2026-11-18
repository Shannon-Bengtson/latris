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
latris capabilities --surface [-m TYPE]           # surface manifest for apps: spec blocks, result and chart kinds per type
latris foundations [--json]                      # the methods registry behind the report's Methods and foundations section
latris docs [agents|readme|llms|foundations]     # the guide, from the installed package
latris --json <group> <command> ...
```

`--json` (before the command group) makes supported commands print one
JSON object instead of rich text: `{"result": ..., "commit_sha": ...}` for
mutations (the server routes' shape) and `{"result": [...]}` for listings.
Errors print `{"error": ..., "type": ...}` with the usual exit codes (1 for
not-found / git / sync errors, 2 for invalid input). Supported today:
`node add|list|show|rename|remove`, `edge add|list|remove`, `attr set`,
`view set|role`, `ref add|list`, `evidence add|check`, `check coherence|handover|integrity`, `build`, `init`, `docs`,
`analyse loops|propagate|paths|d-sep|blanket|adjustment-sets`, `interpret initialise|list|show|set-prose`,
`bn` (setters, `state-spaces`, `cpts`, `check`, `marginals`, `query`, `sensitivity`), `sd` (setters, listings,
`check`, `simulate` — a compact summary; its own `--json` still prints the full series) and `fcm`
(`set-weight`, `weights`, `infer`). In JSON mode `bn check` and `sd check` report `ready` and exit 0.

`latris foundations` prints the methods-and-foundations registry — the same
registry that generates the report's Methods and foundations section and the
capability manifest's `foundations` block, so the three cannot drift apart.
Each entry names the method, its citation, what Latris uses it for, and its
stated limits; `--json` emits the raw list. `latris docs foundations` prints
the prose companion (docs/FOUNDATIONS.md, bundled in the wheel).

## Project

```bash
latris init <name> [--question "..."]
latris project show
latris project set-question "..."
latris project select-models <model-types>
latris build --spec model.yaml [--verified-by human|ai]   # '-' reads stdin
```

`build` adds a whole model from one YAML or JSON spec — `factors` (label,
kind, description, sources, contradicts), `links` (from, to, kind, polarity,
reason, weight, description, confidence, sources, contradicts), `sources` (key, title, authors,
year, container, doi, url, notes), `assumptions` (text, or text + target +
rationale), `questions`, `findings` (statement, category, detail, targets;
recorded as proposed), `challenges` (argument, target), `interpretation`
(section, prose, by), `decisions` (statement, rationale, target), `outcome`
and an optional `model_type` — as **one commit**. Links and citations refer to
factors by label and to sources by key, from the spec or already in the
project. The whole spec is checked first and nothing changes if anything
fails to resolve. Field names match the hosted MCP server's
`apply_changes` operations. See `src/latris/schema/build_spec.py`.

## Substrate: Nodes And Edges

```bash
latris node add <label> [--kind concept|variable|event|actor|state|decision|hazard]
latris node list
latris node show <id>
latris node rename <id> <new-label>      # labels are unique (case-insensitive)
latris node remove <id>                  # also removes its links and every row about them

latris edge add <from-id> <to-id> [--kind causal|temporal|decomposition|conditional|informational|flow|support|logical|association]
latris edge list
latris edge remove <id>
```

`edge add` refuses a second link of the same kind between the same two
nodes. Removal deletes descriptions, confidence, polarity, citations,
parameters, roles and mappings for what was removed, in the same commit;
challenges, findings, signoffs and other history are kept.

## Attributes, References, Evidence

```bash
latris attr set <target-id> <attribute> <value>   # description | confidence
#   confidence: low | medium | high | quantitative-pending | by-definition
#   (by-definition: true by definition or accounting; needs no source and
#   doesn't count against evidence coverage)

latris ref add <bibkey> --title "..." --author "..." --year ... [--doi ...] [--url ...] [--cited-via <key>]
latris ref edit <bibkey> [--title ...] [--author ...] [--year ...] [--doi ...] [--url ...] [--notes ...] [--cited-via <key>]   # "" clears
latris ref remove <bibkey> [--with-citations] [--rationale "..."]
latris ref list
latris ref import <bibfile>

latris evidence add <target> <attribute> <bibkey> [--verified-by human|ai] [--notes "..."] [--contradicts]
latris evidence check <target> <attribute> <bibkey> supports|against|off-topic|too-little|unchecked     --rationale "..." [--quote "..."] [--by human|ai]
    # --quote is looked up in the source's stored text (snapshot, fetched full text, abstract);
    # an AI's quote that isn't found is refused, and an AI's `supports` needs one.
latris evidence remove <target> <attribute> <bibkey> [--rationale "..."]
# <target>: a factor (label or ID) or a link ("From -> To", or its edge ID)
```

`--contradicts` records a source that argues **against** the claim. It sits
on the same link as the sources for it; reports mark it "against", list
the link under "Contested links" (sources for and against, plus open
challenges), and leave it out of evidence coverage. In a build spec, use
`contradicts: [<bibkey>]` beside `sources:`.

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

**Run by an AI agent** (the shell sets `CLAUDECODE`, `AI_AGENT` or
`LATRIS_AGENT`): new work is recorded `ai-proposed`, `--by` /
`--verified-by` default to `ai`, and commits carry
`Recorded-by-agent: <name>`. `mature review|approve`, `signoff record`,
`mapping approve`, `challenge resolve` and a check, build or prose
`--by human` then need `--confirmed-by-person`: the person reviewed it and
asked the agent to record it (the commit says so).
`LATRIS_AGENT=none` turns detection off.

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
latris view set <model-type> <target> <attribute> <value> [--rationale "..."]
latris view set fcm <edge> weight -- -0.7   # `--` before a negative number
latris view role <model-type> <node> <role>  # e.g. cld "Volunteer departures" outcome

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
latris export md [--pack client|audit|review|workshop|publication] [--report-url URL] [--no-ai] [--no-link]
latris export dot --view system_map|cld|dag
latris export spec [-m TYPE]                     # the model as a build spec (what a link carries; build --spec reads it)
latris link [--model-type cld] [--app-url URL]   # a link that opens the model in the Latris app
```

`latris link` needs no network: it packs the project (as a `build` spec:
factors, links, evidence for and against, sources, assumptions, open
questions, findings, open challenges, interpretation prose and the outcome
— not the git history) into the fragment of an `app.latris.app/open#…`
URL. Opening it creates a hosted copy with a report link and the full
figure; the person can save it to their account. Everything arriving this
way is recorded as AI-proposed, and findings arrive unapproved.

**Known issue:** the link drops source checks, quotes, extracts and
approvals but keeps the interpretation prose, so a copy can claim checks it
doesn't hold. See [`SHARE_LINK.md`](SHARE_LINK.md).

The library exports Markdown and DOT. Word reports, self-contained
HTML review packs (and importing completed ones) and story HTML are part
of the Latris app (`app.latris.app`) since 0.5.0. The Markdown report includes a
Mermaid sketch of the model (section `diagram`, in every pack) that
renders on GitHub and in most chat UIs, with links coloured by polarity and
the feedback loops listed under it (R1, B1, …; cycles that differ by one
alternative step count as one loop). Sections appear in the pack's own
order: `client` and `publication` lead with the interpretation (answer,
implications, confidence) and leave out the change log (`history`); the
client pack shows approved findings only and says how many are waiting. `--report-url` adds a link to the
hosted copy of the report in the footer; it defaults to the link recorded
when the project was shared, if any. `--no-ai` writes the narrative
preamble without attempting an AI call.

## Graph Analysis

```bash
latris analyse loops
latris analyse propagate <variable>
latris analyse d-sep <x> <y> [--given <z1,z2,...>]
latris analyse blanket <variable>
latris analyse paths <from-variable> <to-variable>
latris analyse adjustment-sets <treatment> <outcome>
latris analyse estimate <treatment> <outcome> --dataset NAME [--adjust F ...] [--no-adjust]
                        [--column "Factor=column" ...] [--model auto|linear|logistic] [--no-record]
```

Qualitative computation on the existing stable views. `loops` finds all
feedback loops with R/B classification (CLD polarity). `propagate` traces
qualitative effects of a hypothetical increase. `d-sep` tests d-separation
(conditional independence) given a conditioning set. `blanket` computes
the Markov blanket (parents + children + co-parents). `paths` enumerates
all paths between two variables with node classification
(chain/fork/collider). `adjustment-sets` finds valid adjustment sets via
the backdoor criterion. `estimate` fits the effect from a dataset, adjusting
for the smallest valid backdoor set the data measures (or a given set,
checked), and records it (`dag-estimate`). Variables resolve by ID, label,
or prefix.

## Data

```bash
latris data add <file.csv|.tsv> [--name NAME] [--description TEXT]   # copied into data/files, committed
latris data list
latris data show <name>                                                # columns and types
```

The app's data workspace has the full set of cleaning and reshaping
operations (`/api/datasets/*`).

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
latris bn set-noisy-or <node> -c "Cause=yes:0.6" [--leak 0.02] [--active yes]   # Noisy-OR; --active = the effect state
latris bn learn <dataset>                      # learn parameters from data (provenance-protecting merge)
latris bn state-spaces                         # list defined state spaces
latris bn cpts                                 # list defined CPTs
latris bn check                                # validate state-space / CPT completeness
latris bn marginals                            # compute prior marginals (recorded; --no-record)
latris bn query [-q node] [-e node=state] [-s "node=state:0.8"] [--likelihood "node=a:4,b:1"]
                                               # posterior query under hard / soft / likelihood evidence (recorded)
latris bn explain [-e node=state] [-s ...] [--over node ...]   # most likely explanation (MPE / MAP), recorded
latris bn set-uncertainty <node> --n 20 [--row "Parent=state,..."] [--reason] [--source]
latris bn uncertainty | clear-uncertainty <node>
latris bn monte-carlo <target> [--state s] [-e ...] [-s ...] [--runs 500] [--seed 1234] [--max-seconds 60]
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
latris sd set-settings [--time-units month] [--final-time 36] [--initial-time] [--dt] [--saveper] [--method]
latris sd settings                             # the stored clock and the defaults for anything unset
latris sd set-role <node> <stock|flow|auxiliary|constant|source_sink>
latris sd set-initial-value <stock> <value> --units <u> [--non-negative]
latris sd set-constant <node> <value> --units <u>
latris sd set-equation <flow|aux> "<expression>" --units <u>   # names = slugified labels; TIME; MIN MAX ABS IF_THEN_ELSE STEP TABLE EXP LN SQRT
latris sd set-table <flow|aux> -p x:y -p x:y ... --x-units <u> --y-units <u> [--extrapolate clamp|linear]
latris sd roles | equations | stocks | constants | tables   # listings
latris sd check                                # readiness incl. dimensional consistency
latris sd simulate [--scenario NAME ...] [--set "Var=value [units]" ...] [--final-time T] [--dt DT] [--saveper S] [--method euler|rk2|rk4|adaptive] [--json] [--no-record]
latris sd set-scenario NAME --set "Var=value [units]" ... [--description] [--reason] [--source] [--origin]
latris sd scenarios | remove-scenario NAME
latris sd set-uncertainty <constant|stock> <uniform|triangular|normal|lognormal|beta|gamma> [--min --mode --max --mean --sd --alpha --beta --shape --scale] [--reason] [--source]
latris sd uncertainty | clear-uncertainty <node>
latris sd monte-carlo [--runs 200] [--seed 1234] [--sampling lhs|random] [--var V ...] [--scenario NAME] [--max-seconds 60]
latris sd sensitivity <variable> [--metric final|peak|peak-time|min|mean|at:T] [--pct 10] [--scenario NAME]
latris sd loops [--scenario NAME] [--from T] [--to T]          # loop dominance (Loops That Matter)
```

Simulate, monte-carlo, sensitivity and loops take the run settings
(`--final-time`, `--dt`, `--method`) and record their result
(`--no-record` to skip).

## ToC (Theory of Change)

A results chain on the shared substrate: each factor gets a level (view
role), links are ordinary causal links running forward through the levels,
and the impact is the outcome of interest. The check is recorded as an
`AnalysisRun` (`toc-pathways`) so reports show it.

```bash
latris toc level <node> <input|activity|output|short_term_outcome|long_term_outcome|impact>
latris toc levels                              # factors by level, and any without one
latris toc check [--no-record]                 # pathways activity → impact; per-link evidence status + assumptions
latris assumption add "<why the step happens>" --target "From -> To"   # counted per link by the check
latris toc prior "From -> To" <p> [--source ID] [--origin …] [--verified] [--notes …]   # process tracing: prior (default 0.5)
latris toc test "From -> To" <name> --if-true <P(E|holds)> --if-false <P(E|doesn't)> [--found|--not-found]
               [--description …] [--source ID] [--verified] [--notes …] [--remove]     # add / update / remove a test
latris toc trace [--no-record]                 # posterior per link, pathway confidence, most informative next test
latris toc impact <outcome> --dataset D --time COL --at T [--column C] [--no-record]   # interrupted time series
latris toc impact <outcome> --dataset D --time COL --at T --group COL --treated V…     # difference-in-differences
```

Impact estimates are recorded as `toc-impact` (one per outcome, dataset and
design) and list a caution for each validity check that fails or can't be
made. Process tracing is recorded as `toc-process-trace`; tests are classified as
hoop, smoking gun, doubly decisive or straw in the wind from their two
probabilities.

## FT (Fault Trees)

A fault tree on the shared substrate: each event's type is a view role, an
input links to the event it feeds (`logical` or `causal` edge), and every
top or intermediate event has a gate stored on it. Only events with a type
are in the tree. `ft analyse` is recorded as an `AnalysisRun`
(`ft-analysis`).

```bash
latris ft event <node> <top_event|intermediate_event|basic_event|undeveloped_event>
latris ft gate <event> <and|or|vote> [--k K]          # vote: at least K of the inputs
latris ft probability <event> <p> [--source KEY] [--origin ORIGIN] [--verified] [--notes]
latris ft show                                        # the tree from the top event down
latris ft check                                       # structure; exits 1 until complete
latris ft analyse [--max-order N] [--no-record]       # cut sets, SPOFs, exact P(top), importance
latris ft uncertainty <target> [lognormal --median M --error-factor EF | uniform --min --max | …] [--reason] [--source] [--clear]
latris ft monte-carlo [--runs N] [--seed S] [--sampling lhs|random] [--output R] [--no-record]   # percentiles, mean vs point, drivers
```

## Bow-tie

Threats, barriers and consequences around one top event, on the shared
substrate: each element is a view role, lines are ordinary links, and each
barrier's type, status, owner and failure probability (PFD) are stored with
provenance. `bowtie analyse` is recorded as an `AnalysisRun` (`bt-analysis`).

```bash
latris bowtie element <node> <hazard|top_event|threat|consequence|barrier|escalation_factor>
latris bowtie barrier <barrier> [--type passive_hardware|active_hardware|active_hardware_human|human]
                      [--status in_place|degraded|not_in_place] [--owner] [--pfd P] [--source] [--origin] [--verified]
latris bowtie frequency <threat> <per_year> [--source] [--origin] [--verified] [--notes]
latris bowtie show                                    # line by line
latris bowtie check                                   # structure; exits 1 until complete
latris bowtie analyse [--no-record]                   # lines, flags, LOPA frequencies, RAW per barrier
latris bowtie uncertainty <target> [lognormal --median M --error-factor EF | uniform --min --max | …] [--reason] [--source] [--clear]
latris bowtie monte-carlo [--runs N] [--seed S] [--sampling lhs|random] [--output R] [--no-record]   # percentiles, mean vs point, drivers
```

## Event tree

From one initiating event through ordered yes/no headings to end states.
The tree is stored as data (heading order + sequences), not substrate
links. `et analyse` is recorded as an `AnalysisRun` (`et-analysis`).

```bash
latris et element <node> <initiating_event|functional_event|end_state>
latris et order <heading> <heading> ...               # left to right
latris et sequence <end_state> "Heading=yes" "Heading=no" ...   # one path; same answers replace it
latris et remove-sequence "Heading=yes" ...
latris et probability <heading> <p_yes> [--given "Heading=no" ...] [--source] [--origin] [--verified]
latris et frequency <initiating_event> <per_year> [--source] [--origin] [--verified]
latris et show                                        # sequences table (· = not asked)
latris et check                                       # complete tree? exits 1 until it is
latris et analyse [--no-record]                       # sequence and end-state probabilities / frequencies
latris et uncertainty <target> [lognormal --median M --error-factor EF | uniform --min --max | …] [--reason] [--source] [--clear] [--given "Heading=no"]
latris et monte-carlo [--runs N] [--seed S] [--sampling lhs|random] [--output R] [--no-record]   # percentiles, mean vs point, drivers
```

## MCDA (multi-criteria decision analysis)

Options against swing-weighted criteria. Options and criteria are view
roles; weights, directions, scales and scores are stored with provenance.
`mcda analyse` is recorded as an `AnalysisRun` (`mcda-analysis`).

```bash
latris mcda element <node> <option|criterion>
latris mcda criterion <criterion> [--weight W] [--direction higher|lower] [--worst X --best Y] [--units U]
                      [--source] [--origin] [--verified] [--notes]      # only what you give changes
latris mcda score <option> <criterion> <value> [--source] [--origin] [--verified] [--notes]
latris mcda show                                      # options × criteria matrix with weights
latris mcda check                                     # weights, directions, every score; exits 1 until complete
latris mcda analyse [--no-record]                     # ranking, contributions, dominance, weight thresholds
```

## ACH (analysis of competing hypotheses)

Hypotheses against evidence items (view roles); one rating per pair, and an
item's credibility and relevance, each with provenance. An item's sources
are ordinary citations on it. `ach analyse` is recorded (`ach-analysis`).

```bash
latris ach element <node> <hypothesis|evidence_item>
latris ach item <item> [--credibility high|medium|low] [--relevance high|medium|low] [--notes]
latris ach rate <item> <hypothesis> <CC|C|N|I|II> [--rationale] [--origin] [--verified]
latris ach show                                       # items × hypotheses matrix
latris ach check                                      # every pair rated? exits 1 until so
latris ach analyse [--no-record]                      # ranking by evidence against, linchpins, non-diagnostic items
```

## Decision tree

Decision, chance and terminal nodes (view roles); branches are ordinary
links, each node with one parent. Branch labels, probabilities, values and
payoffs are stored with provenance. `dt analyse` is recorded (`dt-analysis`).

```bash
latris dt element <node> <decision|chance|terminal>
latris dt branch "Parent -> Child" [--label L] [-p P] [--value V] [--source] [--origin] [--verified]
latris dt payoff <terminal> <value> [--source] [--origin] [--verified] [--notes]
latris dt uncertainty <chance node> <name>             # same name: one uncertainty under different choices
latris dt settings [--objective maximise|minimise] [--units U]
latris dt show                                         # the tree with expected values; → marks best choices
latris dt check                                        # one root, a tree, payoffs, probabilities sum to 1
latris dt analyse [--no-record]                        # best strategy, EVPI, probability thresholds
```

## Markov cohort model

States and strategies (view roles); transitions are ordinary links between
states. Probabilities, costs, utilities and the start are stored with
provenance. `markov analyse` is recorded (`markov-analysis`).

```bash
latris markov element <node> <state|strategy>
latris markov transition "From -> To" <p> [--strategy S] [--source] [--origin] [--verified]
latris markov reward <state> [--cost C] [--utility U] [--strategy S] [--source] [--verified]
latris markov start <state> <proportion>
latris markov settings [--cycles N] [--cycle-length L] [--time-units years] [--discount R] [--outcome-discount R]
                       [--half-cycle/--no-half-cycle] [--wtp W] [--cost-units U] [--outcome-units U]
latris markov show | check
latris markov analyse [--no-record]            # costs, outcomes, ICERs, dominance, the choice at the WTP
```

## Results

Recorded analysis results and which ones reports show (the latest run of
each analysis; results computed before the model changed are marked out of
date).

```bash
latris results list [--all]      # what reports use (--all: every recorded result)
latris results show <run>        # one result in full
latris results hide <run>        # leave it out of reports (stays in the log)
latris results unhide <run>
```

## Check (coherence)

```bash
latris check coherence    # cross-artefact coherence checks over the project
latris check handover     # ready for a board? what's left, each with its fix (exit 1 until clear)
latris check integrity    # does every reference between files resolve? (exit 1 on errors)
latris check integrity --fix   # first remove rows left by deleted nodes/links; --all also lists history notes
```

`check integrity` is listed in SCHEMA_NOTES.md § Invariants.

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
latris finding add "<statement>" [--category structure] [--model-type cld] [--target <node|edge>] [--detail "..."]
latris finding list
latris finding show <finding-id>
latris finding check-stale    # flag findings whose underlying state changed
```

## Interpret

Interpret-phase sections: template claims + AI-generated prose.

```bash
latris interpret initialise            # create the sections, with their claims
latris interpret list                  # list interpretation sections
latris interpret refresh-claims        # re-derive claims after changing the model
latris interpret generate-prose <section>  # AI prose for one section
latris interpret generate-all          # AI prose for all sections
latris interpret show <section|type>   # a section's claims and prose (e.g. answer_to_question)
latris interpret set-prose <section|type> "..." [--by human|ai]   # write the prose yourself
```

## Story (Communicate)

A versioned `Story` object: a plain-language walk through the model. The
Latris app publishes it as scrollytelling HTML.

```bash
latris story draft                 # scaffold a Story from the current model
latris story list
latris story show <story-id>
latris story generate-prose <beat> # AI prose for one beat (StoryBeatProse)
latris story generate-all          # AI prose for all beats
latris story set-prose <beat> ...  # set beat prose manually
```

## Sync (collaboration)

Turn-based git push/pull through the Latris-native control plane +
invisible Gitea (see [`GIT_INTEGRATION.md`](GIT_INTEGRATION.md) →
"Remote collaboration").

```bash
latris sync login --email you@x.com            # request a one-time code
latris sync login --email you@x.com --code ... # finish signing in
latris sync share "Project name"                # create + push a remote project
latris sync link on|off [--pack client]         # public report link (owner only)
latris sync remote      # configure / show the project's sync remote
latris sync push        # push local commits to the shared project
latris sync pull        # pull + integrate remote commits
latris sync fetch       # fetch remote state without integrating
latris sync status      # show local vs remote sync state
```

`login`/`share` are the bridge from a local project to the hosted app
(`https://app.latris.app`). `share` prints
the hosted app's address (sign in there and pick the project from the
list) and, when the control plane provides one, the project's report
link. `link on` gives the shared project a public, unindexed report page
at `app.latris.app/r/...` (off by default); Markdown exports then link to
it. Turning it off and on again issues a new link.

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
