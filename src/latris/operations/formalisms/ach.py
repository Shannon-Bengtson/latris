"""ACH as a formalism plugin — competing hypotheses against the evidence (``operations/ach.py``)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from latris.operations.formalisms import ChatTool, Formalism, ResultKind, default_origin, register, spec_verification

_SOURCE_WORDS = {"checked": "its source checked", "cited": "a source not yet checked", "none": "no source",
                 "contested": "a source against it"}


def _render(p: dict[str, Any]) -> list[str]:
    from latris.exporters.results import _table
    from latris.operations.ach import describe

    out = [describe(p) + ".", ""]
    rows = [[r["hypothesis"], f"{r['inconsistency']:.2f}", ", ".join(r["against"]) or "—", str(r["consistent"])]
            for r in p["ranking"]]
    out += ["Hypotheses, least evidence against first (Heuer: favour the hypothesis the evidence fails to rule "
            "out, not the one with most in its favour).", ""]
    out += _table(["Hypothesis", "Weighted inconsistency", "Evidence against it", "Consistent items"], rows)
    hyps = p["hypotheses"]
    rows = [[m["item"], *(m["ratings"][h] for h in hyps), f"{m['credibility']}/{m['relevance']}",
             _SOURCE_WORDS[m["sources"]]] for m in p["matrix"]]
    out += _table(["Evidence", *hyps, "Credibility/relevance", "Source"], rows)
    out += ["CC very consistent · C consistent · N neutral or not applicable · I inconsistent · II very "
            "inconsistent.", ""]
    if p["linchpins"]:
        out += ["Linchpins — without any one of these the lead would change or be tied: "
                + "; ".join(f"{x['item']} ({_SOURCE_WORDS[x['sources']]})" for x in p["linchpins"]) + ".", ""]
    if p["non_diagnostic"]:
        out += ["Rated the same against every hypothesis, so they don't help choose: "
                + ", ".join(p["non_diagnostic"]) + ".", ""]
    return out


def _charts(p: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    return [("ach-matrix", {})] if p.get("matrix") else []


def _claims(paths, section: str) -> list[str]:
    from latris.operations import ach

    p = ach.analyse(root=paths.root)
    if p["problems"]:
        return [f"The ACH matrix is incomplete: {len(p['problems'])} structure problem(s) (e.g. "
                f"{p['problems'][0]['label']}: {p['problems'][0]['message']})"] if section == "structure" else []
    claims: list[str] = []
    if section == "structure":
        claims.append(f"{len(p['hypotheses'])} hypotheses weighed against {len(p['items'])} evidence items.")
    elif section == "answer":
        claims.append(ach.describe(p) + ".")
        for r in p["ranking"][len(p["leading"]):]:
            if r["against"]:
                claims.append(f"{r['hypothesis']} is contradicted by: {', '.join(r['against'][:4])}.")
    elif section == "sensitivity":
        for x in p["linchpins"]:
            claims.append(f"The conclusion turns on {x['item']} ({_SOURCE_WORDS[x['sources']]}, credibility "
                          f"{x['credibility']}).")
        if not p["linchpins"]:
            claims.append("No single evidence item changes the leading hypothesis.")
    elif section == "implications":
        if len(p["ranking"]) >= 2:
            a, b = p["ranking"][0]["hypothesis"], p["ranking"][1]["hypothesis"]
            claims.append(f"Look next for evidence that would be inconsistent with {a} but not {b}, or the reverse.")
        weak = [x["item"] for x in p["linchpins"] if x["sources"] != "checked"]
        if weak:
            claims.append(f"Check the sources behind these linchpins first: {', '.join(weak)}.")
        if p["non_diagnostic"]:
            claims.append(f"These items don't discriminate and can be set aside: {', '.join(p['non_diagnostic'])}.")
    elif section == "gaps":
        none = [m["item"] for m in p["matrix"] if m["sources"] == "none"]
        if none:
            claims.append(f"Evidence items with no source: {', '.join(none)}.")
        if p["unverified_ratings"]:
            claims.append(f"{p['unverified_ratings']} rating(s) not reviewed by a person"
                          + (f" ({p['ai_ratings']} proposed by AI)." if p["ai_ratings"] else "."))
    return claims


def _mermaid(paths, entities, edges) -> str:
    from latris.exporters.mermaid import _mermaid_text
    from latris.operations import ach

    p = ach.analyse(root=paths.root)
    if p["problems"]:
        return ""
    lines = ["flowchart LR"]
    hid = {h: f"h{i}" for i, h in enumerate(p["hypotheses"])}
    for r in p["ranking"]:
        lines.append(f'    {hid[r["hypothesis"]]}(["{_mermaid_text(r["hypothesis"])}<br/>against: '
                     f'{r["inconsistency"]:.2f}"])')
    for j, m in enumerate(p["matrix"]):
        against = [(h, v) for h, v in m["ratings"].items() if v in ("I", "II")]
        if not against:
            continue
        lines.append(f'    e{j}["{_mermaid_text(m["item"])}"]')
        lines += [f"    e{j} -.->|{v}| {hid[h]}" for h, v in against]
    return "\n".join(lines) + "\n"


def _problems(root: Path) -> list:
    from latris.operations import ach

    return ach.structure_problems(root=root)


def _check(block, known, outcome: str | None) -> list[str]:
    names = ([("ach element", x.node) for x in block.elements] + [("ach item", x.node) for x in block.items]
             + [("ach rating", n) for x in block.ratings for n in (x.item, x.hypothesis)])
    return [f"{where}: no factor named {n!r}" for where, n in names if not known(n)]


def _apply(block, verified_by: str, root: Path) -> int:
    from latris.operations import ach

    n = 0
    for e in block.elements:
        ach.set_element(e.node, e.type, root=root)
        n += 1
    for it in block.items:
        ach.set_item(it.node, credibility=it.credibility, relevance=it.relevance, notes=it.notes,
                     origin=it.origin or default_origin(verified_by), source_id=it.source,
                     verification=spec_verification(it.verified, verified_by), root=root)
        n += 1
    for r in block.ratings:
        ach.set_rating(r.item, r.hypothesis, r.rating, rationale=r.rationale,
                       origin=r.origin or default_origin(verified_by),
                       verification=spec_verification(r.verified, verified_by), root=root)
        n += 1
    return n


def _export(paths, labels: dict[str, str]):
    from latris.operations import ach
    from latris.schema.build_spec import SpecACH, SpecACHElement, SpecACHItem, SpecACHRating

    elements = sorted((SpecACHElement(node=labels[k], type=v) for k, v in ach.get_elements(root=paths.root).items()
                       if k in labels), key=lambda e: (e.type, e.node))
    if not elements:
        return None
    items = [SpecACHItem(node=labels[i.target_id], credibility=i.credibility, relevance=i.relevance, notes=i.notes,
                         source=i.source_id, origin=i.origin, verified=i.verification == "human-verified")
             for i in ach.get_items(root=paths.root).entries if i.target_id in labels]
    ratings = [SpecACHRating(item=labels[r.target_id], hypothesis=labels[r.hypothesis], rating=r.rating,
                             rationale=r.rationale, origin=r.origin, verified=r.verification == "human-verified")
               for r in ach.get_ratings(root=paths.root).entries
               if r.target_id in labels and r.hypothesis in labels]
    return SpecACH(elements=elements, items=items, ratings=ratings)


def _run(a, root: Path) -> str:
    from latris.operations import ach

    payload = ach.analyse(root=root)
    if payload["problems"]:
        raise ValueError(ach.describe(payload))
    return ach.record(payload, root=root)[1]


def _definition(payload: dict[str, Any]):
    from latris.schema.build_spec import make_analysis

    return make_analysis(kind="ach_analyse")



# How a chat assistant runs each analysis (latris-app generates the tool from the manifest).
_TOOLS = {
    'ach-analysis': ('analyse_ach',
        'Analysis of competing hypotheses: the hypotheses ranked by how much evidence is inconsistent '
        "with them (the one the evidence fails to rule out first), items that don't discriminate, and the "
        'linchpins the conclusion turns on. Recorded with a chart.'),
}

register(Formalism(
    model_type="ach",
    outcome_role=None,
    outcome_refusal=("ACH weighs competing hypotheses rather than explaining one outcome: give factors the "
                     "element 'hypothesis' or 'evidence_item' (latris ach element <factor> hypothesis)."),
    outcome_ids=lambda paths: set(),
    structure_problems=_problems,
    validators={
        "ach_elements_present": ("ach_too_few_hypotheses", "ach_no_items"),
        "ach_matrix_complete": ("ach_missing_rating",),
    },
    whole_label="(matrix)",
    claims=_claims,
    centrality=False,
    own_implications=True,
    sensitivity_fallback="Rate every item against every hypothesis to find the linchpins.",
    results=(ResultKind(tool=ChatTool(*_TOOLS['ach-analysis']),
                        kind="ach-analysis", title="Competing hypotheses", render=_render, analysis="ach_analyse",
                        run=_run, definition=_definition, charts=_charts,
                        chart_kinds=("ach-matrix",)),),
    # The analysis reads each item's own citations (checked or not).
    fingerprint_files=lambda paths: [paths.evidence_links_yaml],
    spec_field="ach",
    spec_check=_check,
    spec_apply=_apply,
    spec_export=_export,
    mermaid=_mermaid,
    cli=("latris.cli.ach_cmd", "ach"),
    routes="latris.server.routes.ach",
))
