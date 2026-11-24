"""AI interrogation prompts: source verification, adversarial edge checks, the completeness gate."""

from __future__ import annotations

from latris.ai.prompts._spec import PromptIntent, PromptScope, PromptSpec
from latris.ai.prompts.inputs import (
    ChallengeEdgeInputs,
    CompletenessGateInputs,
    EdgeReclassifyInputs,
    EvidenceDemoteInputs,
    VerifyClaimAgainstSourceInputs,
)

PROMPTS: dict[str, PromptSpec] = {
    "VerifyClaimAgainstSource": PromptSpec(
        name="VerifyClaimAgainstSource",
        title="Verify claim against source",
        description=(
            "Audit-grade evidence verification. Given an evidence link "
            "and the claim it supposedly supports, the AI reads the "
            "Reference's source_snapshot extract and returns one of "
            "supports / contradicts / orthogonal / insufficient_extract. "
            "On `supports` the AI must include a verbatim quote that "
            "appears in the extract; the apply()-time validator rejects "
            "the proposal otherwise. The model cannot self-attest."
        ),
        inputs=VerifyClaimAgainstSourceInputs,
        template=(
            "You are verifying whether a cited source actually supports "
            "a specific claim. The user message gives you the claim, "
            "the source-snapshot extract, and metadata about the "
            "evidence link.\n\n"
            "Decide one of:\n"
            "  - supports: the extract contains language that backs "
            "    the claim. You MUST include a verbatim quote drawn "
            "    from the extract (copy-paste exact characters, "
            "    including punctuation). The quote will be checked "
            "    character-for-character against the stored extract; "
            "    paraphrases or near-matches are rejected.\n"
            "  - contradicts: the extract addresses the claim and "
            "    states the opposite. No quote required.\n"
            "  - orthogonal: the extract is on-topic but does not "
            "    address the specific claim. No quote required.\n"
            "  - insufficient_extract: the extract is too narrow / "
            "    only an abstract / does not contain enough text to "
            "    decide. Use this when you'd need to read more of the "
            "    source.\n\n"
            "Return a `summary` paragraph that names what the source "
            "actually says vs. what the claim asserts (the critique "
            "prose), plus a confidence (high/medium/low).\n\n"
            "Hard rules:\n"
            "- The verbatim quote MUST be a contiguous span of "
            "  characters from the extract. Do not splice multiple "
            "  parts together.\n"
            "- Do not invent text not present in the extract.\n"
            "- If you cannot find verbatim language that supports "
            "  the claim, choose orthogonal or insufficient_extract — "
            "  do NOT pick supports with a paraphrased quote.\n"
        ),
        output_hint=(
            "A VerifyClaimAgainstSourceProposal with verdict, "
            "rationale, confidence, summary, and (when verdict="
            "supports) a verbatim quote that the apply-time validator "
            "checks against the stored extract."
        ),
        scope=PromptScope.element,
        intent=PromptIntent.action,
    ),
    "ChallengeEdge": PromptSpec(
        name="ChallengeEdge",
        title="Challenge this edge",
        description=(
            "Adversarial pass on a single low-coverage or low-confidence "
            "edge. Generates the strongest counter-mechanism and proposes "
            "one of three actions: evidence_search (record an open question "
            "for a targeted search), polarity_flip (reverse the sign on a "
            "CLD edge), or remove (detach the edge entirely with rationale)."
        ),
        inputs=ChallengeEdgeInputs,
        template=(
            "You are challenging a single edge in a {model_type} model. "
            "Read the edge's source and destination labels, polarity (if "
            "any), description, and any attached evidence. Articulate the "
            "STRONGEST counter-mechanism — the mechanism that, if true, "
            "either reverses the sign or makes the edge irrelevant.\n\n"
            "Then choose ONE action:\n"
            "  - evidence_search: write a query the human should run "
            "    (Semantic Scholar, OpenAlex, etc.) that would settle "
            "    whether the edge holds. Records as an OpenQuestion.\n"
            "  - polarity_flip: pick a new polarity from + / - / ambiguous "
            "    when the counter-mechanism implies the sign is wrong.\n"
            "  - remove: detach the edge entirely when the counter-mechanism "
            "    suggests the relation is not real (or is wholly subsumed "
            "    by another edge).\n\n"
            "All actions carry a rationale and confidence (high/medium/low). "
            "ALSO produce a `summary` paragraph that is the critique prose "
            "itself — the strongest argument against the edge as currently "
            "encoded.\n\n"
            "Hard rules:\n"
            "- Pick ONE action, not multiple. The reviewer triages.\n"
            "- evidence_search query must be a literal search string, not "
            "  a sentence describing what to search.\n"
            "- polarity_flip is only valid for CLD models with a current "
            "  polarity attribute on the edge — otherwise pick a different "
            "  action.\n"
        ),
        output_hint=(
            "A ChallengeEdgeProposal with critique prose (summary), one "
            "action variant (evidence_search | polarity_flip | remove), "
            "rationale, and confidence."
        ),
        scope=PromptScope.element,
        intent=PromptIntent.action,
    ),
    "EvidenceDemote": PromptSpec(
        name="EvidenceDemote",
        title="Demote this evidence link",
        description=(
            "Adversarial pass on a single evidence link. Asks whether the "
            "cited source actually supports the specific claim, or only "
            "topically overlaps with it. Output is either a verdict change "
            "(supports → orthogonal / contradicts / insufficient_extract / "
            "unverified) or removal entirely, with rationale."
        ),
        inputs=EvidenceDemoteInputs,
        template=(
            "You are auditing one evidence link. The user message gives you "
            "the cited reference (title, abstract or source-snapshot when "
            "available), the target element, and the attribute the link "
            "claims to support.\n\n"
            "Decide whether the source genuinely supports the specific "
            "claim attached to this link, or only topically overlaps with "
            "it. Then pick ONE action:\n"
            "  - change_verdict: set support_verdict to one of unverified / "
            "    supports / contradicts / orthogonal / insufficient_extract. "
            "    Use orthogonal when the source is on-topic but does not "
            "    address THIS claim. Use insufficient_extract when the "
            "    snapshot/abstract is too thin to decide and a deeper "
            "    fetch is needed.\n"
            "  - remove: detach the link entirely when the source has no "
            "    bearing on the claim and the citation is misleading.\n\n"
            "Action carries a rationale and confidence (high/medium/low). "
            "ALSO produce a `summary` paragraph naming what the source "
            "actually says vs. what the claim asserts.\n\n"
            "Hard rules:\n"
            "- Do NOT promote to `supports` from this prompt — Phase 4 "
            "  promotes via verbatim-quote validation, not by AI fiat.\n"
            "- If the source-snapshot is missing entirely (only title is "
            "  available), prefer change_verdict→insufficient_extract over "
            "  remove. Removal is for misleading citations, not unread ones.\n"
        ),
        output_hint=(
            "An EvidenceDemoteProposal with one action (change_verdict | "
            "remove), rationale, confidence, and summary critique prose."
        ),
        scope=PromptScope.element,
        intent=PromptIntent.action,
    ),
    "EdgeReclassify": PromptSpec(
        name="EdgeReclassify",
        title="Reclassify edges",
        description=(
            "Adversarial pass over every edge to catch misclassified "
            "policy / governance / definitional links currently typed as "
            "causal. Each action is a retag (to the right kind) or a "
            "remove (with rationale) — non-causal kinds are excluded "
            "from loop and centrality analysis, so retagging is enough "
            "to repair the inflation bug without deleting structure."
        ),
        inputs=EdgeReclassifyInputs,
        template=(
            "You are reviewing a {model_type} model for edge-kind "
            "misclassification — the bug pattern from the 4DWW capability "
            "run, where policy/decision links and definitional identities "
            "were typed as causal and inflated feedback-loop counts.\n\n"
            "For each edge in the substrate, decide one of:\n"
            "  - keep: leave the edge as-is.\n"
            "  - retag: change the edge.kind to one of: causal, "
            "    decision_rule, governance, definitional. Use:\n"
            "      * causal — physical/behavioural mechanism A → B.\n"
            "      * decision_rule — policy or allocation (e.g. budget, "
            "        staffing rules).\n"
            "      * governance — accountability, ownership, oversight.\n"
            "      * definitional — identity / mathematical relation "
            "        (e.g. Output = Hours × Rate; Total / Average).\n"
            "  - remove: detach the edge entirely. Only choose this when "
            "    no kind tag fits — the edge is not a real relation, or "
            "    is wholly subsumed by another edge.\n\n"
            "For every action, give a one- or two-sentence rationale that "
            "names the relation (e.g. 'budget allocation, not mechanism'). "
            "Add a confidence: high / medium / low — your own confidence "
            "in the call. Default medium when unsure.\n\n"
            "ALSO produce a one-paragraph `summary` of the worst "
            "misclassifications you found and what changing them would "
            "do to the model's feedback-loop story. The summary is shown "
            "as critique prose alongside the per-edge actions.\n\n"
            "Hard rules:\n"
            "- Do NOT propose actions for edges that are already correctly "
            "  typed; mark those keep.\n"
            "- Do NOT change edge.kind to one of the v2+ kinds "
            "  (informational, flow, support, logical, association, "
            "  temporal, decomposition, conditional). Confine retags to "
            "  causal / decision_rule / governance / definitional.\n"
            "- Do NOT remove an edge as a stand-in for a polarity flip. "
            "  Polarity is a separate concern.\n"
        ),
        output_hint=(
            "An EdgeReclassifyProposal with per-edge actions (keep/retag/"
            "remove with rationale + confidence) plus a summary of the "
            "headline misclassifications."
        ),
        scope=PromptScope.model,
        intent=PromptIntent.action,
    ),
    "CompletenessGate": PromptSpec(
        name="CompletenessGate",
        title="Completeness gate",
        description=(
            "Run before Interpret* to identify variables required to answer "
            "the modelling question that are missing from the model. Reports "
            "are persisted at views/{model_type}/completeness-report.yaml so "
            "human overrides survive subsequent runs."
        ),
        inputs=CompletenessGateInputs,
        template=(
            "You are checking whether a {model_type} model has the variables "
            "needed to answer its modelling question, BEFORE interpretation "
            "prose is generated. The user has supplied claims the upcoming "
            "Interpret* will produce; identify variables required to support "
            "those claims that are missing from the entity set.\n\n"
            "For each missing variable produce a MissingVariableProposal "
            "with:\n"
            "  - name: short, human-readable label.\n"
            "  - rationale: one or two sentences on why the variable is "
            "    necessary to answer the question.\n"
            "  - required_for: list of claim strings (verbatim) or "
            "    open-question topics that depend on the variable.\n"
            "  - severity: required (the question cannot be answered without "
            "    this variable), recommended (the answer is materially "
            "    weaker without it), or optional (the variable is "
            "    nice-to-have).\n"
            "  - confidence: high/medium/low — your own confidence in the "
            "    call. Missing-variable detection is judgement-heavy; use "
            "    this honestly. Default to medium when unsure.\n\n"
            "Hard rules:\n"
            "- Do NOT re-propose variables the user has already excluded "
            "  (they appear under 'Prior excluded missing variables' in the "
            "  context). Excluded variables stay excluded.\n"
            "- Do NOT re-propose variables already represented as entities "
            "  in the model. Match case-insensitively on label.\n"
            "- Do NOT speculate beyond what the modelling question, claims, "
            "  and substrate support. If you cannot articulate a concrete "
            "  required_for chain, omit the proposal.\n\n"
            "Return a CompletenessGateResult with `entries` (the missing-"
            "variable proposals). The `coverage_ratio` field is populated "
            "by the application from the substrate — leave it at its "
            "default; do not attempt to compute it yourself."
        ),
        output_hint=(
            "A list of missing-variable records (name, rationale, "
            "required_for, severity, confidence). coverage_ratio is "
            "computed deterministically by the application."
        ),
        scope=PromptScope.model,
        intent=PromptIntent.action,
    ),
}
