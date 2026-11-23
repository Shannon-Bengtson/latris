# ruff: noqa: E501
"""Static in-app help topic data.

Help topics are bundled with the application. They are deliberately project
independent: the GUI can open help from any workspace state without needing
to inspect the active project.
"""

from __future__ import annotations

from pydantic import BaseModel


class HelpTopic(BaseModel):
    id: str
    title: str
    category: str
    summary: str
    body: str


HELP_CATEGORIES: list[str] = [
    "getting-started",
    "workflow",
    "build",
    "formalise",
    "analyse",
    "interpret",
    "communicate",
    "collaboration",
    "model-types",
    "evidence",
    "provenance",
    "ai",
    "versioning",
    "developer",
]


HELP_TOPICS: list[HelpTopic] = [
    HelpTopic(
        id="welcome",
        title="Welcome to Latris",
        category="getting-started",
        summary="What Latris is, what it is for, and the ideas that make the workspace hang together.",
        body="""## What Latris is

Latris is an evidence-native modelling workbench for building, reviewing, analysing, and reporting on causal and systems models. It keeps the model, evidence, provenance, AI assistance, version history, and exported outputs in one auditable project.

## Core ideas

- **Inspectability is the boundary.** Latris is for models whose reasoning can be inspected, evidenced, challenged, and defended. The graph is *how* a model is made inspectable — the lens, not the limit. Models you can run but can't explain (black-box predictors) are out of scope by design.
- **Substrate first.** The shared conceptual model is the source of truth for entities, edges, definitions, evidence, and review history.
- **Formal views second.** CLD, DAG, and FCM views are projections from the shared substrate with model-specific rules and attributes.
- **Evidence attaches to claims.** Citations and data links attach to attributes such as definitions, confidence, polarity, and weights.
- **AI is reviewable.** AI drafts suggestions, but the user previews, accepts, rejects, and audits what lands in the project.
- **Every change is versioned.** Project state is stored in files and committed through Git-backed history.

## Main workspace

Use the process stepper across the top of the app:

1. **Build** the conceptual model.
2. **Formalise** by selecting model types and setting their parameters.
3. **Analyse** each model on its canvas.
4. **Interpret** findings into claims and prose.
5. **Communicate** through reports, diagrams, and review packs.

Evidence (Data and References) is always available alongside the stepper — it is a persistent resource, not a phase.
""",
    ),
    HelpTopic(
        id="create-open-projects",
        title="Create and Open Projects",
        category="getting-started",
        summary="How projects are created, what a project contains, and what must be configured first.",
        body="""## Project foundations

Every project starts with a modelling question or decision statement. This foundation tells the app, the AI prompts, readiness checks, and exports what the model is meant to answer.

## Requirements

Latris uses Git under the hood for version history and human accountability. You do not need to understand Git commands or workflows; the app presents history as versions, milestones, alternatives, compare, and undo.

## Project contents

A Latris project contains:

- `project.yaml` for the foundation and selected model types.
- `research-base/` for references and notes.
- `substrate/` for conceptual entities, edges, attributes, mappings, and evidence links.
- `views/` for formal views such as CLD, DAG, and FCM.
- `data/` for registered datasets, versions, and data action logs.
- `provenance/` for assumptions, decisions, questions, sign-offs, sessions, predictions, and exclusions.
- `ai/` for AI interactions and challenge records.
- `reports/` for draft reports and generated report content.

## First practical path

1. Create or open a project from the landing page.
2. Set the modelling question in the project overview.
3. Build the conceptual model.
4. Move through Build, Formalise, Analyse, Interpret, and Communicate. Data and References are always available as the evidence basis.
""",
    ),
    HelpTopic(
        id="project-context",
        title="Project Context & Scope Contract",
        category="getting-started",
        summary="What the project-level context and scope fields are for and how AI uses them.",
        body="""## Why project context matters

The project's modelling question is the headline, but on its own it is rarely enough for AI suggestions to land in the right register. Latris reads these foundation fields into every AI prompt:

- **Modelling Question** — the specific question the model exists to answer.
- **Background / Context** — the broader situation: who is this for, what decision does it inform, what is already known, what is the policy or operational setting?
- **Model Boundary** — what is in scope and out of scope.
- **Exclusions** — things deliberately not modelled, with reasons.
- **Predictions** — the behaviour you expect the model to explain (a reference mode), checked against what the AI produces.

Without Background filled in, AI prompts produce generic suggestions ("agricultural trends") instead of mechanistic ones ("phosphorus loading from catchment runoff"). Background is the difference between a textbook answer and a project answer.

## The scope contract (optional, high-leverage)

Three further fields sharpen the *structure* the AI builds. They are optional, but when set they make repeated AI runs cover the same ground at a consistent level of detail — the single biggest lever on model quality and consistency:

- **Coverage Dimensions** — the themes or subsystems the model must span (e.g. "economic, social, environmental drivers"). The AI is told to cover every one, so runs stop drifting to different corners of the problem.
- **Granularity Level** — the intended resolution (e.g. "each node a measurable variable a manager could track" vs "a high-level strategic sketch"). Keeps the abstraction level uniform.
- **Audience** — who the model is for, so variables and mechanisms are framed appropriately.

Leave them blank and the AI uses its judgement; fill them in and the structural prompts treat them as binding.

## What to write

A few sentences is usually enough. Useful elements include:

- The setting: organisation, jurisdiction, or system being modelled.
- The decision the model is meant to inform.
- Stakeholders who will read or act on the model output.
- Constraints, prior work, or upstream context the model should respect.

You can edit Background at any time from the project inspector. Updates are auto-committed and reach all subsequent AI calls immediately.

## How AI uses context

Every prompt that proposes content the user will live with — node descriptions, edge rationales, citation suggestions, evidence-gap detection, interpretation prose — receives these foundation fields as part of its context, and the structural prompts additionally honour the scope contract (coverage dimensions, granularity, audience). You do not need to repeat them in individual prompts; they are threaded automatically.
""",
    ),
    HelpTopic(
        id="workflow-overview",
        title="The Five-Phase Workflow",
        category="workflow",
        summary="How Build, Formalise, Analyse, Interpret, and Communicate fit together.",
        body="""## Evidence basis

Data and References are always available from the header — a persistent resource, not a phase. Import datasets and references whenever they are useful; they inform structure in Build and parameters in Formalise.

## Build

Create the conceptual model. Use Compose to stage candidate nodes and edges, Visualise to edit the canvas, and Detail to review model elements in table form.

## Formalise

Turn the structure into a complete formal model. Select model types, then parameterise each one — a Table representation for the parameter grid (e.g. CLD polarity, FCM weights) and a Canvas representation for reference.

## Analyse

Interrogate a finished model. Pick a model from the Analyse dropdown to see its canvas with overlays (loops, propagation, Markov blanket, d-separation).

## Interpret

Turn analysis outputs and project evidence into structured interpretation sections. Interpret is per-formalism: pick a model from the Interpret dropdown to see that formalism's sections. These sections are then available to the report builder.

## Communicate

Use the left-hand strip to switch between Report, Diagram, Review, Story and Explorer. Report, Diagram and Review are per-formalism: pick a model from the Communicate dropdown to assemble report sections, export diagrams, create Word or Markdown reports, and send Review Packs to outside reviewers. Stories belong to the whole project: each tells the answer to the project's question for one audience, drawing on every model type. An Explorer is one model as an interactive page a reader can click through.

**Everything here is shared the same way.** Each of the five has *Share by link*: turn it on and you get a link anyone can open, with no account needed. Turn it off and the link stops working; turn it on again and you get a new one. Sharing by link needs the project saved to your Latris account, and only its owner can share. A link always shows the current version of the model. Each also has a download, for a file you can send or keep.

## Readiness gates

The stepper shows traffic-light readiness between phases. A red transition blocks progression because required project material is missing. Yellow means work can continue but the output is not yet strong. Green means the project has the expected inputs for that transition.
""",
    ),
    HelpTopic(
        id="readiness-gates",
        title="Readiness Gates",
        category="workflow",
        summary="What the red, yellow, and green phase indicators mean.",
        body="""## What readiness checks do

Readiness checks look for the minimum material needed to move from one phase to the next. They are guardrails, not a judgement that the model is complete.

## Traffic lights

- **Red** means the next phase is blocked until required items exist.
- **Yellow** means the phase can be entered, but some important evidence, attributes, or review items are thin.
- **Green** means the project has the expected inputs for the transition.

## Typical blockers

- Home -> Build: no modelling question defined.
- Build -> Formalise: fewer than 3 nodes, or the graph is not a single connected network (orphan nodes or separate sub-graphs).
- Formalise -> Analyse: no model type selected, a selected model is structurally incomplete (e.g. CLD without loops, DAG with a cycle), or required attributes (e.g. polarity for CLD, weights for FCM) are missing.
- Interpret -> Communicate: no structural summary with claims.

## How to resolve issues

Use the phase tools instead of working around the gate. Set the modelling question in the overview, add evidence anytime via the Data and References buttons, create entities and edges in Build, select and parameterise model types in Formalise, and generate prose in Interpret before using those sections in reports.
""",
    ),
    HelpTopic(
        id="formalise-overview",
        title="The Formalise Phase",
        category="formalise",
        summary="Select model types and set their parameters before analysing.",
        body="""## What Formalise is for

Formalise turns your conceptual structure into a complete formal model. Choose the model types you want from Model selection, then parameterise each one.

## Per-model workspaces

Each selected model type appears in the Formalise dropdown. With a model open you work in the representation(s) that type offers:

- **Table** — a parameter grid for setting model-specific attributes (CLD polarity, FCM weights).
- **Canvas** — the structure, drawn the way the report's figure draws that type, with the selected element's parameters in the inspector: Bayesian networks (states and probability tables), system dynamics (roles, equations and values), decision trees (decision, chance and payoff nodes; each branch's option or state, probability and value), Markov models (states, moves per cycle, costs, utilities, the starting cohort and the clock) and theories of change (each factor's level; process-tracing priors and evidence tests on links).
  Fault trees (event types, gates — AND, OR, k of n — and basic-event probabilities) and bow-ties (threats and their frequencies, barriers with type, status, owner and failure probability, the top event and consequences) are set here too, with a median and error factor for any value whose uncertainty you know.
- **Matrix** — MCDA (options, criteria, swing weights and the score grid), ACH (hypotheses, evidence, credibility, relevance and the consistency grid) and event trees (the initiating frequency, the headings in order with their probabilities — conditional ones too — and each sequence's end state). These have no links: Build doesn't ask for their elements to be connected, and the other types' canvases leave them out.

## Moving on

The Formalise -> Analyse gate turns green once at least one model type is fully parameterised. Analyse then lets you interrogate that model on its canvas.
""",
    ),
    HelpTopic(
        id="gather-data",
        title="Data Workspace",
        category="evidence",
        summary="Upload datasets, inspect rows and columns, apply data operations, and keep an audit trail.",
        body="""## What Data mode is for

Data mode lets you register source datasets and perform lightweight wrangling while preserving the audit trail. The dataset itself can support model claims through data evidence links.

## Main tasks

- Upload CSV or TSV data.
- Preview rows and columns.
- Select columns for inspection.
- Assign column roles and descriptions.
- Apply supported data operations.
- Create dataset versions before or after major changes.
- Restore earlier dataset versions if needed.

## Data evidence

Data does not automatically prove a model claim. Link a dataset, column, statistic, value, and rationale to a node or edge through the inspector when the data supports a specific attribute.

## Audit trail

Dataset operations are recorded as data actions. Reports can include datasets and data action history so reviewers can see what changed before the model used the data.
""",
    ),
    HelpTopic(
        id="gather-references",
        title="References Workspace",
        category="evidence",
        summary="Import, search, review, and reuse citations as project evidence.",
        body="""## What References mode is for

References mode is the project bibliography and evidence base. References can come from BibTeX, DOI import, manual entry, or scholarly search.

## Main tasks

- Import BibTeX records.
- Import a source by DOI when metadata is available.
- Search for scholarly references.
- Review titles, authors, years, identifiers, abstracts, and URLs.
- Use references as citations for attributes on nodes and edges.

## Evidence links

A reference becomes evidence only when it is attached to a specific claim or attribute. Attach citations in the inspector so reviewers can see exactly what a source supports.

## Source snapshots

A reference can carry a `source_snapshot` recording publisher-fetched content (abstract, landing-page text, or a full-text excerpt) with retrieval URL, fetch timestamp, and content hash. This is distinct from the user-authored `notes` field.

When attaching evidence, the system promotes `source_access` from `title_only` to `abstract` only when the reference has a real abstract or an abstract / full-text snapshot. User notes alone and landing-page-text snapshots do **not** confer abstract-grade access — they may discuss topical context but they are not the paper's content.

## Practical advice

Keep references broad enough to support the model, but attach them narrowly. A paper might support a node definition, an edge direction, a polarity judgement, or a confidence rating; those are different claims and should be linked separately when possible.
""",
    ),
    HelpTopic(
        id="build-compose",
        title="Compose Mode",
        category="build",
        summary="Stage candidate nodes and edges from references, data, AI suggestions, or manual entry before applying them.",
        body="""## What Compose mode is for

Compose mode bridges evidence and Build. It helps you curate candidate structure before it becomes part of the model.

## Node stage

Review candidate entities, edit their labels or descriptions if needed, then accept the ones that belong in the model.

## Edge stage

After nodes are accepted, review candidate relationships between them. Edges can come from references, data, AI proposals, or manual entry.

## Applying to the model

Accepted candidates remain staged until you apply them. Applying creates real substrate entities and edges, records provenance where available, and refreshes the model workspace.

## When to use it

Use Compose when you want a controlled review queue. Use the canvas when you already know the structure and want to edit directly.
""",
    ),
    HelpTopic(
        id="build-canvas",
        title="Visualise Mode",
        category="build",
        summary="Edit the conceptual model directly on the graph canvas.",
        body="""## What Visualise mode is for

Visualise mode is the main graph canvas for the conceptual model and selected formal view. It is best for direct editing and spatial reasoning.

## Common actions

- Add nodes.
- Connect nodes with edges.
- Rename nodes inline.
- Select nodes or edges to edit details in the inspector.
- Arrange the view.
- Open context actions on graph elements.

## Substrate versus views

The conceptual substrate is the shared model. Formal views such as CLD, DAG, and FCM add model-specific requirements. If an element is not ready for a selected view, use Analyse and Configure to complete the required attributes.

## Links

- To link two factors, drag from the dot on one factor's edge and let go anywhere on the other factor.
- Links meet each factor's border on the line between the two, so they stay attached sensibly when you move a factor.
- Causal maps draw curved links that bow outward around each feedback loop, as the report's figure does. Trees (fault tree, decision tree, theory of change, bow-tie) draw right-angle connectors.
- Select a curved link to show its bend handle. Drag it to reshape the curve; double-click it to go back to the automatic bow.
- Arrange → Links switches between Auto, Curved and Right-angle. The choice is remembered for this project on this device.

## Layout

Canvas positions are saved separately from semantic model data. Moving a node changes the layout, not the underlying claim.

Arrange → Re-layout All lays the whole map out again: maps with feedback loops are spread so each loop reads as a ring, and maps without loops are laid out top-down. Re-layout clears hand-made link bends.
""",
    ),
    HelpTopic(
        id="build-detail-table",
        title="Detail Mode",
        category="build",
        summary="Review and edit model elements in a structured table.",
        body="""## What Detail mode is for

Detail mode is a table view for systematic review. It is useful when the canvas is too visual and you need to scan, compare, or edit many elements.

## What to check

- Labels and kinds.
- Descriptions.
- Confidence and per-element maturity (proposed → reviewed → approved).
- Evidence indicators.
- Review annotations and unresolved questions.
- Mapping or model-specific status.

## Best use

Use Detail mode for cleanup passes: standardise naming, find missing descriptions, spot thin evidence, and prepare the model before Analyse or export.
""",
    ),
    HelpTopic(
        id="analyse-canvas",
        title="Analyse Canvas",
        category="analyse",
        summary="View formal model analysis overlays without changing the Build canvas.",
        body="""## What the Analyse canvas is for

The Analyse canvas mirrors model structure but adds analysis overlays and formal-view context. It keeps analytic reading separate from direct model authoring.

## Supported stable views

- **CLD:** feedback loop detection, loop polarity, and polarity propagation.
- **DAG:** acyclicity checks, paths, d-separation, Markov blankets, and adjustment-set support.
- **FCM:** weighted influence structure and simulation-oriented attributes.
- **BN:** observe evidence on nodes and read posterior beliefs, shown as bars inside each node (see the Bayesian Networks topic).
- **SD:** run the simulation (with saved scenarios to compare), Monte Carlo, sensitivity and loop dominance from the analysis pane; each factor shows its end-of-run value on the canvas (see the System Dynamics topic).
- **BN, beyond evidence:** *set* a factor (a policy, not an observation), apply a saved scenario, record the query, find the most likely explanation, run sensitivity, Monte Carlo over the tables (after saying how well each table is known) and compare scenarios.
- **Decision tree, Markov, theory of change:** roll back the tree, run the cohort, or check the theory and run process tracing from the analysis pane.
- **MCDA, ACH:** run the analysis from the matrix page; its charts, tables and the report's figure show there.
- **Fault tree, bow-tie, event tree:** analyse (cut sets and importance; consequence frequencies through the barriers; end-state frequencies), then Monte Carlo over the ranges you set.

Nodes take the shapes the report figure gives them — stocks as boxes, flows with a valve, sources and sinks as dashed clouds, BN nodes as belief-bar monitors — so the editor and the report read the same.

## Recorded results

Runs that are recorded (simulations, Monte Carlo, sensitivity, loop dominance, recorded BN queries and every other model type's analyses) are listed under **Recorded results** in the pane on the right. Click one to read it at full width over the canvas or table, with the same charts and tables the report shows; **Close** or Escape returns. Each says if the model has changed since it ran ("Out of date"), and **Hide from report** leaves it out of reports (the same as `latris results hide`).

Under **Analyses** (or **More analyses**), the pane offers every other analysis Latris has for the model type as a form — DAG effect estimates, theory-of-change impact, fuzzy-cognitive-map steady states, Bayesian-network queries with uncertain evidence or interventions, system-dynamics option comparisons under uncertainty, and any added later. Each option is labelled and explained; factors, states, scenarios, datasets and columns are picked from the model. **Run** records the result and opens it.

MCDA, analysis of competing hypotheses and event trees are edited as grids in the centre; their readiness, **Run the analysis** and recorded results are in the pane on the right, as for every other model type. Click a factor's name in a grid to show its details there.

## Workflow

1. Select a model type.
2. Review readiness for that view.
3. Run or inspect available analyses.
4. Record your reading in **Observations** (see below).
5. Use findings as inputs for Interpret.

## Observations

The analysis pane carries an **Observations** section on every formalism — when nothing is selected (a project-level reading) and when a node or edge is selected (a reading of that element). Record what you see in the analysis here: each observation is saved as a finding, committed with provenance, and flows into the matching Interpret section's claims. Element-anchored observations are flagged if the element they reference later changes. Pick a category (structure, sensitivity, inference, etc.) so the observation lands in the right report subsection.

## Editing

Use Build for core graph edits. Use Configure for model-specific attributes such as CLD polarity or FCM weights.
""",
    ),
    HelpTopic(
        id="bayesian-networks",
        title="Bayesian Networks",
        category="model-types",
        summary="Define state spaces and CPTs, then observe evidence and read posterior beliefs.",
        body="""## What a Bayesian Network is

A Bayesian Network (BN) is a DAG where every node has a discrete **state space** and a **conditional probability table (CPT)** giving the probability of each state for every combination of its parents' states. Once parameterised, you can enter evidence and the network computes updated (posterior) beliefs for every node by exact inference.

## Parameterise in Formalise

Select **Bayesian Network** as a model type, then open the Formalise phase and select a node:

1. **State space** — list the node's mutually exclusive, exhaustive states (e.g. `low, high`). Mark it *ordered* for ordinal states. A node needs a state space before it can have a CPT.
2. **CPT table** — click *Edit CPT table* to open the spreadsheet. Each row is one combination of the parents' states; enter the probability of each of the node's states. Each row must sum to 1.0 — the Σ column flags rows that don't and offers one-click normalisation. Root nodes have a single prior row.
3. **Noisy-OR (optional)** — for a binary node whose parents are all binary, parameterise it compactly as Noisy-OR (a per-cause probability plus a leak) instead of a full table.

Every value carries provenance (where the number came from), so a BN built in Latris stays auditable — something incumbent BN tools can't do.

## Analyse: evidence and beliefs

Open the Analyse phase with the BN view active. Each node shows **belief bars** — the posterior probability of each state. Click a state's bar on a node (or use the inspector) to **observe** it as evidence; beliefs update across the whole network. The observed node is badged, and the inspector shows the full posterior with a faint marker for the prior. Clear evidence on a node or clear the whole scenario at any time.

## Readiness

The Formalise → Analyse gate turns green once every BN node has a state space and a complete, normalised CPT. Until then the inspector lists what's missing.
""",
    ),
    HelpTopic(
        id="analyse-configure",
        title="Configure Mode",
        category="analyse",
        summary="Review and apply model-specific attribute suggestions.",
        body="""## What Configure mode is for

Configure mode helps fill the attributes required by selected formal views. Examples include CLD polarity, FCM weights, and formal-view mapping decisions.

## Sources

Suggestions can come from:

- Data.
- References.
- AI.
- Manual entry.

## Review pattern

1. Fetch suggestions from a source.
2. Review each proposal.
3. Accept, dismiss, or edit before applying.
4. Batch-apply accepted changes.
5. Re-check readiness.

## Important rule

Suggestions are not automatically trusted. Treat them as drafts that need human review, especially when the result affects report claims or decision recommendations.
""",
    ),
    HelpTopic(
        id="analyse-table",
        title="Analyse Table",
        category="analyse",
        summary="Bulk review model-specific attributes across edges and views.",
        body="""## What the Analyse table is for

The Analyse table is a dense review surface for model-specific attributes. It is useful when you need to verify many edges or compare values across the model.

## Common checks

- CLD edge polarity.
- FCM edge weights.
- Per-element maturity (proposed/reviewed/approved) and per-cell verification state.
- Missing values that block readiness.
- Attributes that need evidence.

## Practical workflow

Use Configure to generate or stage values, then use the Analyse table to scan for gaps and make final corrections.
""",
    ),
    HelpTopic(
        id="interpret-findings",
        title="Interpret Phase",
        category="interpret",
        summary="Turn analysis results into structured findings, claims, and report-ready prose.",
        body="""## What Interpret does

Interpret converts model structure, analysis results, evidence, provenance, and your recorded observations into narrative sections. These sections answer the project foundation and prepare material for reports. Observations you record in the Analyse phase feed the matching section's claims by category.

## Typical sections

- Structural summary.
- Key findings.
- Sensitivity and robustness.
- Assumptions and limitations.
- Evidence gaps.
- Evidence coverage.
- Answer to the project question.
- Implications and interventions.
- Confidence assessment.
- Open questions and next steps.

## A model of several types

When a model is several types at once (a loop map with a simulation and a network on the same map), the reader-facing sections — the answer, implications, confidence and open questions — are **one set for the whole model**: their claims pool every type's, each labelled by where it came from ("Simulation: …", "Network: …"). The technical sections (structure, key findings, sensitivity, assumptions, evidence) stay one per type, and describe only that type's own factors and links. When a model gains a second type, any answer already written is kept as the model-wide answer (earlier versions stay in its history).

## Workflow

1. Initialise or refresh interpretation sections.
2. Refresh claims from current project state.
3. Generate prose for each section.
4. Edit prose where needed.
5. Use the generated sections in Communicate.

## How the claims are counted

- **Evidence coverage** counts links (the model's claims) that have at least one source; factors aren't counted.
- **Intervention points** are factors many causal paths run through. The outcome the model explains is left out once it's marked: `latris view role cld "<factor>" outcome`.
- **Feedback loops** are counted as mechanisms: two cycles that differ by one alternative step count once.

## Keep it current

If the model changes after prose is generated, refresh claims and regenerate affected sections before exporting.

In client and publication reports the answer, implications and confidence come first.
""",
    ),
    HelpTopic(
        id="communicate-story",
        title="Story (public-facing)",
        category="communicate",
        summary="Tell the model's answer to its question to one audience, as a scrolling page anyone can read.",
        body="""## What a Story is

A Story is a scrolling web page that answers the project's question for one audience: what the model found, how it works, what it can't tell them yet, and what it means for them. As the reader scrolls, the model's diagram highlights what each part is about. It sits alongside the formal Report and the audit-facing Review Pack.

A project can have **several stories**: a council briefing, a community explainer, a board summary. Each has its own audience, purpose and voice. All of them answer the same question from the same model. They can differ in what they emphasise and how they say it, but not in what they claim.

## How it works

1. **Start a story** with who it's for, what it should achieve, a voice (conversational, formal, executive or technical) and a depth.
2. **Plan the outline.** The AI proposes a one-sentence answer to the question (the *short answer*) and the beats that tell it. Each beat has a purpose and draws on things the model has recorded: its interpretation, findings, feedback loops and analysis results. You can add a steer ("lead with the cost to tourism"). A steer changes the framing, not the facts.
3. **Correct the outline.** Reorder, retitle, change what a beat draws on, choose its picture, add or remove beats, rewrite the short answer. A beat you change is kept when you re-plan.

   Each beat has one picture, drawn from what it cites: the whole model with the beat's factors highlighted; just those factors on their own; a causal path or feedback loop drawn link by link as the reader scrolls; or a chart of an analysis result (a simulation over time, how sure the model is, which option is better), drawn as the reader scrolls. A picture needs its source: a path picture needs a cited path or loop, a chart needs a cited result.
4. **Approve the outline**, then **write the story**. The AI writes each beat from what it draws on, with the whole story in view. You can rewrite any beat in your own words; the AI never replaces them.
5. **Preview** the page as a reader will see it, and **export** it as one self-contained HTML file.
6. **Share it by link.** In the story's settings, *Share by link* gives a link anyone can open, with no account needed. It works the same for everything in Communicate (see *Communicate* in the workflow help).

## Staying honest

- The story says only what the model says. A number that isn't in a beat's sources is flagged.
- Every story includes what the model **can't** tell the reader yet.
- If you change a beat's plan after it was written, its prose is marked out of date.
- Stories are versioned with the rest of the project, so you can always see what was told, from which version of the model.

## What it is not

A Story is curated for its audience and may leave out detail, for confidentiality or to fit the reader. The Report and Review Pack carry the full evidence.

Stories are made in the Latris app.
""",
    ),
    HelpTopic(
        id="communicate-explorer",
        title="Explorer (interactive model)",
        category="communicate",
        summary="Hand someone the model itself, as a page they can click through, with the reasoning and sources behind it.",
        body="""## What an Explorer is

An Explorer is one of your models as an interactive web page. A Story tells the reader what the model says; an Explorer lets them look for themselves. It works for every model type.

On the page a reader can:

- **Hover** over a factor or a link for a summary, and see what it connects to.
- **Click** anything for its description, why it is there, how confident the model is in it, whether a person has reviewed it, and what supports it.
- **Trace** what drives a factor and what it drives. Where links have a direction, they can follow a change: if this goes up, what goes up, what goes down, and what depends on how strong the links are.
- **Light up a feedback loop** from the list of loops.
- **Highlight** the links with no source yet, the disputed ones, and anything proposed by AI that nobody has reviewed.
- **Read the results** the model has recorded, as charts and tables.

## Trying things on a Bayesian network

When the model is a Bayesian network and the page carries *Everything*, a reader can also work the model:

- **Click a state** to say it has been seen. Every factor's probabilities update at once, with a mark showing where each stood before.
- Choose **We see this** (an observation, which also tells you about its causes) or **We make it so** (an intervention: what follows responds, its causes stay as they were).
- Say **how sure** they are of an observation, from 50% to 100%.
- Switch between the model's saved **options** and see what each changes.
- Keep one factor **in view**, and see **what to find out next**: the other factors ranked by how much knowing them would tell you about it.
- See **the most likely explanation**: the single most likely state of everything at once.

The numbers are calculated in the page from the model's own probability tables, and give the same answers as Latris itself. The page opens where the model's latest recorded query stands.

## Trying values on a simulation

When the model is a system-dynamics model and the page carries *Everything*, a reader can run it themselves:

- **Move a value.** Every constant has a slider, over the range you gave it as its uncertainty (or half to one and a half times its value if you gave none). So does each stock's starting value. The graph redraws as they drag.
- **Read the graph.** Any stock, flow or variable over time, with the model as you built it as a dashed line behind it, and where it ends up compared with that. It opens on the model's outcome.
- Switch between the model's saved **scenarios**, and carry on from one.
- **Put it back**, one value or all of them.

The page simulates from the model's own equations, and is tested against Latris's own runs.

## Trying things on the other model types

At *Everything*, these also recalculate in the page as the reader changes something, each shown against the model as you built it:

- **Multi-criteria analysis**: move how much a criterion counts. The others keep their proportions, the options are re-ranked, and marks on each slider show where the top choice would change.
- **Fuzzy cognitive map**: hold a factor at a level and see what moves.
- **Decision tree**: change the odds, a payoff or a cost along the way, and see the best choice and the plan that follows.
- **Event tree**: change the odds at a step, or how often it starts, and see how it ends.
- **Competing hypotheses**: set a piece of evidence aside and see which hypothesis leads, and which evidence the lead rests on.
- **Fault tree**: change how likely a basic event is, from never to certain, and see the top event, what drives it and the ways it can happen.
- **Bow-tie**: change how often a barrier fails or a threat arises, and see how often the top event and each consequence follow.
- **Markov cohort model**: change a chance of moving, a state's cost or quality of life, or what an outcome is worth paying, and see each strategy's cost and outcome and which is the best value.

Other model types show their picture, their reasoning and sources, and their recorded results.
- **Copy a link to what they are looking at**, so a colleague opens the same view.

## Making one

1. In Communicate, choose **Explorer** and **New explorer**. It is made for the model you have open.
2. Try it in the preview: it is exactly the page your readers get.
3. Give it a heading and a line or two on what to look for.
4. **Share it by link**, or **download the page**. The link opens the explorer for anyone who has it, with no account needed, and always shows the current model. The download is one file that works offline: send it to colleagues or put it on your own website.

## What leaves the building

You decide what the page carries:

- **Structure**: the picture, descriptions, confidence and review status.
- **Results**: also the model's recorded results.
- **Everything** (the default): also the model's own numbers, so readers can try their own what-ifs where the model type supports it. Anyone who has the file can read those numbers, so choose a lower level for a confidential model.

**Show sources** is on by default: readers see what each link cites, whether the source was checked, and the passage that was quoted. The text you stored from a source never leaves.

## A snapshot

The page is stamped with the date it was made and the version of the model it came from. A downloaded file does not change when the model does: download it again after you update the model. A shared link redraws itself from the current model.

Explorers are made in the Latris app.
""",
    ),
    HelpTopic(
        id="communicate-reports",
        title="Report Builder",
        category="communicate",
        summary="Assemble report sections and export Markdown or Word deliverables.",
        body="""## What Report mode is for

Report mode assembles project material into exportable documents. It combines project data, model structure, provenance, evidence, findings, and Interpret-phase prose.

Reports are per-formalism: the report is scoped to the formalism chosen in the process stepper. The model structure, findings, and interpretation are filtered to that formalism's view; project-level material (evidence, references, history) is shared. Each formalism remembers its own section selection, voice, and depth.

## Section types

- Foundation.
- Nodes and edges.
- Evidence and references.
- Assumptions, decisions, questions, exclusions, predictions, sign-offs, and sessions.
- Challenges and findings.
- Datasets and data actions.
- Milestones.
- Methods and foundations — the established methods the model relies on, each cited with its source and stated limits, generated from the foundations registry so it cites only methods the report actually used.
- Interpret-generated prose sections.

## Export formats

Use Markdown for transparent text output and Word for stakeholder-ready documents. The Markdown report opens with a Mermaid sketch of the model, which GitHub and most chat tools draw as a diagram. **Build spec (.json)** exports the model itself — factors, links, sources, the model type's values and its analyses — as `latris export spec` does; `latris build --spec` (or a chat with the Latris connector) rebuilds it elsewhere.

## Ready to share?

With no report section selected, Communicate's inspector shows **Ready to share?** — what's left before the model goes to a board: links with no source, citations nobody has checked, sources with nothing on file showing they were read, findings waiting for approval, report sections unwritten or out of date, results computed before the model last changed, model types with no recorded reason, a type's own check, and broken references between files. Each item says what to do; its link takes you to the place to do it, with the factors and links concerned selected (or, for a source, References with that source open). Check a citation under the link's **Citations** with **Check…** — what the source says, a passage copied from it, and whether it supports the claim, argues against it, is off topic or too short to tell — or remove it there. Save the passage you read of a source with **Save what you read…** in References; a check's quote is looked up in it. Broken references between files have a **Remove leftover rows** button. Once nothing is left, record a **sign-off** (your role, and what you're signing off). A factor's or link's **Maturity** (proposed, reviewed, approved) is set in its inspector; approving asks for your role and records a sign-off too. The arrow into Communicate is the same check: green once the list is empty, amber while anything is left. From the command line: `latris check handover`.

## Importing a build spec

**Import a build spec** (command palette, or the link in the Export dialog) builds a spec — YAML or JSON — into the open project. Factors, links and sources the project already has are used as they are; the spec only fills what they lack (an empty description, a missing polarity or weight). Before anything changes you see what it would add, what it found already there, what it would change and which analyses it would run and record — or why it can't be built. Import makes it one commit. From the command line: `latris build --spec FILE --reuse`, with `--dry-run` for the same preview.

## Practical advice

Generate interpretation sections before relying on them in the report builder. Report mode can show that a section exists but has not yet been generated.
""",
    ),
    HelpTopic(
        id="communicate-diagrams",
        title="Diagram Export",
        category="communicate",
        summary="Create diagram-oriented outputs for reports, review, and external communication.",
        body="""## What Diagram mode is for

Diagram mode focuses on graphical output from the current model or view. It is useful for communication, audit packs, and review material.

## What diagrams show

Diagrams represent the model structure and selected view semantics where available. For example, CLD diagrams can label edge polarity.

## When to use it

Use diagrams when stakeholders need to inspect structure visually. Use reports when they need the surrounding reasoning, evidence, and provenance.

## Sharing a diagram by link

On the Diagram tab, *Share by link* gives a link to a page showing the model's diagram as the report draws it, under the project's name and question. Anyone with the link can open it, with no account needed. Each model type has its own link.
""",
    ),
    HelpTopic(
        id="review-pack",
        title="Review Packs",
        category="communicate",
        summary="Export a self-contained HTML file for external review, then import structured feedback.",
        body="""## What a Review Pack is

A Review Pack is a self-contained HTML file for domain experts, clients, auditors, or peer reviewers. They can open it in a browser, add structured feedback, save the reviewed file, and return it.

## Exporting

In the Communicate phase, choose the Review view and export a Review Pack. The pack is scoped to the formalism chosen in the process stepper: its diagram, findings, and interpretation cover only that formalism's view. The pack contains model summary material, diagram content, and review controls.

## Sending a link instead of a file

On the Review tab, *Share by link* gives a link to the same pack as a web page. Your reviewer opens it, adds their feedback, saves their copy from the page and sends you that file to import. Anyone with the link can open the pack, with no account needed, so send it only to the people you want reviewing. Each model type's pack has its own link.

## Per-formalism scope

The review session records which formalism was reviewed. Returned feedback (challenges, questions, sign-offs) still attaches to the shared substrate elements it targets — a sign-off of the CLD view records that scope, but a challenge against a shared node remains a challenge against that node.

## Reviewer workflow

1. Open the HTML file in a browser.
2. Add project-level, node-level, or edge-level feedback.
3. Choose the feedback type: challenge, question, or sign-off.
4. Enter reviewer identity and role.
5. Save the reviewed file.
6. Send the saved file back.

## Importing

Import the returned Review Pack from the Communicate phase. Latris extracts feedback into provenance records, including challenges, questions, and sign-offs.

## Version drift

If the project changed after the pack was exported, Latris warns that reviewer comments may refer to an older model state.
""",
    ),
    HelpTopic(
        id="evidence-claims",
        title="Evidence and Claims",
        category="evidence",
        summary="How references and datasets support specific model attributes.",
        body="""## Evidence is claim-level

Latris does not treat a reference as evidence for an entire node or edge by default. Evidence attaches to specific attributes.

## Examples

- A report supports a node description.
- A paper supports an edge direction.
- A dataset statistic supports a confidence judgement.
- Expert elicitation supports a polarity or weight.

## Audit axes on evidence

Each evidence link carries four orthogonal axes so a reviewer can answer four separate questions about it:

- **Who proposed it?** `verified_by`: human or ai.
- **What did the proposer see?** `source_access`: title only, abstract, full-text chunk, or full text.
- **Does the source actually support the specific claim?** `support_verdict`: unverified, supports, contradicts, orthogonal, or insufficient extract — the result of someone reading it.
- **Is it offered for the claim or against it?** `stance`: for or against. Citing a source as against a claim (`--contradicts`) sets the stance; it stays unchecked until someone reads it.
- **Where exactly?** `quote` plus `quote_location` (chunk hash, page, offset), and `quote_verified`: whether the quote was found in the text held for the source.

A single ai-verified or human-verified badge conflated these — an AI-suggested link with no source access could read as if it had been verified against the paper. The split makes the difference visible.

## Evidence against a link

A source that argues against a claim goes on the same link, marked as contradicting: `latris evidence add <link> polarity <bibkey> --contradicts` (or `contradicts: [<bibkey>]` on a link in `latris build --spec`). It doesn't count toward evidence coverage. Reports list it as **against**, a "Contested links" section shows each disputed link's sources for and against (with any open challenge on it), and the confidence and open-questions claims name the disagreement. A challenge is different: it's a person disputing something, and it can stand alongside contradicting sources.

## Why this matters

A defensible model needs to show which exact claim is supported and who accepted it. Broad evidence lists are weaker than targeted evidence links.
""",
    ),
    HelpTopic(
        id="provenance-records",
        title="Provenance Records",
        category="provenance",
        summary="Use assumptions, decisions, questions, exclusions, predictions, sessions, and sign-offs to make reasoning auditable.",
        body="""## What provenance records capture

Provenance records explain the reasoning around the model, not just the model structure.

## Record types

- **Assumptions:** things treated as true for modelling purposes.
- **Decisions:** unforced choices such as scope or modelling judgement calls.
- **Questions:** unresolved issues for later review.
- **Exclusions:** deliberate out-of-scope items.
- **Predictions:** expected observations if the model is right.
- **Sessions:** workshops, interviews, or elicitation activities.
- **Sign-offs:** formal review approvals.
- **Challenges:** arguments against a model element or claim.

## Best practice

Record why a choice was made, what it affects, and who was involved. This makes exports more credible and reduces the burden of reconstructing decisions later.

## Removing things keeps the history

Removing a node or link also removes what describes it — its description, confidence, polarity, citations, parameter values, roles and mappings — in the same change. Challenges, questions, sign-offs, assumptions, decisions and findings about it are kept: they are the record of what was argued and approved.

`latris check integrity` checks that every reference between the project's files resolves: no link to a missing node, no citation of a source that isn't in the library, no two nodes with the same name, no duplicate links. The handover check includes it. `latris check integrity --fix` clears rows left behind by older removals or hand edits.
""",
    ),
    HelpTopic(
        id="challenges",
        title="Challenges",
        category="provenance",
        summary="Challenge model elements and record the outcome instead of burying dissent.",
        body="""## What challenges are for

Challenges capture counterarguments, doubts, alternative explanations, or review objections against a node, edge, or attribute.

## Typical outcomes

- Retained unchanged.
- Retained with caveat.
- Modified.
- Split.
- Removed.
- Unresolved.

## Why use them

Challenges make the review process visible. A model is stronger when important links have survived explicit challenge or carry clear caveats.

## AI-assisted challenge

The AI can help draft challenges or counterarguments, but the result should be reviewed and resolved by a human before relying on it in outputs.
""",
    ),
    HelpTopic(
        id="ai-assistance",
        title="AI Assistance",
        category="ai",
        summary="How Latris uses AI for proposals, review, citations, interpretation, and report drafting.",
        body="""## AI role

AI in Latris is a drafting and review assistant. It can propose model structure, citations, challenges, evidence gaps, peer-review comments, interpretation prose, and report sections.

## Review contract

AI output should pass through preview and approval before it changes project state. Accepted AI contributions are recorded so later reviewers can see where AI was involved.

## Bring your own key

The backend uses a provider-agnostic AI layer. API keys are managed outside the project content and are not committed into the model.

## Good use cases

- Draft candidate nodes and edges.
- Suggest missing connections.
- Challenge a relationship.
- Suggest citations for a claim.
- Identify evidence gaps.
- Draft interpretation prose from accepted findings.

## Human responsibility

The modeller remains responsible for accepting, editing, or rejecting proposals. Treat AI as a source of candidate work, not as an authority.

## AI agents using the command line

When an AI agent (such as Claude Code) runs `latris` commands, Latris recognises it and records what it adds as AI-proposed. Each change it saves notes the agent. Approvals, reviews, sign-offs and resolved challenges are a person's judgement: the agent records one only when you have reviewed the item yourself and asked it to, and the change history says it was recorded on your instruction. This catches the ordinary case; it can't stop an agent that sets out to hide itself. Approve in the Latris app when you need an approval that only you could have made.
""",
    ),
    HelpTopic(
        id="ai-checkpoints",
        title="When the AI asks you",
        category="ai",
        summary="Five checkpoints where an AI building a model stops and asks the person, and how skips show in the report.",
        body="""## Why it asks

An AI building a model for you — in a chat with the Latris connector, or running `latris` commands — knows the sources but not your situation. So at each phase of the workflow it stops at a **checkpoint** and asks you a few specific questions, built from the model it has so far:

1. **Framing** (before building) — what's happening and the decision the model informs, who will read it, and what you expect the answer to be.
2. **Structure** (Build → Formalise) — the factors it has mapped: is anything missing, which of them can you change, and is its least-supported link right?
3. **Values** (Formalise → Analyse) — the few estimates the answer depends on most (found by sensitivity analysis): are they right?
4. **Surprise** (Analyse → Interpret) — the result next to what you expected: does it match what you see?
5. **Audience** (Interpret → Communicate) — the reader the report is for, and what they'll push back on.

At most three questions at a time. Nothing is blocked: the AI can carry on without you, but only by saying so.

## What gets recorded

Your answers are recorded in your words, with the agent that relayed them (`latris checkpoint record`). If you tell the AI to carry on alone, it records the skip and why (`latris checkpoint skip`), or — if you say "just build" — stops asking for the rest of the model (`latris checkpoint pace just-build`). Answers are not a sign-off; approving the model is a separate step.

The report's **What the person reviewed** section lists each checkpoint: what you said, what was skipped and why, and what was never asked. A reader can tell a model you shaped from one the AI built alone.

## When it applies

Only to models an AI built: when most factors were added by a person, no checkpoint opens. A person at a terminal isn't prompted; `latris checkpoint show` lists the checkpoints and the one open now. A reviewed structure opens again if the AI later grows the map a lot.
""",
    ),
    HelpTopic(
        id="model-types-overview",
        title="Choosing a Model Type",
        category="model-types",
        summary=(
            "How to choose between CLD, DAG, FCM, BN, SD, Theory of Change, Fault Tree, Bow-Tie, Event Tree, "
            "and planned formal views — by the question each one answers."
        ),
        body="""## Current stable model types

- **CLD:** best for feedback systems and reinforcing or balancing loops.
- **DAG:** best for causal direction, dependencies, and acyclic reasoning.
- **FCM:** best for semi-quantitative influence modelling with weights.
- **BN:** best for quantitative probabilistic reasoning over an acyclic causal subgraph (discrete state spaces + CPTs with per-cell provenance). See the dedicated Bayesian Networks topic.
- **SD:** best for how a system with accumulation, delay, and feedback behaves over time — stocks, flows, unit-checked equations, and deterministic simulation. See the dedicated System Dynamics topic.
- **Theory of Change:** best for programme and policy logic — how an intervention's activities are expected to lead, step by step, to its impact, and what evidence and assumptions hold each step up. See the dedicated Theory of Change topic.
- **Fault Tree:** best for how an undesired event can happen — the combinations of failures that cause it, single points of failure, its probability and which failures matter most. See the dedicated Fault Trees topic.
- **Bow-Tie:** best for showing, for one top event, what could cause it, what could follow, and the barriers in between — where the protection is thin, shared or uncontrolled, and (with frequencies and failure probabilities) how often each outcome is expected. See the dedicated Bow-Ties topic.
- **Event Tree:** best for following one initiating event forward — which safety functions work or fail, in what order, and how often each end state results. See the dedicated Event Trees topic.
- **MCDA:** best for a choice between options judged on several criteria — the ranking, what drives it, and how far the weights would have to move to change it. See the dedicated Multi-Criteria Decision Analysis topic.
- **ACH:** best for choosing between competing explanations — which one the evidence fails to rule out, and which pieces of evidence the conclusion turns on. See the dedicated Analysis of Competing Hypotheses topic.
- **Decision tree:** best for a choice whose outcome depends on chance — the best strategy by expected value, what knowing each uncertainty first would be worth, and the probabilities at which the choice flips. See the dedicated Decision Trees topic.
- **Markov model:** best for what happens to a group over time — moving between states such as well, ill and dead — and what each strategy costs and achieves, with cost-effectiveness (ICERs, net benefit). See the dedicated Markov Cohort Models topic.

## Which factors are in which model type

A model can be several types at once. Every factor and link is in every chosen type unless you leave it out: select a factor or link on the Build canvas and untick a type under **In these model types** (with a reason, if it helps the reader). It stays out — opening the type doesn't put it back — and a factor's links leave with it. Tick it again to put it back. Each type's report covers what's in it. From the command line: `latris mapping leave-out <factor> <type> --reason "..."` and `latris mapping add <factor> <type>`.

## Planned model types

On the roadmap: influence diagrams (for decisions), argument maps, and Goal Structuring Notation (for safety cases) once argument maps exist. Causal identification is being folded into the DAG view rather than offered as a separate model type.

Other registered types — regression (effect estimation ships as an analysis on DAGs instead: `latris analyse estimate`), fishbone diagrams, flowcharts, state machines and Petri nets — are not currently planned. Any type is admitted only if its reasoning stays inspectable; Monte Carlo / PSA is an analysis layer over parameterized models, not a model type of its own.

## How selection affects the app

Selected model types drive readiness checks, Configure suggestions, Analyse views, and report content. Choose the model types that match the question, not every possible view.

## By the question they answer

- "How does this work — what feeds back on what?" → **CLD**. The cheapest
  honest answer; start here unless the question says otherwise.
- "Can this effect actually be estimated, and from what data?" → **DAG**.
  Adjustment sets and d-separation; with a dataset, the effect size under
  the DAG's stated assumptions (`latris analyse estimate`).
- "How likely is each outcome, and what would change my mind?" → **BN** —
  discrete states and probabilities.
- "Which forces dominate, roughly?" → **FCM** — semi-quantitative weights
  and steady-state tendencies.
- "How will it behave over time if we intervene?" → **SD** — the most
  commitment; build the CLD first.
- "How is this programme supposed to work, and which steps are we taking
  on trust?" → **Theory of Change** — a results chain from activities to
  impact, link by link against the evidence.
- "What combinations of failures cause this, and how likely is it?" →
  **Fault Tree** — gates down to basic events; cut sets, probability and
  importance.
- "What stands between this hazard and harm, and where is it thin?" →
  **Bow-Tie** — threats, barriers and consequences around one top event.
- "Once this happens, how does it play out, and how often does it end
  badly?" → **Event Tree** — yes/no headings from one initiating event to
  end states.
- "Which option should we choose, given what we care about?" → **MCDA** —
  options scored against weighted criteria, and how firm the choice is.
- "Which explanation does the evidence fail to rule out?" → **ACH** —
  competing hypotheses rated against every piece of evidence.
- "What should we do, given what we don't know — and is it worth finding
  out more first?" → **Decision tree** — expected values and the value of
  information.
- "What does each option cost and achieve over years, and is the better one
  worth its price?" → **Markov model** — a cohort moving between states,
  with cost-effectiveness.

One substrate carries across: factors, links, evidence and challenges all
stay when you quantify a CLD as FCM/BN/SD later — nothing is redrawn, and
`latris project select-models` records the choice with its rationale.
Triangulating (a CLD plus a DAG on the same substrate) is a strength, not a
mistake. The fuller guide: https://latris.app/formalisms/ — and the methods
behind each formalism, with limits, in docs/FOUNDATIONS.md.
""",
    ),
    HelpTopic(
        id="model-type-bn",
        title="Bayesian Networks (quantitative)",
        category="model-types",
        summary="Discrete BN inference with hard and soft evidence, the most likely explanation, Monte Carlo over the tables, learning and sensitivity — with per-cell provenance.",
        body="""## What a BN adds

A Bayesian Network quantifies an acyclic causal subgraph: every node gets a discrete **state space** and a **conditional probability table (CPT)** giving P(node | parents). You can then compute marginals and posterior queries — reasoning forwards (predictive) and backwards (diagnostic).

## The distinctive bit: per-cell provenance

Every CPT row carries its own provenance — `origin` (human-direct, human-elicited, data-derived, ai-proposed), `verification`, `source`, and who contributed. Different rows in one table can come from different sources (an expert, a dataset, a default), and the model shows where each number came from. No incumbent BN tool does this.

## Working with a BN (the `latris bn` commands)

- **`latris bn set-state-space <node> <states>`** — declare a node's discrete states (`--ordered` for ordinal).
- **`latris bn set-cpt <node> --parents … --probs …`** — fill a CPT (with `--origin`/`--source`).
- **`latris bn set-noisy-or <node> -c "<parent>=<state>:<prob>" --leak …`** — a *canonical model* for high-fan-in binary nodes: each cause contributes independently, so k causes need k probabilities + a leak instead of 2^k rows.
- **`latris bn set-weighted <node> --base 0.02,0.98 -w "Bloom=severe:3" -w "Barrier=failed:2.5"`** — a full table from a base distribution and a weight per parent state (logits; ±1 moderate, ±3 strong), for many-state parents where Noisy-OR doesn't fit. Every weight 0 gives the base in every row; a two-state node is logistic regression; `--toward` picks which end positive weights push to.
- **`latris bn remove-states <node>`** — take a factor out of the network (its states and table go; it stays in the loop map).

In the editor, a selected factor's pane has **Weighted table (many-state parents)** — the base distribution and a weight per parent state — and **Take out of the network**.
- **`latris bn learn <dataset>`** — fit CPTs from data. Rows you elicited or verified are **protected**; data fills only the gaps. Learned rows are stamped data-derived and the run is logged. In the editor: Formalise → **Learn the tables from data** previews what each table would become, then **Apply to the tables**.
- **`latris bn check`** — readiness: state spaces defined, CPTs complete + normalised, acyclic.
- **`latris bn marginals` / `latris bn query --evidence … --query …`** — exact inference. Each query is recorded (`--no-record` to skip); reports show the latest one per evidence set, posterior against prior, with a chart.
- **`latris bn sensitivity <target> --state …`** — rank the parameters that move a conclusion, flagging the ones that aren't human-verified.
- **Noisy-OR** — `latris bn set-noisy-or <node> -c "Cause=yes:0.6" --leak 0.02 --active yes`: `--active` names the node's state the causes push toward; it's required unless the first state is plainly the event (yes, true, present…).
- **Interventions** — `latris bn query --set "Barrier=upgraded"` asks what follows if we *make* it so (the do-operator), not what seeing it tells us: the factor's own causes stop mattering, so its causes' probabilities don't move. Reported as "given we set …".
- **Soft evidence** — `latris bn query -s "Wet=yes:0.8"` when you're not certain: afterwards P(Wet = yes) is 80% (Jeffrey's rule) and the other states share the rest. `--likelihood "Wet=yes:4,no:1"` instead says how much an observation favours each state.
- **`latris bn explain -e …`** — the single most likely combination of states given the evidence (MPE; `--over` limits it to chosen nodes, MAP), its probability, how many times likelier each state is than its runner-up, and where a node's own favourite differs from the combination.
- **`latris bn set-uncertainty <node> --n 20`** — how well a probability table is known: "worth about n observations" (`--row "Parent=state,…"` for one row). **`latris bn monte-carlo <target> [--state s] -e …`** then re-asks the query under seeded draws of every such table and gives the point estimate, median and the range 50% / 95% of draws fall in, the tables held fixed, and which tables drive the spread.
- **Scenarios (what-ifs that don't change the model)** — `latris bn set-scenario "Barrier upgraded" --table "Bloom reaches intake[Barrier=upgraded]=0.1,0.9"` saves new probabilities for the matching rows (`"Node=0.1,0.9"` for every row, or a root's only row); `--observe "Hot week=yes"` defines a situation, `--set` an intervention, `--soft`/`--likelihood` uncertain observations, `--extends OTHER` builds on another scenario. The model's own tables are untouched, so testing an upgrade never needs an edit and a revert. Use it with `bn query --scenario NAME` and `bn monte-carlo --scenario NAME` (the scenario's overridden rows and set factors are held at its values). `bn scenarios`, `bn remove-scenario`.
- **`latris bn compare <target> --state s -S OptionA -S OptionB`** — compare options: P(target = state) under the baseline network (no scenario changes) and each scenario. `-e` evidence holds for every option (a hot week, say). With table uncertainty, every option is asked on the *same* draws of the tables, so each difference (in percentage points) is paired, with the share of draws where it is lower or higher; without, point probabilities. Each row names its reference: an option extending a compared scenario is measured against it, the rest against the baseline; `--reference` sets one for all. Recorded as an options table in the report.

## Not yet

Decision and utility nodes (influence diagrams) and EVPI, ranked nodes / Noisy-MAX, continuous/hybrid nodes, structure learning, dynamic BNs, and incumbent-format import/export (which would strip provenance) are out of scope. See `docs/design/BN_QUANTITATIVE.md`.
""",
    ),
    HelpTopic(
        id="model-type-sd",
        title="System Dynamics (stock-and-flow)",
        category="model-types",
        summary="Stocks, flows, unit-checked equations, scenarios, Monte Carlo uncertainty, sensitivity and loop dominance — with per-parameter provenance.",
        body="""## What an SD model adds

System Dynamics models how quantities accumulate and drain over time. **Stocks** (population, inventory, pollutant load) change only through **flows** (births, orders, emissions); flows and **auxiliaries** are computed from equations; **constants** are fixed parameters; a **source_sink** is a cloud outside the model boundary. Simulating integrates the model forward in time, so you can see growth, overshoot, oscillation, or collapse emerge from the feedback structure.

## How it sits on the substrate

SD uses the same entities and edges as every other view. Each SD variable is an ordinary entity with an SD **role**. Material movement uses **flow** edges, always `stock → flow → stock` (either end may be a source_sink cloud). "X appears in Y's equation" uses a **causal** edge X → Y — an information link. The SD model is whatever has an SD role plus anything a flow edge touches.

**Sharing a map with a loop map.** A factor joins the simulation when it gets an SD role (and the network when it gets states); everything else stays in the loop map. So you can quantify part of a CLD *in place*: give its key factors roles, and links from the rest of the loop map into them stay loop-map links — `sd check` lists them as advisories ("stays in the loop map"), never as gaps. In a model shared with a loop map, a causal link into a stock or one no equation uses is likewise an advisory. `sd unset-role <node>` takes a factor back out (its role and SD values go; the factor, its links and citations stay). In a model that is only a simulation, an unclassified factor feeding it is still a gap. The factor the model explains is set with `latris view role sd <factor> outcome` (kept with the SD settings, since SD roles are one per factor) and `latris sd simulate` runs it.

## Equations and units

Equations reference variables by slugified label (`Birth Rate` → `birth_rate`) plus `TIME`, using arithmetic, comparisons, and `MIN`, `MAX`, `ABS`, `IF_THEN_ELSE(cond, a, b)`, `STEP(height, start)`, `RAMP(slope, start[, end])`, `PULSE(start, width)`, `TABLE(x)`, `EXP`, `LN`, `SQRT`, `SIN`, `COS`, `MODULO(x, period)` (plus `PI`), and the delays `SMOOTH(x, T)` / `SMOOTH3` (a perceived value catching up with x) and `DELAY1(x, T)` / `DELAY3` (material arriving after a delay) — each becomes hidden stocks and flows, so units, Monte Carlo and loop dominance include them. A bare start, end, width or delay time is in the model's time units. **Seasons**: a yearly model can still have a seasonal cycle — set a step shorter than the cycle (`sd set-settings --dt 0.02` is about weekly) and drive it with `1 + amplitude * SIN(2 * PI * TIME / one_year)` (`one_year` a constant of 1 year), or a lookup over `MODULO(TIME, one_year)` (the time within each year). Every stock, constant and equation declares its **units** (pint syntax: `liter`, `person/year`, `1/year`, `dimensionless`; `person`, `dollar` and `item` are built in). Values are evaluated as unit-bearing quantities, so adding litres to people, or a flow whose units aren't its stock's units per time unit, is caught as an error rather than producing a wrong number. Equations have no unit literals — give a unit-bearing number its own named, sourced constant. An equation that is just a bare number (`3`) takes its declared units.

## Working with SD (the `sd` commands)

Each is `latris sd …` on the command line (e.g. `latris sd check`, `latris sd simulate --scenario NAME`); the chat connector and the editor call the same operations.


- **`sd set-role <node> <role>`** — stock, flow, auxiliary, constant, or source_sink.
- **`sd set-settings --time-units month --final-time 36`** — the model's clock and run settings, stored with it (every run, and anyone opening a link, uses them; options on a run override). If the flows are per month but the clock runs in years, every run and `sd check` warn. **`latris view role sd <node> outcome`** marks what the model explains.
- **`sd set-initial-value <stock> <value> --units …`** — a stock's starting value (`--non-negative` warns if a run drives it below zero).
- **`sd set-constant <node> <value> --units …`** and **`sd set-equation <flow|aux> "<expr>" --units …`** — each with `--origin`/`--source` provenance.
- **`sd set-table <node> -p x:y -p x:y … --x-units … --y-units …`** — a piecewise-linear lookup the node's equation calls as `TABLE(x)`; typically elicited from experts as a curve.
- **`sd check`** — readiness: classification, stock-flow plumbing, no algebraic loops among flows/auxiliaries, equations match the diagram's links (no hidden or unused dependencies), values and tables present, and full dimensional consistency.
- **`sd simulate`** — a deterministic run (`--final-time`, `--dt`, `--saveper`, `--method euler|rk2|rk4|adaptive`, `--time-units`). `--scenario NAME` (repeatable) and `--set "Variable=value [units]"` add what-ifs, each compared with the baseline (end, peak, change). The result is recorded and shows in reports; `--json` prints the full series.
- **`sd set-scenario NAME --set "Variable=value [units]" …`** — a named what-if saved with the model, with `--description`, `--reason`, `--source`. Values replace constants or initial values and are unit-checked (a delay in years can be set as `6 month`, not `6 person`). `--extends OTHER` builds on another saved scenario: its values apply first and this one's on top, so "Programme delayed 1 year" can extend "Programme" and change only the start year. `sd scenarios`, `sd remove-scenario` (a scenario others extend can't be removed until they are).
- **`sd set-uncertainty <node> <distribution> …`** — how uncertain a constant or initial value is, in its own units: uniform (`--min --max`), triangular (`--min --mode --max`), normal/lognormal (`--mean --sd`, optional `--min/--max` truncation), beta (`--alpha --beta`, scaled to min..max), gamma (`--shape --scale`); with `--reason`/`--source`/`--origin`. `sd uncertainty`, `sd clear-uncertainty`.
- **`sd monte-carlo`** — samples every value that has a range (Latin hypercube by default, `--seed` for repeatability, `--runs` up to 1000) and reports each variable's percentile bands over time (50/75/95/100% of runs) and which uncertain values drive the spread (rank correlation).
- **`sd compare <variable> -s OptionA -s OptionB`** — options under uncertainty: the baseline (the model with no scenario changes) and each saved scenario run on the *same* sampled draws, so each difference is measured draw by draw. Gives each option's median, 95% range and central-value run, the paired difference from its **reference** and the share of draws where it is lower or higher (`--metric`, including `total`, the sum over the run). The reference is named on every row: an option that extends a compared scenario is measured against it (delayed vs undelayed — the cost of waiting), the rest against the baseline; `--reference NAME` sets one reference for every option. A delayed-sounding option measured only against the baseline, or one whose parent isn't compared, gets a warning. Each claim names the result, the metric, the reference and the world it holds in. Shown as an options table in the report.
- **`sd sensitivity <variable>`** — a tornado: each constant and initial value swung across its range's 5th–95th percentile (or ±10%), ranked by how far it moves one result (`--metric final|peak|peak-time|min|mean|total|at:T`); values with a stated range rank apart from ±10% probes, values with no effect in the run are marked inactive, and values that aren't human-verified are flagged.
- **`--apply-to-all "Variable=value"`** on `sd simulate`, `sd monte-carlo`, `sd compare` and `sd sensitivity` — values that hold in every run, the baseline included (a high-load world, say). `--set` instead adds an unsaved what-if as one more scenario.
- **`sd loops`** — which feedback loop drives the behaviour, and when (Loops That Matter, with the 2023 flow-to-stock revision): loops through the stocks and equations are scored at each step, and a loop (or the fewest loops) holding half the score dominates. Dominant loops built on unsourced or contested links are flagged. Scores are zero when the stocks stop changing — the method explains change, not equilibrium.
- **`sd roles` / `sd equations` / `sd stocks` / `sd constants` / `sd tables`** — listings (`sd roles` gives each variable's name in equations).

## In the editor

In **Formalise**, double-click the canvas for a new factor (name and role, placed where you clicked) and drag from one factor to another to link them — a flow when it joins a flow to a stock or cloud, otherwise an information link — or use **Add to the model**, and select a factor to give it a role and its equation, value or graphical function; the canvas draws it as the report does (stock box, flow valve with its equation, constant with its value, source/sink cloud), and the readiness panel lists what's missing. In **Analyse**, the pane with nothing selected runs the simulation (clock overrides and saved scenarios to compare), saves scenarios (a scenario can build on another: its values, then the new ones), and runs Monte Carlo, sensitivity and loop dominance; **Options compared under uncertainty** (under More analyses) compares scenarios on the same draws, with values that hold in every run; selecting a constant or stock sets its uncertainty, and selecting any factor shows it over the last run. Every run is recorded and appears under **Recorded results** with the report's charts. **Model clock** (Formalise, nothing selected) stores the time unit, start, end, step and method with the model (`sd set-settings`); a selected factor's **Take out of the simulation** drops its role and values, keeping it in the map (`sd unset-role`).

## Results in reports

Simulations, Monte Carlo runs, sensitivity and loop analyses (and BN queries) are recorded. Reports show the latest run of each analysis in a **Results** section — with charts in the hosted report and Word — and the interpretation's claims include what they found. Each heading says what the run was of (its scenarios, evidence or interventions) and when it ran. A result computed before the model last changed is marked out of date — and only a change to what that model type is made of counts, so editing the loop map doesn't age a simulation sharing its map. `latris results list` shows what reports use; `latris results hide <run>` leaves one out. A `latris link` carries the parameters and the analyses, and opening it recomputes the same results. An analysis that read a dataset (effect or impact estimation) can't be re-run without the data, which links don't carry, so its result travels as the sender's, and the report says it was computed by the sender and from which dataset.

## Integration methods

Once a model passes its unit check it runs on a compiled float path (identical results, many times faster), which is what makes hundreds of Monte Carlo runs practical; models with offset units such as degC use the slower unit-checked path. `euler` is fixed-step forward Euler at `dt`. `rk4` and `rk2` use scipy's adaptive Runge–Kutta (RK45 / RK23) bounded to never step past `dt` — close to, but not bit-identical with, the classical fixed-step RK4 of Vensim/Stella. `adaptive` lets scipy choose its own steps. Halving `dt`, or comparing `euler` with `rk4`, is a quick check that results aren't integration artefacts.

## Not yet

Calibration to data, arrays (subscripts), table or mid-run changes in scenarios, correlated uncertainty, strongest-path loop search for very large models (over 500 loops), AI-drafted equations, XMILE/Vensim import/export (which would strip provenance) are out of scope for now. A simulation is a scenario conditional on its assumed structure and parameters, not a forecast.
""",
    ),
    HelpTopic(
        id="model-type-cld",
        title="Causal Loop Diagrams",
        category="model-types",
        summary="Use CLDs for feedback structure, polarity, and reinforcing or balancing loops.",
        body="""## What a CLD represents

A Causal Loop Diagram is a directed graph where edges carry polarity. A positive edge means the source and target move in the same direction, all else equal. A negative edge means they move in opposite directions.

## Best for

- Feedback-rich systems.
- Policy and systems thinking.
- Explaining reinforcing and balancing loops.
- Early-stage system dynamics work.

## Required structure

A CLD must contain at least one feedback loop. Loops are the defining feature of the formalism — an acyclic directed graph is a causal map or DAG, not a CLD. Readiness for a CLD will not pass until at least one loop closes.

## Required attributes

CLD analysis depends on edge polarity. Missing polarity weakens readiness and prevents useful loop classification.

## Analysis outputs

CLD analysis can identify cycles, classify loop polarity, and support polarity propagation through paths.
""",
    ),
    HelpTopic(
        id="model-type-dag",
        title="Directed Acyclic Graphs",
        category="model-types",
        summary="Use DAGs for acyclic causal or dependency structure where direction matters.",
        body="""## What a DAG represents

A Directed Acyclic Graph is a directed graph with no directed cycles. Following arrows from any node can never lead back to the same node.

## Best for

- Causal inference framing.
- Dependency analysis.
- Workflow or process logic where cycles are invalid.
- Foundations for Bayesian networks or causal DAGs.

## Required structure

DAG views require directionality and acyclicity. Feedback loops that are valid in a CLD must be reframed, split, or excluded from a DAG view.

## Analysis outputs

DAG analysis supports path enumeration, d-separation, Markov blankets, and adjustment-set reasoning. In the editor's Analyse pane, **Identification** takes a treatment and an outcome and lists every valid adjustment set; click one to see it on the canvas. **Effect estimate** (under Analyses) estimates the effect from a dataset.

## Estimating the effect

With a dataset (`latris data add survey.csv`, or the data workspace), `latris analyse estimate Exercise "Heart health" --dataset survey` estimates how big the effect is. Factors map to columns by name (or `--column "Exercise=exercise_hours"`). Latris adjusts for the smallest valid backdoor set the dataset measures — or a set you give with `--adjust`, which it checks against the DAG — and fits linear regression with robust standard errors for a numeric outcome, or logistic regression for a yes/no one. The unadjusted association is shown beside it, so you can see what adjustment changed. If every valid adjustment set needs a factor the data doesn't have, Latris names what to measure and estimates nothing.

The estimate is the effect only if the DAG leaves out no common cause, the model's form is right, and every kind of unit could receive every level of the treatment; the output and the report say so each time. The result is recorded and goes out of date when the DAG or the data changes.
""",
    ),
    HelpTopic(
        id="model-type-fcm",
        title="Fuzzy Cognitive Maps",
        category="model-types",
        summary="Use FCMs for weighted causal influence and semi-quantitative scenario reasoning.",
        body="""## What an FCM represents

A Fuzzy Cognitive Map is a weighted directed graph. Each edge has a causal strength, commonly in the range -1 to +1. Positive values reinforce; negative values counteract.

## Best for

- Participatory modelling.
- Expert-driven scenario exploration.
- Semi-quantitative causal influence.
- Systems where feedback exists but full equations are not available.

## Required attributes

FCM analysis depends on edge weights and, for simulation, node activation settings. Missing weights reduce readiness. `latris fcm weights` lists the weights set so far.

## Commands

- **`latris fcm set-weight <edge> <weight>`** — a link's influence, from -1 (strongly opposes) to +1 (strongly drives).
- **`latris fcm weights`** — every weight.
- **`latris fcm infer`** — run the map to its steady state (which factors end up high or low); `--clamp 'Factor=1.0'` holds a factor at a value as a scenario. Each run is recorded (one result per scenario) and shows in the report and under **Recorded results**; `--no-record` only shows it. In the editor, Analyse → **Steady state** runs it, with the factors to hold picked from the map.

## Practical caution

FCM weights are judgement-rich. Link weights to elicitation, evidence, or rationale so they are not mistaken for measured parameters.
""",
    ),
    HelpTopic(
        id="model-type-toc",
        title="Theory of Change",
        category="model-types",
        summary="Lay out how an intervention is meant to reach its impact, and see which steps the evidence holds up.",
        body="""## What a theory of change represents

A theory of change is a results chain: what an intervention does (**activities**), what that directly produces (**outputs**), the changes that follow (**short-term** and **long-term outcomes**), and the long-term change it is for (**impact**). **Inputs** are the resources it uses. Every factor gets one of these levels (`latris toc level <factor> <level>`); links are ordinary causal links that run forward through the levels. The impact is the outcome of interest.

## What the check shows

`latris toc check` lays out every pathway from an activity to an impact and, for each link on one, what holds it up:

- **checked** — a source was read and found to support it;
- **cited** — it has a source nobody has checked yet;
- **untested** — no source at all;
- **contested** — a source argues against it.

A pathway is only as strong as its weakest link. The check also counts the assumptions stated for each link (`latris provenance assumption add ... --target "A -> B"`) and flags *leaps*: links that skip two or more levels (an output straight to the impact), where the steps between are left unstated. The result is recorded, so the report's Results section shows it, and it goes out of date when sources, checks or assumptions change.

## Process tracing: how far does the evidence support each link?

The check says whether a link has evidence; process tracing says how much that evidence should move you. For each link, set how confident you are before looking (`latris toc prior "A -> B" 0.6`; 0.5 if unset), then add **tests** — evidence you'd expect to see if the link holds — with two judgements: how likely you'd find it if the link holds (`--if-true`, its certainty) and if it doesn't (`--if-false`; low means the evidence is unique to the link):

    latris toc test "Mentoring -> Engagement" "attendance rises" --if-true 0.9 --if-false 0.4

Once you've looked, record the result (`--found` or `--not-found`). The test's type follows from the two numbers (Van Evera's four):

- **hoop** (certain, not unique): failing it sinks the link; passing it helps only a little;
- **smoking gun** (unique, not certain): passing it strongly supports the link; failing it hurts little;
- **doubly decisive** (both): settles it either way;
- **straw in the wind** (neither): nudges only.

`latris toc trace` updates each link from its prior through the tests carried out (Bayes' rule in odds form), gives each pathway a confidence (the product of its links, treating them as independent) and its weakest link, and ranks the tests still to run by how far they could move their link. It is recorded, so the report shows it and the interpretation's claims include it. The numbers are judgements: write down why in `--notes`, cite where the evidence was found with `--source`, and mark them `--verified` once someone has reviewed them.

## Impact: did the outcome change when the intervention started?

With data on an outcome over time (`latris data add`), `latris toc impact` estimates the change:

- **Interrupted time series** (no comparison group): `latris toc impact Attendance --dataset monthly --time month --at 2024-01-01`. It fits the trend before the start, the step at the start and the change of slope after it, and compares the last period with the pre-period trend projected forward. At least 8 periods on each side are advised; the errors are modelled as autocorrelated (AR(1)), so month-to-month persistence doesn't make the interval falsely narrow.
- **Difference-in-differences** (a comparison group): add `--group <column> --treated <value>` (repeat `--treated` for several). It compares the treated group's change with the comparison group's, after checking whether their trends were already diverging before the start. With 20 or more groups the errors are clustered by group; with fewer, it says the interval is likely too narrow.

Each check that fails or can't be made is listed as a caution with the result, and the result states what it assumes: for a time series, that nothing else changed at the same time; for difference-in-differences, that the groups would otherwise have moved in parallel. These are the designs' weak points and the data can only partly test them. The estimate is recorded and goes out of date when the dataset changes.

## Readiness

The model is ready when every factor has a level, no link runs backwards (towards activities), there is at least one activity and one impact, every impact is reached from an activity, and nothing dead-ends before the impact.

## Practical caution

The check is structural and about evidence. It shows where a theory rests on untested or contested steps — where to look first in an evaluation — not how big an effect is; for that, use the impact estimate, within its assumptions. Methods behind it: Weiss (1995) on theory-based evaluation, the W.K. Kellogg Foundation (2004) logic model, and Mayne (2012) on contribution analysis. Process tracing doesn't estimate effect sizes: it weighs evidence for each causal step, and its answer is only as good as the probabilities given. Methods: Van Evera (1997), Bennett (2015), Befani & Mayne (2014), Fairfield & Charman (2017); for impact, Wagner et al. (2002), Bernal et al. (2017) and Angrist & Pischke (2009).
""",
    ),
    HelpTopic(
        id="model-type-ft",
        title="Fault Trees",
        category="model-types",
        summary="Break an undesired event down into the failures that cause it; find cut sets, its probability and what matters most.",
        body="""## What a fault tree represents

A fault tree starts from one undesired **top event** and works down through **gates** to the **basic events** that, in combination, cause it. Each factor gets a type (`latris ft event <factor> top_event|intermediate_event|basic_event|undeveloped_event`); link each input to the event it feeds (`latris edge add <input> <event> --kind logical`, or a causal link). Every top or intermediate event has a gate (`latris ft gate`): **and** (all inputs must occur), **or** (any one is enough) or **vote** with k (at least k of them, e.g. 2-out-of-3 redundant supplies). Undeveloped events are leaves you chose not to break down further.

Only factors with a fault-tree type are in the tree, so a fault tree can share its events with a causal loop diagram. A link into the tree from an unclassified factor is left out and listed, never silently used.

## What the analysis shows

`latris ft analyse` lists the **minimal cut sets** — the smallest combinations of basic events that cause the top event — and the **single points of failure** (cut sets of one event). Give every basic event a probability (`latris ft probability <event> <p> --source <where>`) and it adds:

- the **exact top-event probability**, from a binary decision diagram, so an event that feeds more than one gate isn't double-counted (the rare-event approximation and min-cut upper bound are shown beside it);
- each event's **importance**: Fussell–Vesely (the share of the top-event probability that needs it), Birnbaum (how far the top-event probability moves between the event surely happening and surely not) and RAW (how many times likelier the top event is if it happens).

Every probability keeps where it came from; the important ones nobody has verified are flagged, so you know which numbers to check first. The analysis is recorded for the report and goes out of date when the tree or a probability changes.

## How sure is it? (Monte Carlo)

Basic-event probabilities are rarely known exactly. Give them a range — `latris ft uncertainty "Pump A fails" --median 0.01 --error-factor 3` is a lognormal whose 95th percentile is three times its median, the usual way probabilistic risk assessments state it; `uniform --min --max`, `triangular`, `beta` and others also work — then `latris ft monte-carlo`. It recomputes the exact top-event probability for each sample and gives its 5th–95th percentile, median and mean beside the point estimate (with skewed ranges the mean is higher: the point estimate is not the expected value), and ranks the uncertain events by how strongly they drive the spread. Events without a range stay fixed and are listed. Ranges are judgements too: say why with `--reason` and cite with `--source`.

## Readiness

The tree is complete when it has one top event, every top and intermediate event has a gate and inputs (and a vote gate's k fits), basic and undeveloped events have no inputs, nothing loops, and every event leads to the top event. Probabilities aren't needed to be ready — the cut sets are useful on their own.

## Practical caution

The analysis is static and assumes basic events are independent: it has no common-cause failure model, no NOT, priority-AND or sequence gates, and different events' uncertainties are sampled as independent. Methods: the NRC *Fault Tree Handbook* (Vesely et al. 1981), IEC 61025, Rauzy (1993) for the decision diagram, and Birnbaum (1969) and Fussell (1975) for importance.
""",
    ),
    HelpTopic(
        id="model-type-bowtie",
        title="Bow-Ties",
        category="model-types",
        summary="Lay out the threats and consequences of one top event and the barriers between, and see where protection is thin.",
        body="""## What a bow-tie represents

A bow-tie centres on a **top event** — the moment control of a **hazard** is lost (e.g. *loss of containment* of *flammable gas under pressure*). On the left, the **threats** that could cause it, each on a line through the **prevention barriers** meant to stop it. On the right, the **consequences** that could follow, each through **mitigation barriers**. An **escalation factor** is a condition that degrades a barrier (a detector bypassed for maintenance); its own line runs through the barriers that control it.

Give each factor its element (`latris bowtie element <factor> hazard|top_event|threat|consequence|barrier|escalation_factor`) and draw the lines with ordinary links: threat → barrier → … → top event → barrier → … → consequence, and escalation factor → control → … → the barrier it degrades. Only factors with a bow-tie element are in it; a link from anything else is listed and left out.

## Barriers

Each barrier can carry its **type** (passive hardware, active hardware, active hardware + human, human — the CCPS types), its **status** (in place, degraded, not in place), its **owner**, and its **probability of failure on demand**, with where that number came from (`latris bowtie barrier <barrier> --type … --status … --owner … --pfd … --source …`). Only what you give changes.

## What the analysis shows

`latris bowtie analyse` lists every line with its barriers and flags:

- lines with **no effective barrier**, and lines resting on **one** (a degraded or missing barrier doesn't count);
- barriers on **more than one line** — one failure takes them all;
- escalation factors with **no control**, and barriers with **no owner**.

Give every threat a frequency per year (`latris bowtie frequency <threat> <f> --source …`) and every barrier on a line a failure probability, and it adds a layer-of-protection estimate: the top event's frequency, each consequence's, and for each barrier how many times more often its side's outcome would happen if it always failed (RAW). A barrier on two routes from the same threat is counted once. The important values nobody has verified are flagged. The analysis is recorded for the report and goes out of date when the bow-tie or a value changes.

## How sure is it? (Monte Carlo)

Give barrier failure probabilities and threat frequencies a range (`latris bowtie uncertainty "Pressure relief valve" --median 0.01 --error-factor 10`, or `uniform --min --max` and other distributions), then `latris bowtie monte-carlo`: the top event's and each consequence's frequency as a 5th–95th percentile range, median and mean beside the point estimate, and which ranges drive the spread. A barrier on several lines takes one value per run everywhere it appears, as it should.

## Readiness

Complete when there is one top event, at most one hazard (linked to the top event), at least one threat and one consequence each on a line, every barrier on a line, every escalation factor linked to the barrier it degrades, and no link that breaks the pattern or loops.

## Practical caution

The quantification is LOPA's: order-of-magnitude and barriers assumed independent; values are points unless given a range for Monte Carlo. Escalation factors are not quantified, and there is no severity scale or risk matrix. The left side of a bow-tie is often a fault tree: a threat's frequency can cite a fault-tree analysis as its source. Methods: CCPS & Energy Institute (2018) *Bow Ties in Risk Management*, and CCPS (2001) *Layer of Protection Analysis*.
""",
    ),
    HelpTopic(
        id="model-type-et",
        title="Event Trees",
        category="model-types",
        summary="Follow one initiating event forward through yes/no headings to end states, with the probability of each.",
        body="""## What an event tree represents

An event tree starts from one **initiating event** (a gas release) and asks, in order, a series of yes/no questions — the **headings** or functional events (*Gas detected?*, *Isolation succeeds?*, *Ignition?*). Each complete path of answers is a **sequence**, and each sequence ends in an **end state** (*contained release*, *fire*, *gas cloud dispersed*). A branch need not ask every heading: once isolation succeeds, ignition may not matter.

Give each factor its element (`latris et element <factor> initiating_event|functional_event|end_state`), set the heading order (`latris et order <heading> …`), then add each sequence with its answers and end state (`latris et sequence Fire "Gas detected=no" "Ignition=yes"`). The tree isn't drawn with links: one heading is asked on many branches, so the structure is stored as data.

## Probabilities

Each heading has P(yes) (`latris et probability <heading> <p>`), and can have different values on different branches (`--given "Gas detected=no"`): the most specific value that matches a branch applies. The initiating event can have a frequency per year (`latris et frequency`). Every value keeps where it came from; a heading's probability can cite a fault-tree analysis, and the initiating frequency a bow-tie's.

## What the analysis shows

`latris et analyse` gives each sequence's probability (the product of its branch probabilities) and, with the initiating frequency, how often it happens per year; the totals per end state; and the dominant sequence behind each end state. Values on the dominant sequences that nobody has verified are flagged. The result is recorded for the report and goes out of date when the tree or a value changes.

## How sure is it? (Monte Carlo)

Give the uncertain numbers a range and sample them: `latris et uncertainty "Gas release" --median 0.02 --error-factor 3` (a lognormal whose 95th percentile is three times its median — the usual way risk assessments state it), or a branch probability, conditional ones with `--given "Gas detected=no"`; other distributions take `uniform --min --max`, `triangular`, `beta` and so on. `latris et monte-carlo` reruns the tree for each sample and gives every end state's 5th–95th percentile, median and mean beside the point estimate, and ranks the uncertain inputs by how strongly they drive the headline end state (`--output` picks it; by default the rarest). Values without a range stay fixed and are listed, so the spread is a lower bound.

## Readiness

Complete when there is one initiating event and at least one end state, every heading is in the order, and the sequences form a complete tree: at each branch point every sequence asks the same next question, both answers are covered, no sequence stops while a sibling continues, and every heading and end state is used.

## Practical caution

Branches are binary, and dependence between headings is only what you state with conditional probabilities. Uncertainty comes only from the ranges you give for Monte Carlo, and heading probabilities are entered rather than linked live to fault trees. Methods: IEC 62502 (event tree analysis) and the NRC *PRA Procedures Guide* (NUREG/CR-2300).
""",
    ),
    HelpTopic(
        id="model-type-mcda",
        title="Multi-Criteria Decision Analysis",
        category="model-types",
        summary="Choose between options judged on several criteria, and see how firm the choice is.",
        body="""## What an MCDA represents

Options you could choose (sites, suppliers, policies) and the criteria they are judged on (cost, travel time, capacity). Give each factor its element (`latris mcda element <factor> option|criterion`), then for each criterion a **swing weight**, a **direction** and, ideally, a **scale** (`latris mcda criterion Cost --weight 50 --direction lower --worst 100 --best 0 --units "$m"`), and each option's **score** on each criterion (`latris mcda score "Site A" Cost 40 --source quote-2025`).

A swing weight says how much moving from the worst to the best of the scale matters, compared with the other criteria's swings — so a weight means nothing without its scale. Without `--worst`/`--best` the options' own range is used; that shifts when an option is added, and the weights then need revisiting.

## What the analysis shows

`latris mcda analyse` turns each score into a value from 0 (worst) to 1 (best), combines them by the normalised weights into a total out of 100, and shows:

- the **ranking**, with each criterion's contribution to each option's total;
- **dominated** options — no better anywhere, worse somewhere — which can be set aside whatever the weights;
- for each weight, **how far it would have to move** (the others keeping their proportions) before the top choice changes — a fragile choice shows up as a small move;
- the scores the winning margin rests on that nobody has verified.

The result is recorded for the report and goes out of date when a weight, scale or score changes.

## Practical caution

The model is additive and linear: it assumes criteria can be traded off independently and value rises evenly between worst and best. Weights are judgements — record whose (`--source`). Methods: Keeney & Raiffa (1976), Belton & Stewart (2002), and the UK government's *Multi-criteria analysis: a manual* (DCLG 2009).
""",
    ),
    HelpTopic(
        id="model-type-ach",
        title="Analysis of Competing Hypotheses",
        category="model-types",
        summary="Weigh competing explanations against all the evidence at once, and find what the conclusion turns on.",
        body="""## What ACH represents

Several possible explanations (**hypotheses**) and everything you know that bears on them (**evidence items**: facts, reports, arguments, even things you'd expect to see and don't). Give each factor its element (`latris ach element <factor> hypothesis|evidence_item`), say how far each item can be trusted and how directly it bears (`latris ach item <item> --credibility high --relevance medium`), and rate every item against every hypothesis (`latris ach rate <item> <hypothesis> CC|C|N|I|II --rationale "…"`) — very consistent to very inconsistent. Ask of each cell: *if this hypothesis were true, how likely would I be to see this?*

An evidence item can carry its own sources like any factor (`latris evidence add <item> description <key>`), and the analysis says whether they've been checked.

## What the analysis shows

`latris ach analyse` (Heuer's method):

- ranks the hypotheses by the **evidence against them**, weighted by credibility and relevance — the strongest hypothesis is the one the evidence fails to rule out, not the one with most in its favour;
- flags evidence rated the same against every hypothesis — it can't help you choose;
- finds the **linchpins**: items without which the lead would change or be tied, with whether their sources were checked. Those are what to verify first.

The result is recorded for the report and goes out of date when a rating, weight or source changes.

## Practical caution

Ratings are judgements; record your reasoning (`--rationale`). The weights (high 1.0, medium 0.7, low 0.4; an inconsistency counts 1, a strong one 2) are a stated convention, and the ranking orders hypotheses — it doesn't give their probabilities. Method: Heuer (1999), *Psychology of Intelligence Analysis*, ch. 8.
""",
    ),
    HelpTopic(
        id="model-type-dt",
        title="Decision Trees",
        category="model-types",
        summary="Find the best choice under uncertainty, and what finding out more first would be worth.",
        body="""## What a decision tree represents

**Decision** nodes where someone chooses, **chance** nodes where the world does, and **terminal** nodes with a payoff. Give each factor its type (`latris dt element <factor> decision|chance|terminal`) and link each node to its children with ordinary links; each node has one parent, so repeat an outcome under each branch rather than sharing it. Then set each branch's label and, from a chance node, its probability (`latris dt branch "Demand if launched -> High demand, launched" --label High -p 0.4`), any value along a branch such as the cost of a test (`--value -20`), each terminal's payoff (`latris dt payoff <terminal> 500 --source forecast`), and whether you're maximising (profit) or minimising (cost) (`latris dt settings --objective maximise --units "$k"`).

When the same uncertainty appears under several choices — demand if you launch, demand if you license — give those chance nodes one name (`latris dt uncertainty <chance node> Demand`) with the same states and probabilities, so the tree can price knowing it.

## What the analysis shows

`latris dt analyse` rolls the tree back — a chance node is worth the probability-weighted value of its branches, a decision node the best of its options — and gives:

- the **best strategy** and the expected value of each first choice;
- the **expected value of perfect information** for each uncertainty — the most it's worth paying to know it before choosing (market research costing more isn't worth it) — and for all of them together;
- for each two-state uncertainty, the **probability at which the best choice changes**;
- the values on the best path nobody has verified.

The result is recorded for the report and goes out of date when the tree or a value changes.

## Practical caution

Expected value is risk-neutral: a strategy with a small chance of ruin can still come out best. Probabilities and payoffs are point values. Perfect information is an upper bound — real research is imperfect and worth less. Methods: Raiffa (1968), Clemen & Reilly (2014), Howard (1966).
""",
    ),
    HelpTopic(
        id="model-type-markov",
        title="Markov Cohort Models",
        category="model-types",
        summary="Follow a cohort between states over time, and compare what strategies cost and achieve.",
        body="""## What a Markov model represents

A group of people (a cohort) spread over **states** — Healthy, Sick, Dead — moving between them each **cycle**. Give each factor its element (`latris markov element <factor> state|strategy`); a transition is an ordinary link between two states with a probability per cycle (`latris markov transition "Healthy -> Sick" 0.10 --source registry-2024`). Whatever doesn't leave a state stays in it. Say where the cohort starts (`latris markov start Healthy 1`).

Each state can have a **cost** per cycle and a **utility** — a quality-of-life weight per year, 1 for full health and 0 for dead (`latris markov reward Sick --cost 2500 --utility 0.6`). **Strategies** being compared (Standard care, New drug) use the same model and differ where you override a transition or reward for one of them (`--strategy "New drug"`). Settings set the horizon and cycle length, discounting for costs and outcomes, half-cycle correction, the willingness to pay per unit of outcome and the units (`latris markov settings --cycles 40 --discount 0.035 --wtp 20000 --cost-units £ --outcome-units QALY`).

## What the analysis shows

`latris markov analyse` runs the cohort for each strategy and gives its discounted cost and outcome (e.g. QALYs) per person and the expected time in each state. With two or more strategies it does the standard **incremental analysis**: cheapest first; strategies that cost more and achieve no more are **dominated**; those a mix of their neighbours would beat are **extendedly dominated**; the rest have an **ICER** — the extra cost per extra unit of outcome — against the previous one. Each ICER is the willingness to pay at which the choice changes; with a willingness to pay set, the strategy with the highest net monetary benefit is named.

The result is recorded for the report and goes out of date when any value changes.

## Practical caution

The model is memoryless: the chance of moving depends only on the current state, not on how long someone has been in it. Values are point estimates — probabilistic sensitivity analysis is not yet available. Methods: Sonnenberg & Beck (1993), Briggs, Claxton & Sculpher (2006), Drummond et al. (2015).
""",
    ),
    HelpTopic(
        id="lineage-versioning",
        title="Lineage and Versioning",
        category="versioning",
        summary="Use milestones and alternatives to compare model histories without losing auditability.",
        body="""## What lineage is for

Lineage tracks named versions, milestones, and alternatives in a Git-backed project. It lets you preserve model history while exploring different assumptions or framings.

## Main concepts

- **Milestone:** a named checkpoint on the current branch.
- **Alternative:** a new version branch from a milestone or current state.
- **Current version:** the branch or lineage node currently being edited.

## Comparing versions

**Compare with…** in the versions panel lists what changed between the version you're on and another version or a model checkpoint — factors and links added, changed and removed, and the rest of the record (sources, assumptions, decisions) — naming each factor and link. **Show on the canvas** marks what was added and changed on the model; what was removed is listed, since it isn't there to mark. From the command line: `latris version compare <from> <to>`, where either side is a version or a checkpoint.

## When to branch — and when to use a scenario instead

Create alternatives when a modelling assumption, framing, or stakeholder view would change the structure enough that simple notes are not enough: a different link, equation or mechanism; a competing expert view.

Don't branch for options you want to compare (a policy, a delayed start, a high-load world). Those are **scenarios** in one version: they share the same model and the same uncertainty draws, so their differences are paired and a fix to the model reaches every option at once. A useful rule: scenarios answer *what could we do?*; alternative versions answer *what do we believe about how the system works?*

## Published vs local versions

When a project is shared with collaborators, each version is either **local** (only on your machine) or **published** (visible to everyone on the project). Explorations stay local until you choose to **Publish** them, so half-formed what-ifs are not shared by accident. Each version on the tree shows its state at a glance:

- **🔒 Local** — only you have it; publish it to share.
- **✓ Shared** — in sync with the project.
- **⬆ N to publish** — you have changes the project has not seen yet.
- **⬇ Updates** — the shared copy has changes; use **Get latest**.
- **👻 Ghost** — a version a collaborator published that is not in your workspace yet; **add it** to bring it in.

These replace any notion of "push" and "pull" — you publish a version and get the latest for a version; the version tree is where collaboration lives.

## Audit value

Reports can include milestone history so reviewers can see how the model evolved, not only the final result.
""",
    ),
    HelpTopic(
        id="cli-reference",
        title="CLI and Developer Reference",
        category="developer",
        summary="Where the command-line tools fit with the GUI and how to find deeper developer docs.",
        body="""## CLI and GUI share the same core

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
""",
    ),
    # ── AI interrogation Phase 3+4 — adversarial mutation, source verification ──
    HelpTopic(
        id="adversarial-review-tray",
        title="Adversarial Review Tray",
        category="ai",
        summary="The non-blocking docked panel where adversarial AI proposals accumulate for triage.",
        body="""## What it is

The Adversarial Review Tray is a docked panel (bottom-right of the workspace) where mutation proposals from Phase 3+4 prompts queue up for human review. It coexists with the single-proposal modal — the modal stays for one-at-a-time interactive runs, the tray accumulates proposals you want to triage in batches.

## Which prompts queue here

- **EdgeReclassify** (model-scope) — retags or removes misclassified edges.
- **ChallengeEdge** (element-scope) — counter-mechanism + a single repair action per edge.
- **EvidenceDemote** (element-scope) — verdict change or removal on an evidence link.
- **VerifyClaimAgainstSource** (element-scope) — source verification with apply-time verbatim check.

## How to use it

1. Run one of the adversarial prompts from the inspector or the model AI menu — the proposal lands in the tray rather than blocking with a modal.
2. Click an entry to expand it inline. The same picker components used by the modal render here.
3. Approve, reject, or close the entry. Approved proposals flow through the standard apply path; commits go through `auto_commit` and surface in git history.

## Non-blocking

The tray does not block the canvas. You can keep editing the model while proposals accumulate. Reject any time with the per-entry button or by closing the expanded view.
""",
    ),
    HelpTopic(
        id="edge-reclassify",
        title="EdgeReclassify",
        category="ai",
        summary="Adversarial pass that catches policy/governance/definitional links currently typed as causal.",
        body="""## What it does

EdgeReclassify is a model-scope adversarial prompt. It scans every edge and proposes one of:

- **keep** — the edge is correctly typed.
- **retag** — change the edge's `kind` to `causal`, `decision_rule`, `governance`, or `definitional`. Non-causal kinds are excluded from loop counts and centrality analysis (`operations/graph_analysis.py::causal_edges`).
- **remove** — detach the edge with rationale.

## Why

The 4DWW capability run exposed an inflation bug: policy/decision-rule edges typed as causal inflated feedback-loop counts. EdgeReclassify is the repair pass — typing those edges as `decision_rule` keeps them on the canvas but out of loop counts.

## How it flows

1. Run from the model AI menu — queues to the Adversarial Review Tray.
2. Expand the proposal and review per-action checkboxes. Each action carries a rationale + confidence.
3. Approve the subset you accept. Rationale lands in the commit body.
""",
    ),
    HelpTopic(
        id="challenge-edge",
        title="ChallengeEdge",
        category="ai",
        summary="Element-scope adversarial prompt: counter-mechanism plus one repair action per edge.",
        body="""## What it does

ChallengeEdge runs on a single edge and returns the strongest counter-mechanism against the edge as encoded, plus one of three repair actions:

- **evidence_search(query)** — record a literal search query as an OpenQuestion for human pickup.
- **polarity_flip(new_polarity)** — flip the CLD polarity on the edge (`+`, `-`, or `~`).
- **remove(rationale)** — detach the edge entirely.

## Why one action

The asymmetry of Phase 3 is closed: the AI can propose to demote prior-approved state, but only via a single, structured action that goes through `apply()`. The reviewer triages.

## How it flows

1. Open the edge inspector, click "Challenge edge (adversarial)" — the proposal queues to the Adversarial Review Tray.
2. Review the counter-mechanism prose, then the proposed action. Rationale + confidence travel together.
3. Approve to apply, reject to discard.
""",
    ),
    HelpTopic(
        id="evidence-demote",
        title="EvidenceDemote",
        category="ai",
        summary="Adversarial pass on one evidence link: change verdict or remove with rationale.",
        body="""## What it does

EvidenceDemote runs on a single `(target, attribute, bibkey)` evidence link and asks whether the source actually supports the specific claim or only topically overlaps. Output is one of:

- **change_verdict(new_verdict)** — flip `support_verdict` to `unverified`, `contradicts`, `orthogonal`, or `insufficient_extract`. Rationale appends to the link's `notes`.
- **remove(rationale)** — detach the link entirely.

## What it never does

EvidenceDemote does NOT promote a verdict to `supports`. Promotion to `supports` happens only via VerifyClaimAgainstSource (Phase 4a), which enforces a verbatim-quote audit invariant. Demotion has no equivalent guarantee — the model's judgment is enough — so this prompt is one-way.

## How it flows

1. In the inspector, find the evidence entry on a node or edge, click "AI demote" — queues to the Adversarial Review Tray.
2. Review the AI's reasoning. Verdict change applies via the new `set_evidence_support_verdict` operation.
""",
    ),
    HelpTopic(
        id="source-snapshot",
        title="Source Snapshots",
        category="evidence",
        summary="A persistent fetched-content slot on each Reference, with metadata that the verifier audits against.",
        body="""## What it is

`Reference.source_snapshot` records the text the project actually has access to for a citation: `retrieval_url`, `fetched_at`, `content_hash`, an extract (≤2000 chars; a longer one is refused — keep the passage that bears on the claim), and a `kind` discriminator.

## Three kinds

- **`abstract`** — the paper's abstract or a short summary you (or `ref snapshot`) pasted in. Promotes `EvidenceLink.source_access` to `abstract`.
- **`landing_page_text`** — generic publisher landing-page copy. Does NOT promote source_access — landing pages are not the paper's content.
- **`full_text_excerpt`** — created by `ref fetch` (Tier-1). The first 2000 chars of the fetched full text; the rest lives in a per-bibkey artefact at `ai/reference-extracts/<bibkey>.txt`.

## How it's set

- **Manual**: `latris ref snapshot <bibkey> --url ... --extract ... --kind abstract`. Use this when the source is paywalled, behind a login, or otherwise unreachable to the fetcher.
- **Automatic**: `latris ref fetch <bibkey> [--url ...]` or the "Fetch source" button in the Reference Inspector. See Tier-1 retrieval.

## Why it matters

VerifyClaimAgainstSource validates the AI's verbatim quote against `source_snapshot.extract` (Phase 4a) or against the per-bibkey artefact's chunks (Phase 4b). No snapshot, no verification — the prompt refuses to run.

## Refetch behaviour

Refetches overwrite the snapshot. Git history preserves prior snapshots; the YAML always reflects the latest fetch.
""",
    ),
    HelpTopic(
        id="tier-1-retrieval",
        title="Tier-1 Source Retrieval",
        category="evidence",
        summary="`ref fetch` pulls the full text of a reference, chunks it, and stores it as a per-bibkey artefact.",
        body="""## What `ref fetch` does

1. **Resolves the URL** — explicit `--url`, then `Reference.url`, then `https://doi.org/<doi>`.
2. **Fetches via httpx** with redirect follow, timeout, and a Latris user agent.
3. **Extracts text** — HTML is tag-stripped (no BeautifulSoup dep); `text/plain` passes through; `application/pdf` uses `pypdf` if installed.
4. **Writes the artefact** at `ai/reference-extracts/<bibkey>.txt` (gitignored). Each Reference has at most one artefact; refetches overwrite.
5. **Updates `Reference.source_snapshot`** with `kind="full_text_excerpt"`, first 2000 chars as the extract, retrieval URL, fetched_at, and the content hash of the full text.

## How verification uses it

When VerifyClaimAgainstSource runs and the artefact exists, the context builder chunks the full text (1000-char windows with 200-char overlap), scores chunks against the claim with BM25-lite keyword overlap, and passes the top-3 chunks to the model. The verbatim-quote check then matches against the specific chunk whose `content_hash` the model returns.

## What it doesn't do

- **No PDFs without pypdf.** The fetcher raises with a clear message if PDF content arrives without pypdf installed. `pip install pypdf` to enable.
- **No paywall bypass.** Login gates and 403 responses cause empty-text rejections; use `ref snapshot` to paste content manually instead.
- **No Tier-2 discovery.** Auto-discovery via Semantic Scholar / OpenAlex / arXiv at proposal time is a separate (deferred) feature.

## Hermetic tests

Tests inject a stub via the `http_get` parameter on `fetch_reference_source`. No network in CI; see `tests/operations/test_fetch_reference.py`.
""",
    ),
    HelpTopic(
        id="verify-claim-against-source",
        title="VerifyClaimAgainstSource",
        category="ai",
        summary="Apply-time verbatim quote validation against the stored source snapshot. The model cannot self-attest.",
        body="""## The audit invariant

When VerifyClaimAgainstSource returns `verdict="supports"`, the server checks that the model's quote appears in the text held for the source: a chunk of the fetched full text, the stored snapshot extract, or the abstract. Copying artefacts are forgiven (whitespace, curly quotes, dashes, case; `...` marks a gap); wording is not. On match, the link's `support_verdict` flips to `supports`, the quote and `quote_location` (chunk_hash + offset) land on the link with `quote_verified: true`, and `source_access` records what the quote was found in (`full_text_chunk` for the full text or a full-text excerpt, `abstract` for an abstract or summary). On mismatch, the proposal is rejected and the substrate stays unchanged.

The same check runs on `latris evidence check --by ai --quote ...` (and the chat connector's check): an agent cannot record a quote that isn't in the stored text. A person's check with a quote Latris can't find is recorded with `quote_verified: false`, and the report says the quote was not found.

The validator is the source of truth — not the model's confidence, not its prose. The model cannot self-attest.

## Other verdicts

- **contradicts** — the source addresses the claim and states the opposite. No quote required.
- **orthogonal** — the source is on-topic but does not address this specific claim. No quote required.
- **insufficient_extract** — the extract is too thin to decide. No quote required; prompt cycle ends with "needs deeper fetch".

For all three non-supports verdicts, no verbatim check runs — just the verdict flip.

## When to run it

After a reference has a `source_snapshot` (abstract or full text). If the snapshot is missing, the prompt's context builder raises before the LLM call — saves the API cost.

## How it flows in the GUI

1. Open the inspector for the node or edge that carries the evidence link.
2. Click the **Verify** button next to the link (disabled with a tooltip if no snapshot is set or the link is already verified).
3. Type the specific claim being verified — the AI gets it as input alongside the source snapshot.
4. The proposal lands in the Adversarial Review Tray. Approve to apply.

## CLI alternative

```
latris ai call run VerifyClaimAgainstSource \\
    --inputs '{"target_id": "edge_xxx", "attribute": "polarity", "bibkey": "smith2023", "claim": "..."}' \\
    --yes
```
""",
    ),
    HelpTopic(
        id="accounts-sign-in",
        title="Accounts & Signing In",
        category="collaboration",
        summary="Passwordless sign-in, creating an account, your profile, and signing out.",
        body="""## Passwordless sign-in

Latris uses **magic-link** sign-in — there is no password. You enter your email, Latris sends you a one-time code, and you type that code in. The code expires after ten minutes; request a new one if it lapses.

## Sign in vs Create account

The sign-in screen has two tabs:

- **Sign in** — for an email that already has an account.
- **Create account** — for a new account. You provide your **first and last name** (required) and **organisation** (optional) before requesting your code.

If you pick the wrong one, Latris tells you (e.g. "No account for this email — choose Create account") so you can switch.

## Your profile and authorship

- Your **name** and **email** appear as the author on the model changes you make (this is part of the project's provenance and travels with the model).
- Your **organisation** stays on your account only — it is **not** written into the shared model.
- Open the **account menu** from your name in the top-right to **Edit profile** or **Sign out**. (This is separate from the **Versions** view, where sharing and collaboration live.)

## Which server

Accounts live on a Latris **sync server**. Most people never change it — it's prefilled. If you need to point at a specific server, expand **Advanced** on the sign-in screen. Once you sign in successfully, the app remembers it.

## Invite-only

A server may be **invite-only**: an administrator allows specific emails. If your email isn't approved you won't be able to create an account on that server.
""",
    ),
    HelpTopic(
        id="sharing-syncing",
        title="Sharing & Syncing Projects",
        category="collaboration",
        summary="Share a project online, invite collaborators by email, and publish versions so others can see them.",
        body="""## Where collaboration lives

Open the **Versions** view (top-right). Everything about working with other people lives here, alongside the version tree — there is no separate sync screen.

## Sharing a project

In the Versions view, under **People**, enter a name and click **Share**. Latris creates a private online copy of the project. From then on you choose which versions collaborators can see.

## The project list

The landing page shows all your projects in one list, each with a status:

- **Local** — exists only on this machine; not shared.
- **Synced** — your local copy is linked to an online project. Open it as usual.
- **Available** — a project shared *with you* online that you haven't downloaded yet. Click it to clone a local copy, then it becomes Synced.

The list is deduplicated: a project that is both local and online shows as **one** row, not two.

## Keeping in sync (turn-based, per version)

Modelling is deliberative, so collaboration is **turn-based**, not live, and it works **one version at a time**:

- **Publish** a version to make it visible to the project.
- **Get latest** on a version when the shared copy has moved ahead (the version shows an "Updates" badge).
- A version a collaborator published that you don't have yet shows as a faint **ghost** — click it to **add it to your workspace**.

Each version on the tree shows its state at a glance (Local, Shared, changes to publish, Updates, or Diverged). Coordinate with collaborators so you're not editing the same version at once.

## Members and roles

The project owner manages who can access a shared project:

- **Owner** — controls membership and can delete the project.
- **Collaborator** — can change the model.

Invite someone by **email** from **People** in the Versions view. They get an account the first time they sign in, then the project appears as **Available** for them to open. (Until you publish a version, a collaborator who opens the project sees nothing yet.)

## Report link

Under **People**, the owner can turn on a **report link**: a read-only web page of the project's report (with its diagram) that anyone with the link can open — no account needed, and it isn't indexed by search engines. Pick which report pack it shows. It's off by default. Turning it off and on again issues a new link, so an old one stops working.

## Models made in a chat

If you build a model with an AI chat (using the Latris connector), it starts **unsaved** and expires 30 days after its last edit. Ask the AI to save it: it gives you a one-time link that adds the model to your account (sign in with just your email). Saved models appear in your project list, and the chat can keep editing them.

## Reconciling a diverged version

If you and a collaborator both change the **same version** before sharing, it **diverges** — the version shows a "Diverged" badge. Click **Reconcile** to see what changed on the shared copy side by side, then **keep one line**. The line you don't keep is preserved as an **archived** version (turn on "Show archived versions" to see it) — nothing is ever deleted. Coordinate with the other person so divergence stays rare.

## One server per project

A shared project remembers which server it belongs to. Don't share the same project against two different servers (e.g. a local test server and the hosted one) — that crosses wires and sync will fail.
""",
    ),
]


def list_topics() -> list[dict]:
    """Return all topics without body content for the list view."""
    return [t.model_dump(mode="json", exclude={"body"}) for t in HELP_TOPICS]


def get_topic(topic_id: str) -> HelpTopic | None:
    """Return a single topic by ID, or None if not found."""
    for topic in HELP_TOPICS:
        if topic.id == topic_id:
            return topic
    return None
