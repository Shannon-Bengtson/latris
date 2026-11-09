"""The methods-and-foundations registry — one source of truth for what Latris implements.

Every entry names an established method Latris actually implements, the
literature it stands on, what it is used for, and its stated limits. Three
surfaces read this one registry so they cannot drift apart:

- the report's **Methods and foundations** section (:func:`render_methods_section`),
- the capability manifest's ``foundations`` block (``latris capabilities --json``),
- ``latris foundations`` (``latris foundations --json`` for the raw list).

``docs/FOUNDATIONS.md`` is the prose companion; the registry and the code it
describes win where the two disagree.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field

from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import load_model
from latris.schema import EvidenceLinkSet, ProjectFoundation, ReferenceLibrary


@dataclass(frozen=True)
class Foundation:
    """One implemented method, its citation, and its stated limits.

    ``applies_to`` holds model-type ids from ``schema/model_types.py`` — or
    ``("*",)`` for the evidence discipline, which spans every model type.
    """

    id: str
    applies_to: tuple[str, ...]
    method: str
    citation: str
    used_for: str
    limits: str | None


FOUNDATIONS: tuple[Foundation, ...] = (
    Foundation(
        id="cld-loop-analysis",
        applies_to=("cld",),
        method="Qualitative loop analysis (causal loop diagrams)",
        citation="Sterman (2000), *Business Dynamics*, ch. 4; Meadows (2008), *Thinking in Systems*",
        used_for=(
            "detecting feedback loops, classifying them balancing or reinforcing by polarity, "
            "and propagating qualitative effects along paths"
        ),
        limits=(
            "Ambiguous polarity (~) is reported as unknown, not guessed; loop enumeration "
            "is capped and raises beyond it."
        ),
    ),
    Foundation(
        id="dag-identification",
        applies_to=("dag",),
        method="Causal identification on a DAG",
        citation=(
            "Pearl (2009), *Causality*; Hernán & Robins (2020), "
            "*Causal Inference: What If*; d-separation after Shachter (1998)"
        ),
        used_for=(
            "d-separation queries, Markov blankets, path enumeration, and backdoor "
            "adjustment sets by graph surgery"
        ),
        limits=(
            "Identification only — no do-operator estimation and no counterfactuals; "
            "adjustment sets are enumerated only up to size 3."
        ),
    ),
    Foundation(
        id="bn-exact-inference",
        applies_to=("bn",),
        method="Exact inference in discrete Bayesian networks",
        citation=(
            "Pearl (1988), *Probabilistic Reasoning in Intelligent Systems*; "
            "Fenton & Neil (2018), *Risk Assessment and Decision Analysis with "
            "Bayesian Networks* (2nd ed.)"
        ),
        used_for="per-node posterior marginals by variable elimination",
        limits="Variable elimination only — no junction tree or belief propagation; marginals, not joints.",
    ),
    Foundation(
        id="bn-parameter-learning",
        applies_to=("bn",),
        method="CPT parameter learning from data",
        citation=(
            "Fenton & Neil (2018), *Risk Assessment and Decision Analysis with "
            "Bayesian Networks* (2nd ed.)"
        ),
        used_for="MLE and Bayesian-Dirichlet estimators with human-elicited CPT rows protected from overwrite",
        limits="CPT parameters only — structure learning is excluded by design.",
    ),
    Foundation(
        id="fcm-steady-state",
        applies_to=("fcm",),
        method="Fuzzy cognitive map inference",
        citation='Kosko (1986), "Fuzzy Cognitive Maps", *Int. J. Man-Machine Studies* 24(1)',
        used_for=(
            "weighted matrix iteration to a steady state with sigmoid, tanh, or step "
            "transfer functions and clamped scenario nodes"
        ),
        limits="Fixed-point only — non-convergence is flagged; limit cycles are not analysed.",
    ),
    Foundation(
        id="sd-simulation",
        applies_to=("sd",),
        method="Stock-and-flow simulation with dimensional analysis",
        citation="Forrester (1961), *Industrial Dynamics*; Sterman (2000), *Business Dynamics*",
        used_for=(
            "unit-checked stock-flow integration (fixed-step Euler or adaptive RK23/RK45) "
            "with STEP, RAMP, PULSE and TABLE functions and provenance-carrying scenarios"
        ),
        limits=(
            "The adaptive RK option is RK45 under a step cap, not the classical "
            "fixed-step RK4 of Vensim/Stella."
        ),
    ),
    Foundation(
        id="sd-uncertainty",
        applies_to=("sd",),
        method="Uncertainty by Latin-hypercube sampling",
        citation="McKay, Beckman & Conover (1979), *Technometrics* 21(2)",
        used_for="seeded sampling of uncertain constants with percentile bands and Spearman rank correlations",
        limits="Capped at 1000 runs; rank correlations only, no variance decomposition.",
    ),
    Foundation(
        id="sd-sensitivity",
        applies_to=("sd",),
        method="One-at-a-time sensitivity",
        citation="Sterman (2000), *Business Dynamics*",
        used_for="tornado-style swings of each parameter's effect on a chosen metric, with a provenance overlay",
        limits="One-at-a-time only — no multi-way or derivative-based analysis.",
    ),
    Foundation(
        id="sd-loop-dominance",
        applies_to=("sd",),
        method="Loop dominance over a run (Loops That Matter)",
        citation=(
            "Schoenberg, Davidsen & Eberlein (2020), *System Dynamics Review*; "
            "revised score Schoenberg, Hayward & Eberlein (2023)"
        ),
        used_for=(
            "scoring every feedback loop at each step and flagging the loop (or fewest "
            "loops) holding half the score"
        ),
        limits=(
            "Enumerated exhaustively up to 500 loops — no strongest-path fallback; "
            "scores are zero whenever stocks stop changing, so the method explains "
            "change, not equilibrium."
        ),
    ),
    Foundation(
        id="evidence-source-check",
        applies_to=("*",),
        method="Source-vs-claim checking with a verification audit trail",
        citation=(
            "practice after Bradford Hill (1965) and GRADE (Guyatt et al. 2008); "
            "argumentation vocabulary from Toulmin (1958) — inspiration, not implemented criteria"
        ),
        used_for=(
            "recording whether a cited source supports the claim, who checked, which part "
            "of the source was read, and keeping sources for and against together on "
            "contested links"
        ),
        limits=(
            "Does not score claims against the Bradford Hill criteria and does not assign "
            "GRADE ratings; a check is only as good as the stored source text."
        ),
    ),
)

# Analysis result kinds (latris.operations.analysis_results.KIND_ORDER) mapped to
# the foundation entry they pull in. ``sd-simulation`` is a core entry: any
# genuine use of the SD formalism includes it, so it is deliberately absent here.
_ANALYSIS_KIND_TO_ID = {
    "sd-monte-carlo": "sd-uncertainty",
    "sd-sensitivity": "sd-sensitivity",
    "sd-loops": "sd-loop-dominance",
}


class _EntriesFile(BaseModel):
    """The shape shared by every view attribute / role YAML file: ``entries:``."""

    entries: list = Field(default_factory=list)


def _has_view_attribute_content(paths: ProjectPaths, model_type: str) -> bool:
    """True if any view-attribute or role file for ``model_type`` holds entries.

    ``latris view set cld <edge> polarity +`` and ``latris sd set-role ...``
    are documented ways a project gains formalism content without ever
    touching the mapping registry, so they count as genuine use.
    """
    candidates = [
        *paths.parameters_dir.glob(f"{model_type}-*.yaml"),
        paths.roles_dir / f"{model_type}-roles.yaml",
    ]
    return any(f.is_file() and load_model(_EntriesFile, f).entries for f in candidates)


def _uses_formalism(paths: ProjectPaths, model_type: str) -> bool:
    """True if the project genuinely uses this formalism: any of

    - the type is selected in project.yaml (``latris project select-models``),
    - the mapping registry has members for it, or
    - it has stored view-attribute content (polarity, weights, roles, ...).
    """
    from latris.exporters._scope import view_member_ids

    foundation = load_model(ProjectFoundation, paths.project_yaml)
    if model_type in (foundation.selected_model_types or ()):
        return True
    if view_member_ids(paths, model_type) is not None:
        return True
    return _has_view_attribute_content(paths, model_type)


def _has_evidence_or_references(paths: ProjectPaths) -> bool:
    references = load_model(ReferenceLibrary, paths.references_yaml).entries
    evidence = load_model(EvidenceLinkSet, paths.evidence_links_yaml)
    return bool(references) or bool(evidence.entries)


def foundations_for_report(paths: ProjectPaths, *, model_type: str | None = None) -> list[Foundation]:
    """The entries relevant to one rendered report, in ``FOUNDATIONS`` order.

    Core model-type entries: when ``model_type`` is given (a scoped export),
    that type is included outright — the scoped export is itself the request
    for that formalism's report. In the aggregate report (``model_type=None``)
    a core entry is included when the project genuinely uses that formalism:
    it is selected in project.yaml, present in the mapping registry, or holds
    stored view-attribute content. Analysis entries are included only when
    the corresponding result kind is actually shown in the report's Results
    section: the same
    :func:`latris.operations.analysis_results.report_results` selection the
    exporter uses (latest run of each analysis, minus hidden ones, same
    ``model_types`` filter). The evidence entry is included when the project
    holds any references or evidence links.
    """
    from latris.operations.analysis_results import report_results

    results = report_results(model_types=[model_type] if model_type else None, root=paths.root)
    present_kinds = {res.run.result_kind for res in results}

    out: list[Foundation] = []
    seen: set[str] = set()
    for f in FOUNDATIONS:
        if f.applies_to == ("*",):
            include = _has_evidence_or_references(paths)
        elif f.id in _ANALYSIS_KIND_TO_ID.values():
            include = any(
                kind in present_kinds for kind, fid in _ANALYSIS_KIND_TO_ID.items() if fid == f.id
            )
        elif model_type is not None:
            include = f.applies_to == (model_type,)
        else:
            include = any(_uses_formalism(paths, mt) for mt in f.applies_to)
        if include and f.id not in seen:
            seen.add(f.id)
            out.append(f)
    return out


def render_methods_section(paths: ProjectPaths, *, model_type: str | None = None) -> list[str]:
    """Markdown lines for the report's Methods and foundations section.

    Empty list when nothing applies, so an early-stage project renders no
    section at all. No internal IDs — reader packs show this section.
    """
    entries = foundations_for_report(paths, model_type=model_type)
    if not entries:
        return []
    out = ["## Methods and foundations", ""]
    out.append(
        "_Established methods this model relies on, with their sources and stated limits. "
        "Latris cites a method only where it implements it — see the foundations reference "
        "for the full account._"
    )
    out.append("")
    for f in entries:
        limits = f" Limit: {f.limits}" if f.limits else ""
        out.append(f"- **{f.method}** — {f.used_for} ({f.citation}).{limits}")
    out.append("")
    return out
