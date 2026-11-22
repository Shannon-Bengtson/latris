"""Argument map as a formalism plugin — does the conclusion stand? (``operations/argument_map.py``)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from latris.operations.formalisms import (
    ChatOp,
    ChatTool,
    Formalism,
    ResultKind,
    default_origin,
    register,
    spec_verification,
)

_BASIS = {"checked": "a checked source", "cited": "a source not yet checked", "none": "no source",
          "contested": "a source against it", "accepted": "accepted by a person", "rejected": "rejected by a person"}
_STATUS = {"in": "stands", "out": "defeated", "undecided": "undecided"}


def _render(p: dict[str, Any]) -> list[str]:
    from latris.exporters import md
    from latris.operations.argument_map import describe

    out = [md.esc(describe(p)) + ".", ""]
    if p.get("question"):
        out += [f"The question: {md.esc(p['question'])}", ""]
    if p["reasons"]:
        rows = [[r["claim"], " + ".join(r["premises"]), r["status"], r["qualifier"] or "—",
                 md.esc(r["warrant"] or "") or "—"] for r in p["reasons"][:md.MAX_ROWS]]
        out += ["Reasons offered (premises joined by + only work together):", ""]
        out += md.table(["For", "Because", "Holds?", "Qualifier", "Warrant"], rows)
    if p["objections"]:
        rows = [[o["objection"], o["against"], _STATUS[o["status"]],
                 "inference challenged" if o["challenged"] else ("answered" if o["answered"] else "**unanswered**")]
                for o in p["objections"][:md.MAX_ROWS]]
        out += md.table(["Objection", "Against", "Its status", ""], rows)
    if p.get("answers"):
        rows = [[a["objection"], a["against"], _STATUS[a["status"]]] for a in p["answers"][:md.MAX_ROWS]]
        out += ["Answers to objections:", ""]
        out += md.table(["Answer", "To the objection", "Its status"], rows)
    if p["status"] == "in":
        parts = [f"{len(v)} with {_BASIS[k]}" for k, v in p["rests_on"].items() if v]
        out += ["The conclusion rests on premises taken as given: " + "; ".join(parts) + ".", ""]
        unsourced = p["rests_on"].get("none", []) + p["rests_on"].get("cited", [])
        if unsourced:
            out += ["Without a checked source: " + md.esc(", ".join(unsourced[:md.MAX_ROWS])) + ".", ""]
    if p["linchpins"]:
        out += ["Linchpins — if any one were rejected, the conclusion would no longer stand: "
                + "; ".join(f"{md.esc(x['claim'])} ({_BASIS.get(x['basis'], x['basis'])})" for x in p["linchpins"])
                + ".", ""]
    if p["challenged"]:
        out += ["Inferences under an open challenge (counted for nothing until resolved): "
                + md.esc(", ".join(p["challenged"])) + ".", ""]
    if p["outside"]:
        out += ["Claims that don't bear on the conclusion: " + md.esc(", ".join(p["outside"][:md.MAX_ROWS])) + ".",
                ""]
    out += ["Each claim stands when every objection to it is defeated and a reason for it holds (or it is a premise "
            "taken as given); it is defeated when an objection stands or every reason fails (grounded labelling, "
            "Dung 1995).", ""]
    return out


def _claims(paths, section: str) -> list[str]:
    from latris.operations import argument_map as am

    p = am.analyse(root=paths.root)
    if p["problems"]:
        return [f"The argument map is incomplete: {len(p['problems'])} structure problem(s) (e.g. "
                f"{p['problems'][0]['label']}: {p['problems'][0]['message']})"] if section == "structure" else []
    claims: list[str] = []
    if section == "structure":
        claims.append(f"An argument for {p['conclusion']}: {len(p['reasons'])} reason(s) and {len(p['objections'])} "
                      f"objection(s) over {len(p['claims'])} claims.")
    elif section == "answer":
        claims.append(am.describe(p) + ".")
    elif section == "sensitivity":
        for x in p["linchpins"]:
            claims.append(f"The conclusion turns on {x['claim']} ({_BASIS.get(x['basis'], x['basis'])}).")
        if p["status"] == "in" and not p["linchpins"]:
            claims.append("No single premise, rejected, would stop the conclusion standing.")
        for o in p["unanswered"]:
            claims.append(f"Answering the objection '{o['objection']}' (against {o['against']}) would change the "
                          "outcome.")
    elif section == "implications":
        weak = [x["claim"] for x in p["linchpins"] if x["basis"] in ("none", "cited")]
        if weak:
            claims.append(f"Find or check sources for the linchpins first: {', '.join(weak)}.")
        if p["unanswered"]:
            claims.append("Answer the open objection(s) before relying on the conclusion: "
                          + "; ".join(o["objection"] for o in p["unanswered"]) + ".")
        if p["challenged"]:
            claims.append(f"Resolve the challenges to these inferences: {', '.join(p['challenged'])}.")
    elif section == "gaps":
        if p["no_warrant"]:
            claims.append(f"{len(p['no_warrant'])} reason(s) don't say why the premise bears on the claim (no "
                          f"warrant): {', '.join(p['no_warrant'][:4])}.")
        unsourced = p["rests_on"].get("none", [])
        if unsourced:
            claims.append(f"Premises asserted with no source: {', '.join(unsourced[:6])}.")
        if p["unverified_links"]:
            claims.append(f"{p['unverified_links']} link(s) not reviewed by a person"
                          + (f" ({p['ai_links']} proposed by AI)." if p["ai_links"] else "."))
    return claims


def _mermaid(paths, entities, edges) -> str:
    from latris.exporters.mermaid import _mermaid_text
    from latris.operations import argument_map as am

    m = am.load(root=paths.root)
    if m.problems:
        return ""
    lab = am.label(m)
    alias = {c: f"a{i}" for i, c in enumerate(m.claims)}
    lines = ["flowchart BT"]
    for c in m.claims:
        text = _mermaid_text(m.labels[c])
        shape = f'(["{text}"])' if c == m.conclusion else f'["{text}"]'
        lines.append(f"    {alias[c]}{shape}:::{lab[c]}")
    for ln in m.links:
        arrow = "-.->" if ln.relation == "attacks" else "-->"
        tag = "attacks" if ln.relation == "attacks" else (ln.entry.reason or "")
        lines.append(f"    {alias[ln.premise]} {arrow}" + (f'|"{_mermaid_text(tag)}"|' if tag else "")
                     + f" {alias[ln.claim]}")
    lines += ["    classDef in stroke-width:2px", "    classDef out stroke-dasharray:4 3,opacity:0.6",
              "    classDef undecided stroke-dasharray:2 2"]
    return "\n".join(lines) + "\n"


def _problems(root: Path) -> list:
    from latris.operations import argument_map as am

    return am.structure_problems(root=root)


def _check(block, known, outcome: str | None) -> list[str]:
    from latris.operations.build import split_link

    problems = [f"argument element: no factor named {x.node!r}" for x in block.elements if not known(x.node)]
    problems += [f"argument claim: no factor named {x.node!r}" for x in block.claims if not known(x.node)]
    for ln in block.links:
        ends = split_link(ln.link)
        if ends is None:
            problems.append(f"argument link {ln.link!r}: write it as 'Premise -> Claim'")
        else:
            problems += [f"argument link: no factor named {n!r}" for n in ends if not known(n)]
    return problems


def _apply(block, verified_by: str, root: Path) -> int:
    from latris.operations import argument_map as am

    n = 0
    for e in block.elements:
        am.set_element(e.node, e.type, root=root)
        n += 1
    for ln in block.links:
        am.set_link(ln.link, relation=ln.relation, reason=ln.reason, warrant=ln.warrant, qualifier=ln.qualifier,
                    notes=ln.notes, origin=ln.origin or default_origin(verified_by), source_id=ln.source,
                    verification=spec_verification(ln.verified, verified_by), root=root)
        n += 1
    for c in block.claims:
        am.set_claim(c.node, assessment=c.assessment, rationale=c.rationale,
                     origin=c.origin or default_origin(verified_by), source_id=c.source,
                     verification=spec_verification(c.verified, verified_by), root=root)
        n += 1
    return n


def _export(paths, labels: dict[str, str]):
    from latris.operations import argument_map as am
    from latris.repo.yaml_io import load_model
    from latris.schema import Substrate
    from latris.schema.build_spec import SpecArgumentClaim, SpecArgumentElement, SpecArgumentLink, SpecArgumentMap

    elements = sorted((SpecArgumentElement(node=labels[k], type=v) for k, v in am.get_elements(root=paths.root).items()
                       if k in labels), key=lambda e: (e.type, e.node))
    if not elements:
        return None
    ends = {e.id: (e.from_id, e.to_id) for e in load_model(Substrate, paths.conceptual_yaml).edges}
    links = [SpecArgumentLink(link=f"{labels[ends[x.target_id][0]]} -> {labels[ends[x.target_id][1]]}",
                              relation=x.relation, reason=x.reason, warrant=x.warrant, qualifier=x.qualifier,
                              notes=x.notes, source=x.source_id, origin=x.origin,
                              verified=x.verification == "human-verified")
             for x in am.get_links(root=paths.root).entries
             if x.target_id in ends and all(e in labels for e in ends[x.target_id])]
    claims = [SpecArgumentClaim(node=labels[x.target_id], assessment=x.assessment, rationale=x.rationale,
                                source=x.source_id, origin=x.origin, verified=x.verification == "human-verified")
              for x in am.get_claims(root=paths.root).entries if x.target_id in labels]
    return SpecArgumentMap(elements=elements, links=links, claims=claims)


def _run(a, root: Path) -> str:
    from latris.operations import argument_map as am

    payload = am.analyse(root=root)
    if payload["problems"]:
        raise ValueError(am.describe(payload))
    return am.record(payload, root=root)[1]


def _definition(payload: dict[str, Any]):
    from latris.schema.build_spec import make_analysis

    return make_analysis(kind="argument_analyse")


def _outcome_ids(paths) -> set[str]:
    from latris.operations import argument_map as am

    return {k for k, v in am.get_elements(root=paths.root).items() if v == "conclusion"}


def _set_outcome(target: str, root: Path):
    from latris.operations import argument_map as am

    return am.set_element(target, "conclusion", root=root)


# How a chat assistant runs each analysis (latris-app generates the tool from the manifest).
_TOOLS = {
    "argument-analysis": ("analyse_argument_map",
        "Evaluate the argument map: whether the conclusion stands, is defeated or is undecided, the reasons it "
        "stands on, unanswered objections, the linchpin premises (with whether their sources are checked), "
        "and premises asserted with no source."),
}


# How a chat assistant writes this type's build-spec block (latris-app generates each operation).
_CHAT_OPS = (
    ChatOp("set_argument_element", ("elements",),
           "Make a factor the conclusion (what is argued for), a claim (a premise, objection or rebuttal) or "
           "the question the conclusion answers."),
    ChatOp("set_argument_link", ("links",),
           "How a premise bears on a claim ('Premise -> Claim'): supports or attacks; a reason name shared by "
           "premises that only work together; the warrant (why it bears) and qualifier (certainly, probably, "
           "possibly)."),
    ChatOp("set_argument_claim", ("claims",),
           "A person's assessment of a claim taken as given: accepted or rejected, with the rationale."),
)

register(Formalism(
    model_type="argument_map",
    outcome_role="conclusion",
    outcome_refusal="An argument map's outcome is its conclusion: `latris argument element <factor> conclusion`.",
    outcome_ids=_outcome_ids,
    set_outcome=_set_outcome,
    structure_problems=_problems,
    validators={
        "am_structure": ("am_no_conclusion", "am_many_conclusions", "am_many_questions", "am_conclusion_not_top"),
        "am_conclusion_argued": ("am_no_reasons",),
    },
    whole_label="(map)",
    claims=_claims,
    centrality=False,
    own_implications=True,
    sensitivity_fallback="Link reasons and objections to the conclusion to see what it turns on.",
    results=(ResultKind(tool=ChatTool(*_TOOLS["argument-analysis"]),
                        kind="argument-analysis", title="Argument map: does the conclusion stand?",
                        render=_render, analysis="argument_analyse", run=_run, definition=_definition),),
    # The evaluation reads each claim's citations (checked or not) and the open challenges on links.
    fingerprint_files=lambda paths: [paths.evidence_links_yaml, paths.challenges_yaml],
    spec_field="argument_map",
    spec_check=_check,
    spec_apply=_apply,
    spec_export=_export,
    chat_ops=_CHAT_OPS,
    mermaid=_mermaid,
    diagram_direction="TB",
    cli=("latris.cli.argument_cmd", "argument"),
    routes="latris.server.routes.argument",
))
