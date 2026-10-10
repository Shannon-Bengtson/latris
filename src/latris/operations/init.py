"""Scaffold a new latris project.

Lays down the canonical directory structure, writes empty/stub files for every
YAML-backed log, drops ``.gitignore``/``.gitattributes`` templates, runs
``git init``, and creates the initial commit.
"""

from __future__ import annotations

from pathlib import Path

from latris.operations.commit import auto_commit
from latris.repo import git
from latris.repo.layout import ALL_DIRS_TO_CREATE, ProjectPaths
from latris.repo.yaml_io import dump_model
from latris.schema import (
    AssumptionLog,
    ChallengeLog,
    ConfidenceSet,
    DatasetLibrary,
    DatasetVersionLibrary,
    DecisionLog,
    DescriptionSet,
    ElicitationLog,
    EvidenceLinkSet,
    ExclusionLog,
    FloatSet,
    MappingRegistry,
    PolaritySet,
    PredictionLog,
    ProjectFoundation,
    QuestionLog,
    ReferenceLibrary,
    SessionLog,
    SignoffLog,
    Substrate,
    View,
)
from latris.schema.project import SCHEMA_VERSION
from latris.schema.roles import RoleSet

_GITIGNORE_TEMPLATE = """\
# latris: generated exports are regenerable output, not source.
reports/exports/

# latris: layout files (coordinates, colours) are excluded from
# semantic diffs. They can be committed if you want visual continuity
# across collaborators; delete the following two lines to do so.
layout/*.layout.yaml
"""

_GITATTRIBUTES_TEMPLATE = """\
* text=auto eol=lf

*.yaml   text eol=lf
*.yml    text eol=lf
*.md     text eol=lf
*.jsonl  text eol=lf
*.json   text eol=lf
*.bib    text eol=lf
*.csv    text eol=lf
*.tsv    text eol=lf
"""


class ProjectAlreadyExistsError(RuntimeError):
    pass


def init_project(
    root: Path,
    *,
    statement: str,
    name: str = "",
) -> ProjectPaths:
    """Create a new project at ``root``.

    Pre-conditions:
    - ``root`` does not exist, or exists and is empty.
    - git binary is available.
    - git identity is configured (globally, or via env vars).

    Post-conditions:
    - ``root`` contains the full canonical directory tree.
    - ``root`` is a git repository with one initial commit on ``main``.
    - All YAML log files are present (populated with their empty shape).
    """
    git.ensure_git_available()
    git.ensure_identity()  # global — no repo exists yet

    if root.exists():
        if any(root.iterdir()):
            raise ProjectAlreadyExistsError(f"{root} already exists and is not empty")
    else:
        root.mkdir(parents=True)

    paths = ProjectPaths(root)

    for attr in ALL_DIRS_TO_CREATE:
        getattr(paths, attr).mkdir(parents=True, exist_ok=True)

    paths.version_file.write_text(f"{SCHEMA_VERSION}\n", encoding="utf-8", newline="")

    dump_model(
        ProjectFoundation(name=name, statement=statement),
        paths.project_yaml,
    )

    dump_model(Substrate(), paths.conceptual_yaml)
    dump_model(MappingRegistry(), paths.mappings_yaml)
    dump_model(DescriptionSet(), paths.descriptions_yaml)
    dump_model(ConfidenceSet(), paths.confidence_yaml)
    dump_model(EvidenceLinkSet(), paths.evidence_links_yaml)
    dump_model(PolaritySet(), paths.view_attribute_path("cld", "polarity"))
    dump_model(RoleSet(), paths.role_path("cld"))
    dump_model(RoleSet(), paths.role_path("dag"))
    dump_model(RoleSet(), paths.role_path("fcm"))
    dump_model(FloatSet(), paths.view_attribute_path("fcm", "weight"))
    dump_model(View(kind="cld"), paths.view_yaml("cld"))
    dump_model(View(kind="dag"), paths.view_yaml("dag"))
    dump_model(View(kind="fcm"), paths.view_yaml("fcm"))
    dump_model(AssumptionLog(), paths.assumptions_yaml)
    dump_model(DecisionLog(), paths.decisions_yaml)
    dump_model(SignoffLog(), paths.signoffs_yaml)
    dump_model(SessionLog(), paths.sessions_yaml)
    dump_model(QuestionLog(), paths.questions_yaml)
    dump_model(ExclusionLog(), paths.exclusions_yaml)
    dump_model(PredictionLog(), paths.predictions_yaml)
    dump_model(ChallengeLog(), paths.challenges_yaml)

    paths.research_notes_md.write_text("# Research notes\n", encoding="utf-8", newline="")
    paths.references_bib.write_text("", encoding="utf-8", newline="")
    dump_model(ReferenceLibrary(), paths.references_yaml)
    paths.ai_project_context_md.write_text("# AI project context\n", encoding="utf-8", newline="")
    paths.reports_draft_md.write_text("# Draft report\n", encoding="utf-8", newline="")
    paths.interactions_jsonl.write_text("", encoding="utf-8", newline="")

    # M11: elicitation, data, analysis stubs
    dump_model(ElicitationLog(), paths.elicitations_yaml)
    dump_model(DatasetLibrary(), paths.data_datasets_yaml)
    dump_model(DatasetVersionLibrary(), paths.data_versions_yaml)
    paths.analysis_runs_jsonl.write_text("", encoding="utf-8", newline="")

    (root / ".gitignore").write_text(_GITIGNORE_TEMPLATE, encoding="utf-8", newline="")
    (root / ".gitattributes").write_text(_GITATTRIBUTES_TEMPLATE, encoding="utf-8", newline="")

    git.init(root)
    auto_commit(
        root,
        subject="Initialise latris project",
        body=f"Modelling question: {statement}",
        provenance="human-authored",
    )
    return paths
