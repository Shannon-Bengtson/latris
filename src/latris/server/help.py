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

Communicate is per-formalism: pick a model from the Communicate dropdown, then use the left-hand strip to switch between Report, Diagram, Review and Story for that formalism. Assemble report sections, export diagrams, create Word or Markdown reports, draft a public-facing Story, and send Review Packs to outside reviewers — each scoped to the chosen formalism.

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

Each selected model type appears in the Formalise dropdown. With a model open you can switch its representation:

- **Table** — a parameter grid for setting model-specific attributes (e.g. CLD polarity, FCM weights).
- **Canvas** — a read-only reference view of the structure.

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

## Layout

Canvas positions are saved separately from semantic model data. Moving a node changes the layout, not the underlying claim.
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

## Workflow

1. Initialise or refresh interpretation sections.
2. Refresh claims from current project state.
3. Generate prose for each section.
4. Edit prose where needed.
5. Use the generated sections in Communicate.

## Keep it current

If the model changes after prose is generated, refresh claims and regenerate affected sections before exporting.
""",
    ),
    HelpTopic(
        id="communicate-story",
        title="Story (public-facing)",
        category="communicate",
        summary="Turn a model into a self-contained, scrollable HTML story for non-technical and public audiences.",
        body="""## What a Story is

A Story is a self-contained, scrollable HTML page that walks a non-technical reader through a model: the question it set out to answer, what it answered, what it can't, and what that means for them. It is the public-facing counterpart to the formal Report and the audit-facing Review Pack.

## How it works

- A Story is generated **downstream of the Report** — it starts from the same sections you chose to include there.
- The steps follow a plain-language arc (hook, how the system works, what we found, what's uncertain, what it means, next steps).
- Each step's prose is AI-drafted in a public register and then editable by you. The AI only changes the wording — never the substance — so every claim still traces to the evidence in the model.
- As the reader scrolls, the model diagram highlights the nodes and loops each step is about.

## Workflow

1. Draft the story skeleton for a model type.
2. Generate plain-language prose for each step, then edit as needed.
3. Set which parts of the diagram each step emphasises (nodes or detected loops).
4. Export a single self-contained HTML file to share or host.

## What it is not

A Story is curated and audience-framed; it may deliberately leave out detail (for IP, confidentiality, or audience fit). The fully open, click-through-the-evidence experience is a separate (future) interactive model view.
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
- Interpret-generated prose sections.

## Export formats

Use Markdown for transparent text output and Word for stakeholder-ready documents.

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
- **Does the source actually support the specific claim?** `support_verdict`: unverified, supports, contradicts, orthogonal, or insufficient extract.
- **Where exactly?** `quote` plus `quote_location` (chunk hash, page, offset) when the verdict is `supports`.

A single ai-verified or human-verified badge conflated these — an AI-suggested link with no source access could read as if it had been verified against the paper. The split makes the difference visible.

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
""",
    ),
    HelpTopic(
        id="model-types-overview",
        title="Choosing a Model Type",
        category="model-types",
        summary="How to choose between CLD, DAG, FCM, BN, and planned formal views.",
        body="""## Current stable model types

- **CLD:** best for feedback systems and reinforcing or balancing loops.
- **DAG:** best for causal direction, dependencies, and acyclic reasoning.
- **FCM:** best for semi-quantitative influence modelling with weights.
- **BN:** best for quantitative probabilistic reasoning over an acyclic causal subgraph (discrete state spaces + CPTs with per-cell provenance). See the dedicated Bayesian Networks topic.

## Planned model types

The project design also describes regression (fitting coefficients onto DAG edges), system dynamics, causal DAGs, Goal Structuring Notation, bow-ties, fault trees, Petri nets, Markov chains and MDPs, influence diagrams, decision trees, event trees, fishbone diagrams, theories of change, argument maps, flowcharts, and state machines. Each is admitted only if its reasoning stays inspectable; Monte Carlo / PSA is an analysis layer over parameterized models, not a model type of its own.

## How selection affects the app

Selected model types drive readiness checks, Configure suggestions, Analyse views, and report content. Choose the model types that match the question, not every possible view.

## Rule of thumb

Use CLD when feedback is central. Use DAG when cycles would undermine the reasoning. Use FCM when the question needs directional influence strength but not a full quantitative simulation engine.
""",
    ),
    HelpTopic(
        id="model-type-bn",
        title="Bayesian Networks (quantitative)",
        category="model-types",
        summary="Discrete BN inference, canonical models, parameter learning, and sensitivity — with per-cell provenance.",
        body="""## What a BN adds

A Bayesian Network quantifies an acyclic causal subgraph: every node gets a discrete **state space** and a **conditional probability table (CPT)** giving P(node | parents). You can then compute marginals and posterior queries — reasoning forwards (predictive) and backwards (diagnostic).

## The distinctive bit: per-cell provenance

Every CPT row carries its own provenance — `origin` (human-direct, human-elicited, data-derived, ai-proposed), `verification`, `source`, and who contributed. Different rows in one table can come from different sources (an expert, a dataset, a default), and the model shows where each number came from. No incumbent BN tool does this.

## Working with a BN (the `bn` commands)

- **`bn set-state-space <node> <states>`** — declare a node's discrete states (`--ordered` for ordinal).
- **`bn set-cpt <node> --parents … --probs …`** — fill a CPT (with `--origin`/`--source`).
- **`bn set-noisy-or <node> -c "<parent>=<state>:<prob>" --leak …`** — a *canonical model* for high-fan-in binary nodes: each cause contributes independently, so k causes need k probabilities + a leak instead of 2^k rows.
- **`bn learn <dataset>`** — fit CPTs from data. Rows you elicited or verified are **protected**; data fills only the gaps. Learned rows are stamped data-derived and the run is logged.
- **`bn check`** — readiness: state spaces defined, CPTs complete + normalised, acyclic.
- **`bn marginals` / `bn query --evidence … --query …`** — exact inference.
- **`bn sensitivity <target> --state …`** — rank the parameters that move a conclusion, flagging the ones that aren't human-verified.

## Not yet

Interactive belief-bar GUI, continuous/hybrid nodes, structure learning, dynamic BNs, and incumbent-format import/export (which would strip provenance) are out of scope. See `docs/design/BN_QUANTITATIVE.md`.
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

DAG analysis supports path enumeration, d-separation, Markov blankets, and adjustment-set reasoning.
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

FCM analysis depends on edge weights and, for simulation, node activation settings. Missing weights reduce readiness.

## Practical caution

FCM weights are judgement-rich. Link weights to elicitation, evidence, or rationale so they are not mistaken for measured parameters.
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

## When to branch

Create alternatives when a modelling assumption, framing, or stakeholder view would change the structure enough that simple notes are not enough.

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

`Reference.source_snapshot` records the text the project actually has access to for a citation: `retrieval_url`, `fetched_at`, `content_hash`, an extract (≤2000 chars), and a `kind` discriminator.

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

When VerifyClaimAgainstSource returns `verdict="supports"`, the server checks that the model's verbatim quote appears **character-for-character** in the stored source snapshot extract (or in a chunk of the fetched full text). On match, the link's `support_verdict` flips to `supports`, the quote and `quote_location` (chunk_hash + offset) land on the link, and `source_access` bumps to `full_text_chunk`. On mismatch, the proposal is rejected and the substrate stays unchanged.

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
