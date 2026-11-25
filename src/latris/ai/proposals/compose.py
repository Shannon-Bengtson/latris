"""Compose results: variables and claims extracted from evidence, and suggested variables and connections."""

from __future__ import annotations

from pydantic import Field

from latris.ai.proposals._shared import _Base
from latris.schema.substrate import EntityKind


class ExtractedVariable(_Base):
    """A single variable extracted from evidence."""

    label: str = Field(..., description="Concise variable/concept name.")
    kind: EntityKind = Field(
        "variable",
        description=(
            "Entity kind. Must be one of: concept, variable, event, actor, "
            "state, decision, hazard."
        ),
    )
    description: str = Field("", description="What this variable represents.")
    source_bibkeys: list[str] = Field(default_factory=list, description="References where found.")


class ExtractedVariablesResult(_Base):
    """ExtractVariablesFromEvidence output. Read-only — no apply()."""

    variables: list[ExtractedVariable] = Field(default_factory=list)


class ExtractedClaim(_Base):
    """A single causal claim extracted from evidence."""

    from_label: str = Field(..., description="Source entity label.")
    to_label: str = Field(..., description="Target entity label.")
    kind: str = Field("causal", description="Edge kind: causal, temporal, association.")
    description: str = Field(
        "",
        description="One sentence: the mechanism this edge represents.",
    )
    rationale: str = Field("", description="Brief explanation of the causal mechanism.")
    source_bibkeys: list[str] = Field(default_factory=list, description="References supporting this claim.")
    claim_text: str = Field("", description="Direct quote or paraphrase from the reference.")


class ExtractedClaimsResult(_Base):
    """ExtractCausalClaims output. Read-only — no apply()."""

    claims: list[ExtractedClaim] = Field(default_factory=list)


class SuggestedVariable(_Base):
    """A single AI-suggested variable."""

    label: str = Field(..., description="Concise variable/concept name.")
    kind: EntityKind = Field(
        "variable",
        description=(
            "Entity kind. Must be one of: concept, variable, event, actor, "
            "state, decision, hazard."
        ),
    )
    description: str = Field("", description="What this variable represents and why it matters.")
    rationale: str = Field("", description="Why this variable should be in the model.")


class SuggestedVariablesResult(_Base):
    """SuggestVariables output. Read-only — no apply()."""

    variables: list[SuggestedVariable] = Field(default_factory=list)


class SuggestedConnection(_Base):
    """A single AI-suggested connection."""

    from_label: str = Field(..., description="Source entity label.")
    to_label: str = Field(..., description="Target entity label.")
    kind: str = Field("causal", description="Edge kind.")
    description: str = Field(
        "",
        description="One sentence: what this connection means / the mechanism.",
    )
    rationale: str = Field("", description="Brief explanation of the mechanism.")
    confidence: str = Field("medium", description="low | medium | high")


class SuggestedConnectionsResult(_Base):
    """SuggestConnections output. Read-only — no apply()."""

    connections: list[SuggestedConnection] = Field(default_factory=list)
