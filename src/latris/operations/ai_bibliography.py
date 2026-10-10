"""Bibliography search + URL validation for the AI reference prompts.

The reference-suggestion prompts (ExpandBibliography, FindFoundationalReferences,
SuggestCitations) need real bibliographic data, not just LLM text. This module
turns an LLM ``BibliographySearchPlan`` into real OpenAlex references, scores
them for relevance against the project's model concepts, and validates proposed
URLs. Kept out of the route layer so the server stays parse → call → return.
"""

from __future__ import annotations

import logging
import re
import time
from contextlib import suppress
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_STOPWORDS = frozenset(
    ["the", "a", "an", "is", "are", "of", "in", "to", "and", "for", "that", "this", "with", "from", "on", "at", "by", "or", "not", "be", "as", "it", "was", "which", "but", "have", "has", "had", "can", "will", "do", "does", "did", "their", "its", "no", "if", "each", "about", "than", "into", "other", "some", "these", "those", "such", "only", "very", "also", "been", "were", "being", "would", "could", "should", "may", "might"]  # noqa: E501
)


def _tokenize(text: str) -> list[str]:
    """Lowercase, split on non-alpha, drop stopwords and short words."""
    words = re.findall(r"[a-z]{3,}", text.lower())
    return [w for w in words if w not in _STOPWORDS]


def extract_scoring_terms(root: Path) -> set[str]:
    """Build a set of model-concept terms for relevance scoring.

    Extracts words from entity labels and the modelling question/boundary.
    """
    from latris.repo.layout import ProjectPaths
    from latris.repo.yaml_io import load_model
    from latris.schema import Substrate
    from latris.schema.project import ProjectFoundation

    paths = ProjectPaths(root)
    terms: set[str] = set()

    with suppress(Exception):
        foundation = load_model(ProjectFoundation, paths.project_yaml)
        if foundation.statement:
            terms.update(_tokenize(foundation.statement))
        if foundation.boundary:
            terms.update(_tokenize(foundation.boundary))

    with suppress(Exception):
        substrate = load_model(Substrate, paths.conceptual_yaml)
        for entity in substrate.entities:
            terms.update(_tokenize(entity.label))

    return terms


def _score_reference(ref: Any, scoring_terms: set[str]) -> int:
    """Score a reference by keyword overlap with model concepts."""
    text = (ref.title or "") + " " + (ref.abstract or "")
    words = _tokenize(text)
    return sum(1 for w in words if w in scoring_terms)


def search_bibliography(
    proposal_json: dict[str, Any], scoring_terms: set[str] | None = None
) -> dict[str, Any]:
    """Take LLM search queries, search OpenAlex, return real references.

    Transforms a BibliographySearchPlan (queries) into an
    ExpandBibliographyProposal (real references from OpenAlex API).
    When scoring_terms is provided, fetches extra results per query and
    keeps the top 3 by keyword-overlap relevance.
    """
    from latris.operations.references import search_references

    queries = proposal_json.get("queries", [])
    if not queries:
        return {"new_references": []}

    seen_titles: set[str] = set()
    all_refs: list[dict[str, Any]] = []

    fetch_limit = 8 if scoring_terms else 3

    for i, q in enumerate(queries[:6]):  # Cap at 6 queries
        query_str = q.get("query", "")
        if not query_str:
            continue
        # Rate limit: OpenAlex polite pool allows ~10 req/sec
        if i > 0:
            time.sleep(0.2)
        try:
            results = search_references(query_str, limit=fetch_limit)

            # Score and keep top 3 if we have scoring terms
            if scoring_terms:
                scored = sorted(
                    results, key=lambda r: _score_reference(r, scoring_terms), reverse=True
                )
                results = scored[:3]

            for ref in results:
                # Deduplicate by title (case-insensitive)
                title_key = ref.title.lower().strip()
                if title_key in seen_titles:
                    continue
                seen_titles.add(title_key)
                all_refs.append(
                    {
                        "bibkey": ref.bibkey,
                        "title": ref.title,
                        "authors": ref.authors,
                        "year": ref.year,
                        "doi": ref.doi,
                        "url": ref.url,
                        "already_in_library": False,
                        "url_verified": True,  # From OpenAlex = real
                    }
                )
        except Exception as exc:
            logger.warning("OpenAlex search failed for %r: %s", query_str, exc)
            continue

    # Return as ExpandBibliographyProposal shape (what the frontend expects)
    return {"new_references": all_refs}


def validate_proposal_urls(proposal_json: dict[str, Any]) -> dict[str, Any]:
    """Validate URLs in reference proposals. Remove references without URLs
    and annotate the rest with url_verified."""
    from latris.ai.validate_urls import check_url

    refs = proposal_json.get("new_references", [])
    if not refs:
        return proposal_json

    validated: list[dict[str, Any]] = []
    for ref in refs:
        url = ref.get("url")
        doi = ref.get("doi")
        link = url or (f"https://doi.org/{doi}" if doi else None)
        if not link:
            # No URL at all — discard this reference
            continue
        ref["url_verified"] = check_url(link)
        validated.append(ref)

    proposal_json["new_references"] = validated
    return proposal_json
