"""Report fixes from a real agent run (Claude.ai building a CLD with the CLI).

The client pack is what a shared report link shows, so it must read well to
someone outside the modelling work: no internal IDs, the reason behind each
link, sources by name, and a short history rather than the whole log.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from latris.cli.app import app
from latris.exporters import markdown as md_exporter
from latris.exporters import narrative
from latris.operations import edges as edge_ops
from latris.operations import evidence as evidence_ops
from latris.operations import nodes as node_ops
from latris.operations import references as ref_ops
from latris.operations import view_attributes as view_attr_ops
from latris.operations.init import init_project
from latris.repo.layout import ProjectPaths


@pytest.fixture
def project(tmp_path: Path, git_identity) -> Path:
    root = tmp_path / "vol"
    init_project(root, statement="Why do volunteers leave?")
    a, _ = node_ops.add_node("Workload", kind="variable", root=root)
    b, _ = node_ops.add_node("Burnout", kind="state", root=root)
    e, _ = edge_ops.add_edge(a.id, b.id, kind="causal", root=root)
    view_attr_ops.set_view_attribute(e.id, "cld", "polarity", "+", rationale="More hours, more exhaustion.", root=root)
    ref_ops.add_reference("smith2021", "Volunteer burnout", authors=["Smith, J", "Lee, K"], year=2021, root=root)
    evidence_ops.add_evidence(e.id, "polarity", "smith2021", root=root)
    return root


def test_client_pack_reads_without_internal_ids(project: Path) -> None:
    out = md_exporter.render(ProjectPaths(project), pack="client", ai=False)
    assert "`node_" not in out and "`edge_" not in out
    # Two node kinds, so Kind stays; no descriptions, so that column goes.
    assert "| Kind | Label |" in out and "| Description |" not in out
    # The reason behind a link is shown.
    assert "More hours, more exhaustion." in out
    # Evidence names the link and the source, and the sources are listed.
    assert "Workload → Burnout" in out
    # Sources by name, not by their internal key.
    assert "### Smith & Lee (2021), *Volunteer burnout*" in out
    assert "smith2021" not in out
    assert "## References" in out


def test_full_report_keeps_ids_for_agents(project: Path) -> None:
    out = md_exporter.render(ProjectPaths(project), ai=False)
    assert "| `node_" in out and "| `edge_" in out


def test_history_is_summarised_not_dumped(project: Path) -> None:
    for i in range(12):
        node_ops.add_node(f"Factor {i}", root=project)
    out = md_exporter.render(ProjectPaths(project), pack="review", ai=False)
    history = out.split("## Model History", 1)[1].split("\n## ", 1)[0]
    assert "recorded changes" in history
    assert history.count("\n- **") == narrative._HISTORY_SHOWN


def test_rationale_updates_when_polarity_is_set_again(project: Path) -> None:
    edge = edge_ops.list_edges(root=project)[0]
    view_attr_ops.set_view_attribute(edge.id, "cld", "polarity", "+", rationale="Reworded reason.", root=project)
    out = md_exporter.render(ProjectPaths(project), pack="client", ai=False)
    assert "Reworded reason." in out
    assert "More hours, more exhaustion." not in out


def test_report_skips_ai_quietly_without_a_key(project: Path, monkeypatch) -> None:
    monkeypatch.delenv("LATRIS_AI_MOCK", raising=False)
    monkeypatch.delenv("GRAPH_TOOLING_AI_MOCK", raising=False)
    monkeypatch.setattr("latris.ai.credentials.get_key", lambda provider: None)

    def boom(*_a, **_k):
        raise AssertionError("an AI call was attempted without a key")

    monkeypatch.setattr("latris.ai.adapters.get_adapter", boom)
    out = md_exporter.render(ProjectPaths(project), pack="client")
    assert "## Model Structure" in out


def test_finding_add(project: Path, monkeypatch) -> None:
    monkeypatch.chdir(project)
    result = CliRunner().invoke(
        app,
        ["--json", "finding", "add", "Workload drives burnout in a reinforcing loop.",
         "--category", "structure", "--target", "Workload", "--detail", "From `latris analyse loops`."],
    )
    assert result.exit_code == 0, result.output
    finding = json.loads(result.stdout.strip().splitlines()[-1])["result"]
    assert finding["category"] == "structure"
    # Proposed findings show in the review pack; the client pack says they wait.
    assert "Workload drives burnout in a reinforcing loop." in md_exporter.render(
        ProjectPaths(project), pack="review", ai=False
    )
    client = md_exporter.render(ProjectPaths(project), pack="client", ai=False)
    assert "1 draft finding is not shown here until a person approves it" in client
    assert "latris mature" not in client

    bad = CliRunner().invoke(app, ["finding", "add", "x", "--category", "vibes"])
    assert bad.exit_code == 2


def test_history_names_things_instead_of_ids(project: Path) -> None:
    out = md_exporter.render(ProjectPaths(project), pack="review", ai=False)
    history = out.split("## Model History", 1)[1].split("\n## ", 1)[0]
    assert "edge_" not in history and "node_" not in history
    assert "Workload → Burnout" in history


def test_client_pack_leads_with_the_answer_and_drops_the_change_log(project: Path) -> None:
    out = md_exporter.render(ProjectPaths(project), pack="client", ai=False)
    assert "## Model History" not in out
    headings = [line for line in out.splitlines() if line.startswith("## ")]
    assert headings.index("## Diagram") < headings.index("## Edges") < headings.index("## Evidence")
    # The audit pack keeps everything, change log included.
    assert "## Model History" in md_exporter.render(ProjectPaths(project), pack="audit", ai=False)


def test_reader_packs_open_the_interpretation_with_the_answer(project: Path) -> None:
    from latris.operations.interpret import save_interpretation
    from latris.schema.interpretation import InterpretationStore, InterpretSection

    store = InterpretationStore(
        sections=[
            InterpretSection(id=f"s{i}", section_type=t, model_type="cld", prose=f"Prose for {t}.")
            for i, t in enumerate(["structural_summary", "key_findings", "answer_to_question", "implications"])
        ]
    )
    save_interpretation(store, root=project)
    paths = ProjectPaths(project)
    client = md_exporter.render(paths, pack="client", ai=False)
    assert client.index("Prose for answer_to_question.") < client.index("Prose for structural_summary.")
    review = md_exporter.render(paths, pack="review", ai=False)
    assert review.index("Prose for structural_summary.") < review.index("Prose for answer_to_question.")


def test_reference_names_ending_in_an_initial_get_one_full_stop(project: Path) -> None:
    ref_ops.add_reference("mueller2020", "Retention", authors=["Mueller, Stephanie L."], year=2020, root=project)
    out = md_exporter.render(ProjectPaths(project), pack="client", ai=False)
    assert "Mueller, Stephanie L. (2020). *Retention*." in out
    assert "L.." not in out
    # Names with commas are separated by semicolons.
    assert "Smith, J; Lee, K" in out


def test_description_matching_the_reason_is_not_repeated(project: Path) -> None:
    from latris.operations.attributes import set_attribute

    edge = edge_ops.list_edges(root=project)[0]
    set_attribute(edge.id, "description", "More hours, more exhaustion.", root=project)
    out = md_exporter.render(ProjectPaths(project), pack="client", ai=False)
    assert out.count("More hours, more exhaustion.") == 1


def test_identical_audit_tags_are_stated_once(project: Path) -> None:
    edge = edge_ops.list_edges(root=project)[0]
    ref_ops.add_reference("lee2022", "Workload", year=2022, root=project)
    evidence_ops.add_evidence(edge.id, "polarity", "lee2022", root=project)
    out = md_exporter.render(ProjectPaths(project), pack="client", ai=False)
    evidence = out.split("## Evidence", 1)[1].split("\n## ", 1)[0]
    assert evidence.count("not yet checked against the source") == 1
    assert (
        "_Every citation below: attached by a person · from the source's title · "
        "not yet checked against the source._"
    ) in evidence
    assert "=" not in evidence


def test_diagram_colours_polarity_and_lists_loops(project: Path) -> None:
    edge_ops.add_edge("Burnout", "Workload", root=project)
    back = edge_ops.list_edges(root=project)[-1]
    view_attr_ops.set_view_attribute(back.id, "cld", "polarity", "-", root=project)
    out = md_exporter.render(ProjectPaths(project), pack="client", ai=False)
    assert "linkStyle 0 stroke:#2e8b57" in out and "linkStyle 1 stroke:#c0392b" in out
    assert "**B1** (balancing): Workload → Burnout → Workload" in out


def test_agent_written_prose_is_not_logged_as_generated(project: Path, monkeypatch) -> None:
    from latris.operations.interpret import save_interpretation
    from latris.repo import git
    from latris.schema.interpretation import InterpretationStore, InterpretSection

    save_interpretation(
        InterpretationStore(sections=[InterpretSection(id="s1", section_type="answer_to_question", model_type="cld")]),
        root=project,
    )
    monkeypatch.chdir(project)
    result = CliRunner().invoke(app, ["interpret", "set-prose", "answer_to_question", "Because.", "--by", "ai"])
    assert result.exit_code == 0, result.output
    subject = git.run_git(["log", "-1", "--format=%s"], cwd=project).stdout.strip()
    assert subject == "Write (AI agent) interpretation: answer_to_question"


def test_sources_against_a_link_show_both_sides(project: Path, monkeypatch) -> None:
    from latris.operations.interpret import coverage_ratio, extract_claims
    from latris.operations.project import update_selected_models

    update_selected_models(["cld"], root=project)
    edge = edge_ops.list_edges(root=project)[0]
    ref_ops.add_reference("tuohy2015", "Workload and retention revisited", authors=["Tuohy, R"], year=2015,
                          root=project)
    monkeypatch.chdir(project)
    result = CliRunner().invoke(app, ["evidence", "add", edge.id, "polarity", "tuohy2015", "--contradicts"])
    assert result.exit_code == 0, result.output

    out = md_exporter.render(ProjectPaths(project), pack="client", ai=False)
    contested = out.split("## Contested links", 1)[1].split("\n## ", 1)[0]
    assert "**Workload → Burnout**" in contested
    assert "For: Smith & Lee (2021)" in contested and "Against: Tuohy (2015)" in contested
    evidence = out.split("## Evidence", 1)[1].split("\n## ", 1)[0]
    assert "Workload → Burnout / **polarity** — **against**" in evidence
    # A source against doesn't bring the shared audit tags back onto every line.
    assert evidence.count("not yet checked against the source") == 1

    # Coverage counts sources for a claim only; the disagreement reaches the claims.
    assert coverage_ratio("cld", ProjectPaths(project))[:2] == (1, 1)
    open_qs = extract_claims("open_questions", "cld", root=project)
    assert any("Sources disagree — Workload → Burnout: 1 source for, 1 against (tuohy2015)" in c for c in open_qs)


def test_no_contested_section_without_disagreement(project: Path) -> None:
    out = md_exporter.render(ProjectPaths(project), pack="client", ai=False)
    assert "## Contested links" not in out


def test_tables_drop_columns_that_say_nothing(project: Path) -> None:
    out = md_exporter.render(ProjectPaths(project), pack="client", ai=False)
    edges = out.split("### Causal substrate", 1)[1].split("\n## ", 1)[0]
    # Every link is causal (the heading says so) and none has a description.
    assert "| From → To | Polarity | Why |" in edges
    assert "Kind" not in edges and "Description" not in edges


def test_last_updated_is_readable(project: Path) -> None:
    import re

    out = md_exporter.render(ProjectPaths(project), pack="client", ai=False)
    assert re.search(r"_Last updated \d{1,2} [A-Z][a-z]{2} \d{4}, \d{2}:\d{2} UTC_", out)


def test_client_pack_puts_the_diagram_right_after_the_answer(project: Path) -> None:
    from latris.operations import interpret as interpret_ops
    from latris.operations.project import update_selected_models

    update_selected_models(["cld"], root=project)
    edge_ops.add_edge("Burnout", "Workload", root=project)  # a loop, so the CLD can be interpreted
    store, _, _ = interpret_ops.initialise_sections(root=project)
    answer = next(s for s in store.sections if s.section_type == "answer_to_question")
    interpret_ops.update_prose(answer.id, "Volunteers leave because of workload.", root=project)
    out = md_exporter.render(ProjectPaths(project), pack="client", ai=False)
    answer = out.index("\n## Answer to Modelling Question")
    diagram = out.index("## Diagram")
    rest = out.index("## Interpretation")
    assert answer < diagram < rest
    assert "interpretation continues" not in out
    # Packs for the modelling team keep the interpretation in one piece.
    review = md_exporter.render(ProjectPaths(project), pack="review", ai=False)
    assert "\n## Answer to Modelling Question" not in review


def test_reader_packs_drop_claims_where_prose_says_it(project: Path) -> None:
    from latris.operations import interpret as interpret_ops
    from latris.operations.project import update_selected_models

    update_selected_models(["cld"], root=project)
    edge_ops.add_edge("Burnout", "Workload", root=project)
    store, _, _ = interpret_ops.initialise_sections(root=project)
    answer = next(s for s in store.sections if s.section_type == "answer_to_question")
    interpret_ops.refresh_all_claims(root=project)
    interpret_ops.update_prose(answer.id, "Volunteers leave because of workload.", root=project)
    client = md_exporter.render(ProjectPaths(project), pack="client", ai=False)
    answer_part = client.split("\n## Answer to Modelling Question", 1)[1].split("\n## ", 1)[0]
    assert "Claims (from analysis)" not in answer_part
    # Sections without prose still show their claims.
    assert "Claims (from analysis)" in client
    review = md_exporter.render(ProjectPaths(project), pack="review", ai=False)
    assert review.count("Claims (from analysis)") > client.count("Claims (from analysis)")


def test_report_links_to_the_model_as_it_is_now(project: Path) -> None:
    from latris.operations.share_link import decode_payload

    out = md_exporter.render(ProjectPaths(project), pack="client", ai=False, app_link=True)
    link = out.split("(https://app.latris.app/open#", 1)[1].split(")", 1)[0]
    assert [f.label for f in decode_payload(link).spec.factors] == ["Workload", "Burnout"]
    node_ops.add_node("Recognition", root=project)
    later = md_exporter.render(ProjectPaths(project), pack="client", ai=False, app_link=True)
    fresh = later.split("(https://app.latris.app/open#", 1)[1].split(")", 1)[0]
    assert "Recognition" in [f.label for f in decode_payload(fresh).spec.factors]
    # Off unless asked for (the hosted page mustn't link to itself).
    assert "open#" not in md_exporter.render(ProjectPaths(project), pack="client", ai=False)
