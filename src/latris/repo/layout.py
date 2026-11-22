"""Canonical on-disk layout for a latris project.

Single source of truth for every known path inside a project. Every other
module imports paths from here — never hardcodes directory names.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

# A filename component that is safe on every platform and cannot escape
# its directory. Anything else is stored under a hashed name instead.
_SAFE_FILENAME_STEM = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._+-]{0,150}$")


def safe_filename_stem(name: str) -> str:
    """Return *name* if it is a safe filename stem, else a stable hashed stand-in."""
    if _SAFE_FILENAME_STEM.match(name) and ".." not in name:
        return name
    return "_key-" + hashlib.sha256(name.encode("utf-8")).hexdigest()[:24]


def contained_path(base: Path, candidate: Path) -> Path:
    """Return *candidate* if it resolves inside *base*, else raise ``ValueError``."""
    resolved_base = base.resolve()
    resolved = candidate.resolve()
    if resolved != resolved_base and resolved_base not in resolved.parents:
        raise ValueError(f"path {candidate} escapes {base}")
    return candidate

STATE_DIR_NAME = ".graph-tooling"
VERSION_FILE_NAME = "version"


@dataclass(frozen=True)
class ProjectPaths:
    """All paths inside an initialised project, rooted at ``root``."""

    root: Path

    # Top-level
    @property
    def project_yaml(self) -> Path:
        return self.root / "project.yaml"

    @property
    def state_dir(self) -> Path:
        return self.root / STATE_DIR_NAME

    @property
    def version_file(self) -> Path:
        return self.state_dir / VERSION_FILE_NAME

    @property
    def lineage_node_yaml(self) -> Path:
        return self.state_dir / "lineage-node.yaml"

    @property
    def milestones_yaml(self) -> Path:
        return self.state_dir / "milestones.yaml"

    @property
    def preferred_version_file(self) -> Path:
        return self.state_dir / "preferred-version"

    @property
    def cpts_dir(self) -> Path:
        return self.state_dir / "cpts"  # v2+, CSV quantitative data

    # Research base
    @property
    def research_base_dir(self) -> Path:
        return self.root / "research-base"

    @property
    def references_bib(self) -> Path:
        return self.research_base_dir / "references.bib"

    @property
    def references_yaml(self) -> Path:
        """Structured sidecar to references.bib — used until BibTeX I/O lands."""
        return self.research_base_dir / "references.yaml"

    @property
    def research_notes_md(self) -> Path:
        return self.research_base_dir / "notes.md"

    # Substrate (Layer 2)
    @property
    def substrate_dir(self) -> Path:
        return self.root / "substrate"

    @property
    def conceptual_yaml(self) -> Path:
        return self.substrate_dir / "conceptual.yaml"

    @property
    def mappings_yaml(self) -> Path:
        return self.substrate_dir / "mappings.yaml"

    @property
    def attributes_dir(self) -> Path:
        return self.substrate_dir / "attributes"

    @property
    def descriptions_yaml(self) -> Path:
        return self.attributes_dir / "descriptions.yaml"

    @property
    def confidence_yaml(self) -> Path:
        return self.attributes_dir / "confidence.yaml"

    @property
    def polarity_yaml(self) -> Path:
        return self.attributes_dir / "polarity.yaml"

    @property
    def evidence_links_yaml(self) -> Path:
        return self.attributes_dir / "evidence-links.yaml"

    @property
    def data_links_yaml(self) -> Path:
        return self.attributes_dir / "data-links.yaml"

    @property
    def parameter_uncertainty_yaml(self) -> Path:
        """Uncertainty distributions on quantitative parameters (any model type)."""
        return self.attributes_dir / "parameter-uncertainty.yaml"

    # Views (Layer 3)
    @property
    def views_dir(self) -> Path:
        return self.root / "views"

    def view_yaml(self, kind: str) -> Path:
        """Return path for a view's YAML file: ``views/{kind}.yaml``.

        The single source of truth for view file paths. Adding a new
        model type does not require touching this class.
        """
        return self.views_dir / f"{kind}.yaml"

    # View roles (formalism-specific entity classifications)
    @property
    def roles_dir(self) -> Path:
        return self.views_dir / "roles"

    def role_path(self, model_type: str) -> Path:
        """Return path for a model-type role file."""
        return self.roles_dir / f"{model_type}-roles.yaml"

    # View parameters (model-specific attributes)
    @property
    def parameters_dir(self) -> Path:
        return self.views_dir / "parameters"

    def view_attribute_path(self, model_type: str, attribute: str) -> Path:
        """Return path for a model-specific attribute file."""
        return self.parameters_dir / f"{model_type}-{attribute}.yaml"

    # Layout (coordinates, colours — git-ignored by default)
    @property
    def layout_dir(self) -> Path:
        return self.root / "layout"

    @property
    def canvas_layout_yaml(self) -> Path:
        return self.layout_dir / "canvas.layout.yaml"

    # Provenance
    @property
    def provenance_dir(self) -> Path:
        return self.root / "provenance"

    @property
    def assumptions_yaml(self) -> Path:
        return self.provenance_dir / "assumptions.yaml"

    @property
    def decisions_yaml(self) -> Path:
        return self.provenance_dir / "decisions.yaml"

    @property
    def model_choices_yaml(self) -> Path:
        return self.provenance_dir / "model-choices.yaml"

    @property
    def signoffs_yaml(self) -> Path:
        return self.provenance_dir / "signoffs.yaml"

    @property
    def sessions_yaml(self) -> Path:
        return self.provenance_dir / "sessions.yaml"

    @property
    def questions_yaml(self) -> Path:
        return self.provenance_dir / "questions.yaml"

    @property
    def person_input_yaml(self) -> Path:
        """What the person said at each checkpoint (schema/person_input.py)."""
        return self.provenance_dir / "person-input.yaml"

    @property
    def exclusions_yaml(self) -> Path:
        return self.provenance_dir / "exclusions.yaml"

    @property
    def predictions_yaml(self) -> Path:
        return self.provenance_dir / "predictions.yaml"

    @property
    def review_sessions_yaml(self) -> Path:
        return self.provenance_dir / "review-sessions.yaml"

    @property
    def members_yaml(self) -> Path:
        """Advisory governance mirror of project membership (sync feature)."""
        return self.provenance_dir / "members.yaml"

    # AI
    @property
    def ai_dir(self) -> Path:
        return self.root / "ai"

    @property
    def interactions_jsonl(self) -> Path:
        return self.ai_dir / "interactions.jsonl"

    @property
    def challenges_yaml(self) -> Path:
        return self.ai_dir / "challenges.yaml"

    @property
    def ai_project_context_md(self) -> Path:
        return self.ai_dir / "project-context.md"

    @property
    def references_extracts_dir(self) -> Path:
        """Directory for per-bibkey full-text artefacts (Phase 4b).

        Gitignored: extracts are derived (fetched) content, not authored.
        Each Reference's full text lives at
        ``references_extracts_dir / f"{bibkey}.txt"`` and is loaded on
        demand by the verification context builder.
        """
        return self.ai_dir / "reference-extracts"

    def references_extract_path(self, bibkey: str) -> Path:
        """Path to the per-bibkey extract artefact (Phase 4b).

        Bibkeys are user data: an unsafe one (path separators, ``..``,
        characters some filesystems reject) maps to a hashed filename, so
        the artefact can never land outside ``references_extracts_dir``.
        """
        return self.references_extracts_dir / f"{safe_filename_stem(bibkey)}.txt"

    # Elicitations (under provenance)
    @property
    def elicitations_dir(self) -> Path:
        return self.provenance_dir / "elicitations"

    @property
    def elicitations_yaml(self) -> Path:
        return self.provenance_dir / "elicitations.yaml"

    # Data
    @property
    def data_dir(self) -> Path:
        return self.root / "data"

    @property
    def data_datasets_yaml(self) -> Path:
        return self.data_dir / "datasets.yaml"

    @property
    def data_files_dir(self) -> Path:
        return self.data_dir / "files"

    @property
    def data_versions_yaml(self) -> Path:
        return self.data_dir / "versions.yaml"

    @property
    def data_actions_dir(self) -> Path:
        return self.data_dir / "actions"

    def data_action_log(self, dataset_id: str) -> Path:
        """Per-dataset action log file."""
        return self.data_actions_dir / f"{dataset_id}.yaml"

    # Analysis
    @property
    def analysis_dir(self) -> Path:
        return self.root / "analysis"

    @property
    def analysis_runs_jsonl(self) -> Path:
        return self.analysis_dir / "runs.jsonl"

    @property
    def findings_jsonl(self) -> Path:
        return self.analysis_dir / "findings.jsonl"

    @property
    def interpretation_yaml(self) -> Path:
        return self.analysis_dir / "interpretation.yaml"

    def completeness_report_yaml(self, model_type: str) -> Path:
        """Per-model-type CompletenessGate report (AI interrogation Phase 2c)."""
        return self.views_dir / model_type / "completeness-report.yaml"

    @property
    def analysis_outputs_dir(self) -> Path:
        return self.analysis_dir / "outputs"

    @property
    def analysis_report_yaml(self) -> Path:
        """Which recorded results the reports hide."""
        return self.analysis_dir / "report.yaml"

    # Reports
    @property
    def reports_dir(self) -> Path:
        return self.root / "reports"

    @property
    def reports_draft_md(self) -> Path:
        return self.reports_dir / "draft.md"

    @property
    def reports_exports_dir(self) -> Path:
        return self.reports_dir / "exports"

    # Communicate (report config + story artifacts)
    @property
    def communicate_dir(self) -> Path:
        return self.root / "communicate"

    @property
    def report_config_yaml(self) -> Path:
        return self.communicate_dir / "report_config.yaml"

    @property
    def story_yaml(self) -> Path:
        return self.communicate_dir / "story.yaml"

    @property
    def story_assets_dir(self) -> Path:
        return self.communicate_dir / "assets"


ALL_DIRS_TO_CREATE = (
    "state_dir",
    "research_base_dir",
    "substrate_dir",
    "attributes_dir",
    "views_dir",
    "roles_dir",
    "parameters_dir",
    "layout_dir",
    "provenance_dir",
    "elicitations_dir",
    "ai_dir",
    "reports_dir",
    "reports_exports_dir",
    "communicate_dir",
    "data_dir",
    "data_files_dir",
    "data_actions_dir",
    "analysis_dir",
    "analysis_outputs_dir",
)
"""Directories created during `latris init` (M2)."""
