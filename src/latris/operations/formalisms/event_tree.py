"""Event tree as a formalism plugin — yes/no headings from one initiating event (``operations/event_tree.py``)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from latris.operations.formalisms import (
    Formalism,
    ResultKind,
    _risk_mc,
    register,
)


def _claims(paths, section: str) -> list[str]:
    """Event-tree claims for one section, from the live analysis."""
    from latris.operations import event_tree

    p = event_tree.analyse(root=paths.root)
    if p["problems"]:
        if section == "structure":
            return [f"The event tree is incomplete: {len(p['problems'])} structure problem(s) "
                    f"(e.g. {p['problems'][0]['label']}: {p['problems'][0]['message']})"]
        return []
    fr = p["frequency"]
    claims: list[str] = []
    if section == "structure":
        claims.append(event_tree.describe(p) + ".")
        claims.append("Headings, in order: " + " → ".join(p["headings"]) + ".")
    elif section == "answer" and p["quantified"]:
        for d in p["end_states"]:
            amount = f"{d['frequency']:.3g} per year" if fr else f"probability {d['probability']:.3g}"
            claims.append(f"{d['end_state']}: {amount}, mostly through {d['dominant']['text']} "
                          f"({d['dominant']['share']:.0%}).")
        if not fr:
            claims.append(f"These are probabilities given that {p['initiator']} happens; give it a frequency for "
                          "rates per year.")
    elif section == "sensitivity" and p["quantified"]:
        weak = sorted({v["heading"] for v in p["values"] if v["weak"]})
        on_top = sorted({h for d in p["end_states"] for r in p["sequences"] if r["n"] == d["dominant"]["n"]
                         for h in r["unverified"]})
        if on_top:
            claims.append(f"Branch probabilities on the dominant sequences that nobody has verified: "
                          f"{', '.join(on_top)} — these move the answer most directly.")
        elif weak:
            claims.append(f"Branch probabilities nobody has verified: {', '.join(weak)}.")
        if fr and fr["weak"]:
            claims.append(f"The frequency of {p['initiator']} scales every result and hasn't been verified.")
    elif section == "implications" and p["quantified"]:
        for d in p["end_states"]:
            claims.append(f"To make {d['end_state']} rarer, look first at sequence #{d['dominant']['n']}: "
                          f"{d['dominant']['text']}.")
    elif section == "gaps":
        if p["missing"]:
            claims.append("Not quantified — missing: " + "; ".join(p["missing"][:5])
                          + (f" (+{len(p['missing']) - 5} more)." if len(p["missing"]) > 5 else "."))
        if not fr:
            claims.append(f"No frequency for {p['initiator']}, so results are conditional probabilities.")
        unsourced = sorted({v["heading"] for v in p["values"] if not v["source"]})
        if unsourced:
            claims.append(f"Branch probabilities with no stated source: {', '.join(unsourced)}.")
    return claims


def _charts(p: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    return [("et-endstates", {})] if p.get("quantified") else []


def _render(p: dict[str, Any]) -> list[str]:
    from latris.exporters.results import _MAX_ROWS, _esc, _f, _table  # noqa: F401
    from latris.operations.event_tree import describe

    out = [describe(p) + ".", ""]
    fr = p.get("frequency")
    if fr:
        out += [f"Initiating event {p['initiator']}: {_f(fr['per_year'])} per year"
                + (f" ({fr['source']})" if fr.get("source") else "") + ".", ""]
    heads = p["headings"]
    rows = []
    for r in p["sequences"][: _MAX_ROWS * 3]:
        ans = {a["heading"]: a["answer"] for a in r["answers"]}
        rows.append([str(r["n"])] + [ans.get(h, "·") for h in heads] + [r["end_state"], _f(r["probability"])]
                    + ([_f(r["frequency"])] if fr else []))
    if rows:
        out += _table(["#", *heads, "End state", "Probability"] + (["Per year"] if fr else []), rows)
    if p.get("quantified"):
        rows = [[d["end_state"], _f(d["probability"])] + ([_f(d["frequency"])] if fr else [])
                + [f"#{d['dominant']['n']} ({d['dominant']['text']})"] for d in p["end_states"]]
        out += _table(["End state", "Probability"] + (["Per year"] if fr else []) + ["Dominant sequence"], rows)
        weak = sorted({v["heading"] for v in p["values"] if v["weak"]})
        if weak:
            out += [f"Branch probabilities nobody has verified: {', '.join(weak)}.", ""]
    return out


def _mermaid(paths) -> str:
    """The tree drawn from its sequences: a question node per branch point, yes/no edges, end states as leaves."""
    from latris.exporters.mermaid import _mermaid_text
    from latris.operations.event_tree import analyse

    p = analyse(root=paths.root)
    if p["problems"] or not p["sequences"]:
        return ""
    lines = ["flowchart LR", f'    s0(["{_mermaid_text(p["initiator"])}"])']
    questions: dict[tuple, str] = {}  # answers so far → the question node asked there

    def edge(src: str, answer: str | None, dst: str) -> None:
        lines.append(f"    {src} -->|{answer}| {dst}" if answer else f"    {src} --> {dst}")

    for r in p["sequences"]:
        prefix: tuple = ()
        src, via = "s0", None
        for a in r["answers"]:
            node = questions.get(prefix)
            if node is None:
                node = questions[prefix] = f"q{len(questions) + 1}"
                lines.append(f'    {node}{{"{_mermaid_text(a["heading"])}?"}}')
                edge(src, via, node)
            src, via = node, a["answer"]
            prefix = prefix + ((a["heading"], a["answer"]),)
        text = _mermaid_text(r["end_state"])
        if r["probability"] is not None:
            text += f"<br/>p = {r['probability']:.3g}"
        leaf = f"e{r['n']}"
        lines.append(f'    {leaf}["{text}"]')
        edge(src, via, leaf)
    return "\n".join(lines) + "\n"


def _export(paths, labels: dict[str, str]):  # noqa: ANN001, ANN202
    """Event-tree elements, heading order, sequences, probabilities and frequency as spec entries."""
    from latris.operations import event_tree as et
    from latris.schema.build_spec import (
        SpecETElement,
        SpecETFrequency,
        SpecETProbability,
        SpecETSequence,
        SpecEventTree,
    )
    from latris.schema.event_tree import ET_ELEMENTS

    elements = sorted(
        (SpecETElement(node=labels[eid], type=t) for eid, t in et.get_elements(root=paths.root).items()
         if eid in labels),
        key=lambda e: (ET_ELEMENTS.index(e.type), e.node),
    )
    if not elements:
        return None
    s = et.get_structure(root=paths.root)
    ok = all(h in labels for h in s.headings)
    seqs = [
        SpecETSequence(answers={labels[x.heading]: x.answer for x in q.path}, end_state=labels[q.end_state])
        for q in s.sequences
        if q.end_state in labels and all(x.heading in labels for x in q.path)
    ]
    probs = [
        SpecETProbability(node=labels[p.target_id], p_yes=p.p_yes, given={labels[c.heading]: c.answer for c in p.given},
                          source=p.source_id, origin=p.origin, verified=p.verification == "human-verified",
                          notes=p.notes)
        for p in et.get_probabilities(root=paths.root).entries
        if p.target_id in labels and all(c.heading in labels for c in p.given)
    ]
    f = next((x for x in et.get_frequencies(root=paths.root).entries if x.target_id in labels), None)
    freq = SpecETFrequency(node=labels[f.target_id], frequency=f.frequency, source=f.source_id, origin=f.origin,
                           verified=f.verification == "human-verified", notes=f.notes) if f else None
    return SpecEventTree(elements=elements, order=[labels[h] for h in s.headings] if ok else [], sequences=seqs,
                         probabilities=probs, frequency=freq,
                         uncertainty=_risk_mc.spec_export("event_tree", paths, labels))


def _apply(spec_et, verified_by: str, root: Path) -> int:
    """Elements, then the heading order, then sequences, probabilities and the initiating frequency."""
    from latris.operations import event_tree as et_ops

    default_origin = "ai-proposed" if verified_by == "ai" else "human-direct"

    def verification(v: bool) -> str:
        return "human-verified" if v and verified_by == "human" else "unverified"

    n = 0
    for e in spec_et.elements:
        et_ops.set_element(e.node, e.type, root=root)
        n += 1
    if spec_et.order:
        et_ops.set_order(spec_et.order, root=root)
        n += 1
    for s in spec_et.sequences:
        et_ops.set_sequence(s.end_state, list(s.answers.items()), root=root)
        n += 1
    for p in spec_et.probabilities:
        et_ops.set_probability(p.node, p.p_yes, given=list(p.given.items()), origin=p.origin or default_origin,
                               source_id=p.source, verification=verification(p.verified), notes=p.notes, root=root)
        n += 1
    if spec_et.frequency:
        f = spec_et.frequency
        et_ops.set_frequency(f.node, f.frequency, origin=f.origin or default_origin, source_id=f.source,
                             verification=verification(f.verified), notes=f.notes, root=root)
        n += 1
    return n + _risk_mc.spec_apply("event_tree", spec_et.uncertainty, verified_by, root)


def _outcome_ids(paths) -> set[str]:
    from latris.operations import event_tree

    return {eid for eid, t in event_tree.get_elements(root=paths.root).items() if t == "end_state"}


def _problems(root: Path) -> list:
    from latris.operations import event_tree

    return event_tree.structure_problems(root=root)


def _check(block, known, outcome: str | None) -> list[str]:
    names = ([("event_tree element", x.node) for x in block.elements]
             + [("event_tree order", x) for x in block.order]
             + [("event_tree sequence", x.end_state) for x in block.sequences]
             + [("event_tree sequence", h) for x in block.sequences for h in x.answers]
             + [("event_tree probability", x.node) for x in block.probabilities]
             + [("event_tree probability", h) for x in block.probabilities for h in x.given]
             + ([("event_tree frequency", block.frequency.node)] if block.frequency else []))
    return ([f"{where}: no factor named {n!r}" for where, n in names if not known(n)]
            + _risk_mc.spec_check("event_tree", block.uncertainty, known))


def _run(a, root: Path) -> str:
    from latris.operations import event_tree

    payload = event_tree.analyse(root=root)
    if payload["problems"]:
        raise ValueError(event_tree.describe(payload))
    return event_tree.record(payload, root=root)[1]


def _definition(payload: dict[str, Any]):
    from latris.schema.build_spec import SpecAnalysis

    return SpecAnalysis(kind="et_analyse")


register(Formalism(
    model_type="event_tree",
    outcome_role=None,
    outcome_refusal=(
        "An event tree's outcomes are its end states: give the factor the element 'end_state' "
        "(latris et element <factor> end_state)."
    ),
    outcome_ids=_outcome_ids,
    structure_problems=_problems,
    validators={
        "et_elements_classified": ("et_no_initiator", "et_many_initiators", "et_no_end_state"),
        "et_headings_ordered": ("et_heading_unordered", "et_bad_heading"),
        "et_sequences_complete": ("et_no_sequences", "et_duplicate", "et_bad_sequence", "et_overlap",
                                  "et_inconsistent", "et_missing_branch", "et_heading_unused",
                                  "et_end_state_unused"),
    },
    whole_label="(tree)",
    claims=_claims,
    centrality=False,
    own_implications=True,
    sensitivity_fallback="Give every heading its probability to see which values move the result.",
    results=(ResultKind(kind="et-analysis", title="Event tree: sequences and end states", render=_render,
                        analysis="et_analyse", run=_run, definition=_definition, charts=_charts,
                        chart_kinds=("et-endstates",)),
             _risk_mc.result_kind("event_tree")),
    spec_field="event_tree",
    spec_check=_check,
    spec_apply=_apply,
    spec_export=_export,
    mermaid=lambda paths, entities, edges: _mermaid(paths),
    cli=("latris.cli.et_cmd", "et"),
    routes="latris.server.routes.et",
))
