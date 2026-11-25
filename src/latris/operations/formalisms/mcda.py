"""MCDA as a formalism plugin — options against weighted criteria (``operations/mcda.py``)."""

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


def _reversal_lines(p: dict[str, Any]) -> list[str]:
    out = []
    for r in p["rank_reversal"]:
        moves = []
        if r["down"]:
            if r["down"].get("tie"):
                moves.append(f"ties with {r['down']['option']} at {r['down']['weight']:.0%} (the top choice holds "
                             "to the limit)")
            else:
                moves.append(f"falls to {r['down']['weight']:.0%} ({r['down']['option']} first)")
        if r["up"]:
            if r["up"].get("tie"):
                moves.append(f"ties with {r['up']['option']} at {r['up']['weight']:.0%} (the top choice holds "
                             "to the limit)")
            else:
                moves.append(f"rises to {r['up']['weight']:.0%} ({r['up']['option']} first)")
        out.append(f"{r['criterion']} (weight {r['weight']:.0%}): "
                   + (" or ".join(moves) if moves else "no weight from 0 to 100% changes the top choice"))
    return out


def _render(p: dict[str, Any]) -> list[str]:
    from latris.exporters import md
    from latris.operations.mcda import describe

    out = [describe(p) + ".", ""]
    crits = p["criteria"]
    rows = [[r["option"], f"{r['total']:.1f}", *(f"{r['contributions'][c]:.1f}" for c in crits)] for r in p["ranking"]]
    out += md.table(["Option", "Total (of 100)", *crits], rows)
    rows = [[w["criterion"], f"{w['weight']:.0%}", f"{w['direction']} is better",
             f"{w['worst']:g} → {w['best']:g}" + (f" {w['units']}" if w["units"] else "")
             + (" (options' range)" if w["local_scale"] else ""),
             (w["source"] or "—") + ("; not verified" if w["weak"] else "")] for w in p["weights"]]
    out += ["Swing weights: how much moving from the worst to the best of each scale matters, relative to the "
            "other criteria's swings.", ""]
    out += md.table(["Criterion", "Weight", "Direction", "Scale (worst → best)", "Weight's source"], rows)
    if p["rank_reversal"]:
        out += ["How far each weight would have to move, others keeping their proportions, before the top "
                "choice changes:", ""]
        out += [f"- {line}" for line in _reversal_lines(p)] + [""]
    if p["dominated"]:
        out += ["Dominated (no better on any criterion, worse on at least one): "
                + "; ".join(f"{d['option']} by {d['by']}" for d in p["dominated"]) + ".", ""]
    if p["margin"] and p["margin"]["unverified_scores"]:
        out += [f"The margin of {p['margin']['first']} over {p['margin']['second']} rests on scores nobody has "
                f"verified: {', '.join(p['margin']['unverified_scores'])}.", ""]
    if p["flat"]:
        out += ["Every option scores the same on " + ", ".join(p["flat"]) + ", so it can't separate them.", ""]
    if p["outside"]:
        out += ["Scores outside the stated scale, clamped to its end: " + ", ".join(p["outside"]) + ". "
                "Check the score or widen the scale.", ""]
    if any(w["local_scale"] for w in p["weights"]):
        out += ["Scales taken from the options' own range change when an option is added or removed, and the "
                "weights then need revisiting.", ""]
    return out


def _charts(p: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = [("mcda-contributions", {})]
    if p["rank_reversal"]:
        out.append(("mcda-swing", {}))
    return out


def _claims(paths, section: str) -> list[str]:
    from latris.operations import mcda

    p = mcda.analyse(root=paths.root)
    if p["problems"]:
        return [f"The MCDA is incomplete: {len(p['problems'])} structure problem(s) (e.g. {p['problems'][0]['label']}: "
                f"{p['problems'][0]['message']})"] if section == "structure" else []
    claims: list[str] = []
    near = mcda.closest_reversal(p)
    if section == "structure":
        claims.append(f"{len(p['options'])} options judged on {len(p['criteria'])} criteria: "
                      + ", ".join(f"{w['criterion']} ({w['weight']:.0%})" for w in p["weights"]) + ".")
    elif section == "answer":
        claims.append(mcda.describe(p) + ".")
        claims.append("Ranking: " + "; ".join(f"{r['option']} {r['total']:.0f}" for r in p["ranking"]) + " (of 100).")
        m = p["margin"]
        if m:
            lead = [b for b in m["by_criterion"] if b["points"] > 0][:2]
            if lead:
                claims.append(f"{m['first']} leads {m['second']} by {m['points']:.1f} points, mostly on "
                              + " and ".join(b["criterion"] for b in lead) + ".")
    elif section == "sensitivity":
        claims += _reversal_lines(p)
        if p["margin"] and p["margin"]["unverified_scores"]:
            weak = ", ".join(p["margin"]["unverified_scores"])
            claims.append(f"The winning margin rests on unverified scores: {weak}.")
    elif section == "implications":
        if near and near.get("tie"):
            claims.append(f"{near['option']} only draws level if the weight on {near['criterion']} reaches "
                          f"{near['to']:.0%} — the choice holds across the whole range.")
        elif near and near["gap"] < 0.1:
            claims.append(f"The choice is fragile: a {near['gap']:.0%} shift in the weight on {near['criterion']} "
                          f"puts {near['option']} first — agree that weight before deciding.")
        elif near:
            claims.append(f"The choice holds unless the weight on {near['criterion']} moves from {near['from']:.0%} to "
                          f"{near['to']:.0%}.")
        else:
            claims.append("No single weight change reverses the top choice.")
        if p["dominated"]:
            claims.append("Dominated options can be set aside whatever the weights: "
                          + ", ".join(d["option"] for d in p["dominated"]) + ".")
    elif section == "gaps":
        unsourced = [w["criterion"] for w in p["weights"] if not w["source"]]
        if unsourced:
            claims.append(f"Weights with no recorded source (whose judgement are they?): {', '.join(unsourced)}.")
        if p["unverified_scores"]:
            claims.append(f"{p['unverified_scores']} score(s) not verified against their source.")
        local = [w["criterion"] for w in p["weights"] if w["local_scale"]]
        if local:
            claims.append(f"Criteria scored on the options' own range rather than a stated scale: {', '.join(local)}.")
        if p["flat"]:
            claims.append(f"Criteria on which every option scores the same (they can't separate them): "
                          f"{', '.join(p['flat'])}.")
        if p["outside"]:
            claims.append(f"Scores outside the stated scale, clamped to its end: {', '.join(p['outside'])}.")
    return claims


def _mermaid(paths, entities, edges) -> str:
    from latris.exporters.mermaid import _mermaid_text
    from latris.operations import mcda

    p = mcda.analyse(root=paths.root)
    if p["problems"]:
        return ""
    lines = ["flowchart TB", '    goal(["Choice"])']
    for i, w in enumerate(p["weights"]):
        lines.append(f'    c{i}["{_mermaid_text(w["criterion"])}<br/>{w["weight"]:.0%}"]')
        lines.append(f"    goal --- c{i}")
    lines.append('    subgraph ranked["Options, best first"]')
    lines += [f'        o{i}(["{i + 1}. {_mermaid_text(r["option"])}<br/>{r["total"]:.0f}"])'
              for i, r in enumerate(p["ranking"])]
    lines.append("    end")
    return "\n".join(lines) + "\n"


def _problems(root: Path) -> list:
    from latris.operations import mcda

    return mcda.structure_problems(root=root)


def _check(block, known, outcome: str | None) -> list[str]:
    names = ([("mcda element", x.node) for x in block.elements] + [("mcda criterion", x.node) for x in block.criteria]
             + [("mcda score", n) for x in block.scores for n in (x.option, x.criterion)])
    return [f"{where}: no factor named {n!r}" for where, n in names if not known(n)]


def _apply(block, verified_by: str, root: Path) -> int:
    from latris.operations import mcda

    n = 0
    for e in block.elements:
        mcda.set_element(e.node, e.type, root=root)
        n += 1
    for c in block.criteria:
        fields = {k: v for k, v in (("weight", c.weight), ("direction", c.direction), ("worst", c.worst),
                                    ("best", c.best), ("units", c.units), ("notes", c.notes)) if v is not None}
        mcda.set_criterion(c.node, **fields, origin=c.origin or default_origin(verified_by), source_id=c.source,
                           verification=spec_verification(c.verified, verified_by), root=root)
        n += 1
    for s in block.scores:
        mcda.set_score(s.option, s.criterion, s.value, origin=s.origin or default_origin(verified_by),
                       source_id=s.source, verification=spec_verification(s.verified, verified_by), notes=s.notes,
                       root=root)
        n += 1
    return n


def _export(paths, labels: dict[str, str]):
    from latris.operations import mcda
    from latris.schema.build_spec import SpecMCDA, SpecMCDACriterion, SpecMCDAElement, SpecMCDAScore

    elements = sorted((SpecMCDAElement(node=labels[k], type=v) for k, v in mcda.get_elements(root=paths.root).items()
                       if k in labels), key=lambda e: (e.type, e.node))
    if not elements:
        return None
    crits = [SpecMCDACriterion(node=labels[c.target_id], weight=c.weight, direction=c.direction, worst=c.worst,
                               best=c.best, units=c.units, notes=c.notes, source=c.source_id, origin=c.origin,
                               verified=c.verification == "human-verified")
             for c in mcda.get_criteria(root=paths.root).entries if c.target_id in labels]
    scores = [SpecMCDAScore(option=labels[s.target_id], criterion=labels[s.criterion], value=s.value, notes=s.notes,
                            source=s.source_id, origin=s.origin, verified=s.verification == "human-verified")
              for s in mcda.get_scores(root=paths.root).entries if s.target_id in labels and s.criterion in labels]
    return SpecMCDA(elements=elements, criteria=crits, scores=scores)


def _run(a, root: Path) -> str:
    from latris.operations import mcda

    payload = mcda.analyse(root=root)
    if payload["problems"]:
        raise ValueError(mcda.describe(payload))
    return mcda.record(payload, root=root)[1]


def _definition(payload: dict[str, Any]):
    from latris.schema.build_spec import make_analysis

    return make_analysis(kind="mcda_analyse")



# How a chat assistant runs each analysis (latris-app generates the tool from the manifest).
_TOOLS = {
    'mcda-analysis': ('analyse_mcda',
        "Rank the options of a multi-criteria decision analysis: each option's weighted score with every "
        "criterion's contribution, dominated options, and how far each weight would have to move before "
        'the top choice changes, flagging unverified scores the margin rests on. Recorded with charts.'),
}


# How a chat assistant writes this type's build-spec block (latris-app generates each operation).
_CHAT_OPS = (
    ChatOp('set_mcda_element', ('elements',),
        'Make a factor an option or a criterion of the decision.'),
    ChatOp('set_mcda_criterion', ('criteria',),
        "A criterion's weight (any positive number; weights are normalised), its direction (higher or "
        'lower is better), its worst and best values and units, and the source of the weight.'),
    ChatOp('set_mcda_score', ('scores',),
        "One option's score on one criterion, with its source."),
)

register(Formalism(
    connected_structure=False,
    model_type="mcda",
    predictor="latris.operations.predictors.mcda",
    outcome_role=None,
    outcome_refusal=("An MCDA's result is the ranking of its options, not one outcome factor: give factors the "
                     "element 'option' or 'criterion' (latris mcda element <factor> option)."),
    outcome_ids=lambda paths: set(),
    structure_problems=_problems,
    validators={
        "mcda_elements_present": ("mcda_too_few_options", "mcda_no_criterion"),
        "mcda_criteria_complete": ("mcda_no_weight", "mcda_no_direction"),
        "mcda_scores_complete": ("mcda_missing_score",),
    },
    claims=_claims,
    centrality=False,
    own_implications=True,
    sensitivity_fallback="Complete the weights and scores to see how firm the choice is.",
    results=(ResultKind(tool=ChatTool(*_TOOLS['mcda-analysis']),
                        kind="mcda-analysis", title="Multi-criteria decision analysis", render=_render,
                        analysis="mcda_analyse", run=_run, definition=_definition, charts=_charts,
                        chart_kinds=("mcda-contributions", "mcda-swing")),),
    spec_field="mcda",
    spec_check=_check,
    spec_apply=_apply,
    spec_export=_export,
    chat_ops=_CHAT_OPS,
    mermaid=_mermaid,
    cli=("latris.cli.mcda_cmd", "mcda"),
    routes="latris.server.routes.mcda",
))
