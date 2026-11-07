"""A link that carries the model: ``latris link``.

Agents in sandboxes often can't reach any server but a package index, yet
they can always write a link into the conversation. ``make_link`` turns the
project into a build spec (the ``latris build --spec`` format), compresses
it, and puts it in the fragment of an app.latris.app URL. Opening the link
loads the model into the Latris app as a hosted report the person can share
and save. Nothing is sent anywhere by this command; the fragment (after
``#``) also isn't sent to a server when the link is merely shared.

The copy carries the model, its evidence, findings (as proposed), open
challenges and interpretation prose — not the git history.

Payload: JSON ``{"v": 1, "name", "question", "model_type", "spec"}``,
raw-DEFLATE compressed, base64url without padding.
"""

from __future__ import annotations

import base64
import json
import os
import zlib
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from latris.repo.project import require_project
from latris.repo.yaml_io import load_model
from latris.schema import (
    AssumptionLog,
    ChallengeLog,
    ConfidenceSet,
    DecisionLog,
    DescriptionSet,
    EvidenceLinkSet,
    PolaritySet,
    ProjectFoundation,
    QuestionLog,
    ReferenceLibrary,
    Substrate,
)
from latris.schema.build_spec import (
    BuildSpec,
    SpecAssumption,
    SpecChallenge,
    SpecDecision,
    SpecFactor,
    SpecFinding,
    SpecInterpretation,
    SpecLink,
    SpecSource,
)

APP_URL_ENV = "LATRIS_APP_URL"
DEFAULT_APP_URL = "https://app.latris.app"
PAYLOAD_VERSION = 1
# Links longer than this get unwieldy in chat; past it, suggest `latris sync share`.
COMFORTABLE_LINK_CHARS = 30_000
MAX_PAYLOAD_BYTES = 400_000  # decompressed; the server refuses more


class LinkPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    v: int = PAYLOAD_VERSION
    name: str
    question: str
    model_type: str = "cld"
    spec: BuildSpec


@dataclass(frozen=True)
class ShareLink:
    url: str
    chars: int
    factors: int
    links: int
    long: bool  # past COMFORTABLE_LINK_CHARS


def export_spec(*, model_type: str | None = None, root: Path | None = None) -> tuple[ProjectFoundation, BuildSpec]:
    """The project as a build spec — the inverse of ``latris build``."""
    from latris.operations.findings import list_findings
    from latris.operations.interpret import load_interpretation
    from latris.schema.attributes import FloatSet
    from latris.schema.roles import RoleSet

    paths = require_project(root)
    foundation = load_model(ProjectFoundation, paths.project_yaml)
    model_type = model_type or next(iter(foundation.selected_model_types), "cld")
    substrate = load_model(Substrate, paths.conceptual_yaml)

    labels = {e.id: e.label for e in substrate.entities}
    # The spec names factors by label, so labels must be unique.
    seen: set[str] = set()
    for e in substrate.entities:
        if e.label.casefold() in seen:
            raise ValueError(f"two factors are both called {e.label!r}; rename one before making a link")
        seen.add(e.label.casefold())

    def name(target_id: str | None) -> str | None:
        if target_id is None:
            return None
        if target_id in labels:
            return labels[target_id]
        edge = next((e for e in substrate.edges if e.id == target_id), None)
        return f"{labels[edge.from_id]} -> {labels[edge.to_id]}" if edge else None

    def _load(cls, path):  # noqa: ANN001, ANN202
        return load_model(cls, path) if path.exists() else cls()

    descriptions = {e.target_id: e.value for e in _load(DescriptionSet, paths.descriptions_yaml).entries}
    confidence = {e.target_id: e.value for e in _load(ConfidenceSet, paths.confidence_yaml).entries}
    polarity = {
        e.target_id: e for e in _load(PolaritySet, paths.view_attribute_path("cld", "polarity")).entries
        if e.attribute == "polarity"
    }
    weights = {e.target_id: e.value for e in _load(FloatSet, paths.view_attribute_path("fcm", "weight")).entries}
    evidence = _load(EvidenceLinkSet, paths.evidence_links_yaml).entries

    def cites(target_id: str, *, against: bool) -> list[str]:
        keys = [
            e.bibkey for e in evidence
            if e.target_id == target_id and (e.support_verdict == "contradicts") == against
        ]
        return list(dict.fromkeys(keys))

    factors = [
        SpecFactor(
            label=e.label, kind=e.kind, description=descriptions.get(e.id),
            sources=cites(e.id, against=False), contradicts=cites(e.id, against=True),
        )
        for e in substrate.entities
    ]
    links = []
    for e in substrate.edges:
        pol = polarity.get(e.id)
        links.append(SpecLink.model_validate({
            "from": labels[e.from_id], "to": labels[e.to_id], "kind": e.kind,
            "polarity": pol.value if pol and pol.value in ("+", "-") else None,
            "reason": pol.rationale if pol else None,
            "weight": weights.get(e.id), "description": descriptions.get(e.id),
            "confidence": confidence.get(e.id),
            "sources": cites(e.id, against=False), "contradicts": cites(e.id, against=True),
        }))
    sources = [
        SpecSource(
            key=r.bibkey, title=r.title, authors=list(r.authors), year=r.year, container=r.container,
            doi=r.doi, url=r.url, notes=r.notes,
        )
        for r in _load(ReferenceLibrary, paths.references_yaml).entries
    ]
    assumptions = [
        SpecAssumption(text=a.statement, target=name(a.target_id), rationale=a.rationale)
        for a in _load(AssumptionLog, paths.assumptions_yaml).entries
    ]
    questions = [q.question for q in _load(QuestionLog, paths.questions_yaml).entries if q.disposition == "open"]
    findings = [
        SpecFinding(
            statement=f.statement, category=f.category, detail=f.detail,
            targets=[n for n in (name(t) for t in f.target_ids) if n],
        )
        for f in list_findings(model_type=model_type, root=paths.root)
        if f.maturity in ("proposed", "reviewed", "approved")
    ]
    challenges = [
        SpecChallenge(argument=c.argument, target=name(c.target_id))
        for c in _load(ChallengeLog, paths.challenges_yaml).entries if c.state == "open"
    ]
    decisions = [
        SpecDecision(statement=d.statement, rationale=d.rationale, target=name(d.target_id))
        for d in _load(DecisionLog, paths.decisions_yaml).entries
    ]
    interpretation = [
        SpecInterpretation(
            section=s.section_type, prose=s.prose, by="human" if s.generation_state == "edited" else "ai",
        )
        for s in load_interpretation(root=paths.root).sections
        if s.model_type == model_type and s.prose.strip()
    ]
    role_path = paths.role_path(model_type)
    outcome = next(
        (labels[r.target_id] for r in _load(RoleSet, role_path).entries
         if r.value == "outcome" and r.target_id in labels),
        None,
    ) if role_path.exists() else None

    spec = BuildSpec(
        model_type=model_type, outcome=outcome, factors=factors, links=links, sources=sources,
        assumptions=assumptions, questions=questions, findings=findings, challenges=challenges,
        decisions=decisions, interpretation=interpretation,
    )
    return foundation, spec


def encode_payload(payload: LinkPayload) -> str:
    raw = payload.model_dump_json(exclude_none=True, exclude_defaults=True, by_alias=True).encode("utf-8")
    comp = zlib.compressobj(level=9, wbits=-15)
    packed = comp.compress(raw) + comp.flush()
    return base64.urlsafe_b64encode(packed).rstrip(b"=").decode("ascii")


def decode_payload(text: str, *, max_bytes: int = MAX_PAYLOAD_BYTES) -> LinkPayload:
    """Unpack a link fragment; ValueError on anything malformed or oversized."""
    text = text.strip().lstrip("#")
    try:
        packed = base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
        dec = zlib.decompressobj(wbits=-15)
        raw = dec.decompress(packed, max_bytes + 1)
    except (ValueError, zlib.error) as exc:
        raise ValueError("this isn't a Latris model link") from exc
    if len(raw) > max_bytes or dec.unconsumed_tail:
        raise ValueError("the model in this link is too large")
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise ValueError("this isn't a Latris model link") from exc
    if not isinstance(data, dict) or data.get("v") not in (None, PAYLOAD_VERSION):
        raise ValueError("this link was made by a newer Latris; update the app")
    return LinkPayload.model_validate(data)


def make_link(
    *, model_type: str | None = None, app_url: str | None = None, root: Path | None = None
) -> ShareLink:
    foundation, spec = export_spec(model_type=model_type, root=root)
    paths = require_project(root)
    payload = LinkPayload(
        name=foundation.name or paths.root.name, question=foundation.statement,
        model_type=spec.model_type or "cld", spec=spec,
    )
    base = (app_url or os.environ.get(APP_URL_ENV) or DEFAULT_APP_URL).rstrip("/")
    url = f"{base}/open#{encode_payload(payload)}"
    return ShareLink(
        url=url, chars=len(url), factors=len(spec.factors), links=len(spec.links),
        long=len(url) > COMFORTABLE_LINK_CHARS,
    )
