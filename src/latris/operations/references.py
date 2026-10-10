"""Reference library operations.

CRUD + BibTeX import + DOI import + OpenAlex search.
"""

from __future__ import annotations

import hashlib
import re
from contextlib import suppress
from pathlib import Path

from latris.operations.commit import auto_commit
from latris.repo.layout import ProjectPaths
from latris.repo.project import require_project
from latris.repo.yaml_io import dump_model, load_model
from latris.schema import Reference, ReferenceLibrary, SourceSnapshot, SourceSnapshotKind
from latris.schema.common import SourceAccess

# ── Helpers ────���─────────────────────────────────────────────────────


def load_library(paths: ProjectPaths) -> tuple[ReferenceLibrary, Path]:
    """Load the reference library, backfilling any missing IDs."""
    library_path = paths.references_yaml
    if not library_path.exists():
        return ReferenceLibrary(), library_path
    library = load_model(ReferenceLibrary, library_path)
    _ensure_ids(library, library_path)
    return library, library_path


def _ensure_ids(library: ReferenceLibrary, library_path: Path) -> bool:
    """Backfill IDs for references that pre-date the id field.

    Pydantic's ``default_factory`` fills in random IDs during load, so
    we can't detect missing IDs by inspecting the model.  Instead, read
    the raw YAML and check for entries lacking an ``id`` key.  If any
    are found, persist the library (with its pydantic-generated IDs) to
    make them stable across loads.
    """
    if not library_path.exists() or not library.entries:
        return False
    from ruamel.yaml import YAML as _RuamelYAML

    y = _RuamelYAML(typ="safe", pure=True)
    raw = y.load(library_path.read_text(encoding="utf-8")) or {}
    raw_entries = raw.get("entries") or []
    if any("id" not in entry for entry in raw_entries):
        dump_model(library, library_path)
        return True
    return False


def _find_ref(library: ReferenceLibrary, query: str) -> Reference:
    """Resolve a reference by bibkey or id (or id-prefix)."""
    # Exact bibkey match.
    for r in library.entries:
        if r.bibkey == query:
            return r
    # Exact id match.
    for r in library.entries:
        if r.id == query:
            return r
    # ID prefix match (min 4 chars after underscore).
    if query.startswith("reference_") and len(query) > len("reference_") + 3:
        matches = [r for r in library.entries if r.id.startswith(query)]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise ValueError(f"ambiguous prefix {query!r} matches {len(matches)} references")
    raise ValueError(f"no reference matching {query!r}")


# ── Read ──────────────────────────────────────��──────────────────────


def list_references(root: Path | None = None) -> list[Reference]:
    paths = require_project(root)
    library, _ = load_library(paths)
    return library.entries


def get_reference(query: str, *, root: Path | None = None) -> Reference:
    """Resolve a single reference by bibkey, id, or id-prefix."""
    paths = require_project(root)
    library, _ = load_library(paths)
    return _find_ref(library, query)


# ── Create ───────────────────────────────────────────────────────────


def add_reference(
    bibkey: str,
    title: str,
    *,
    authors: list[str] | None = None,
    year: int | None = None,
    container: str | None = None,
    doi: str | None = None,
    url: str | None = None,
    notes: str | None = None,
    root: Path | None = None,
) -> tuple[Reference, str]:
    paths = require_project(root)
    library, library_path = load_library(paths)

    if any(r.bibkey == bibkey for r in library.entries):
        raise ValueError(f"reference with bibkey {bibkey!r} already exists")

    ref = Reference(
        bibkey=bibkey,
        title=title,
        authors=authors or [],
        year=year,
        container=container,
        doi=doi,
        url=url,
        notes=notes,
        imported_from="manual",
    )
    library.entries.append(ref)
    dump_model(library, library_path)

    sha = auto_commit(
        paths.root,
        subject=f'Added reference "{bibkey}"',
        body=f"title: {title}",
        paths=[library_path],
    )
    return ref, sha


# ── Source access + snapshot (AI interrogation Phase 2) ──────────────


def compute_source_access(reference: Reference) -> SourceAccess:
    """Determine what level of source access a Reference grants.

    `landing_page_text` snapshots are deliberately NOT promoted to
    `abstract` — generic publisher landing-page copy is not the
    paper's content, and verification prompts should not treat it
    as such. See docs/design/AI_INTERROGATION.md Phase 2.
    """
    if reference.abstract:
        return "abstract"
    snapshot = reference.source_snapshot
    if snapshot is not None and snapshot.kind in {"abstract", "full_text_excerpt"}:
        return "abstract"
    return "title_only"


def set_source_snapshot(
    bibkey: str,
    *,
    retrieval_url: str,
    extract: str,
    kind: SourceSnapshotKind = "abstract",
    root: Path | None = None,
) -> tuple[Reference, str]:
    """Persist a fetched source snapshot against a Reference.

    Phase 4 will fill the URL→fetch path automatically; Phase 2
    exposes the manual setter so the schema slot is reachable from
    operations and CLI today.
    """
    paths = require_project(root)
    library, library_path = load_library(paths)
    ref = _find_ref(library, bibkey)

    content_hash = "sha256:" + hashlib.sha256(extract.encode("utf-8")).hexdigest()
    ref.source_snapshot = SourceSnapshot(
        retrieval_url=retrieval_url,
        content_hash=content_hash,
        extract=extract,
        kind=kind,
    )

    dump_model(library, library_path)
    sha = auto_commit(
        paths.root,
        subject=f'Set source snapshot for "{ref.bibkey}" ({kind})',
        body=f"retrieval_url: {retrieval_url}\ncontent_hash: {content_hash}",
        paths=[library_path],
    )
    return ref, sha


# ── Tier-1 fetch (AI interrogation Phase 4b) ─────────────────────────


_HTML_TAG_RE = re.compile(r"<[^>]+>")
_HTML_SCRIPT_STYLE_RE = re.compile(
    r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL
)
_HTML_WHITESPACE_RE = re.compile(r"\s+")


def _strip_html(html: str) -> str:
    """Deterministic HTML → readable text. No bs4 dep.

    Drops <script> and <style> blocks first (their textContent is
    code, not prose), then strips remaining tags, then collapses
    whitespace. Adequate for verification: the apply-time check
    requires verbatim match against this same text.
    """
    no_scripts = _HTML_SCRIPT_STYLE_RE.sub(" ", html)
    no_tags = _HTML_TAG_RE.sub(" ", no_scripts)
    return _HTML_WHITESPACE_RE.sub(" ", no_tags).strip()


def _extract_pdf_text(content: bytes) -> str:
    """Extract text from a PDF byte payload. Optional pypdf dep.

    Raises a clear ValueError if pypdf isn't installed, pointing the
    user at the install path. We keep PDF support optional so the
    minimum-deps story stays clean — HTML/text fetch works without
    any new package.
    """
    try:
        import pypdf  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ValueError(
            "PDF fetch needs `pypdf` installed (`pip install pypdf`). "
            "Until then, paste source content via "
            "`latris ref snapshot <bibkey> --extract ...` instead."
        ) from exc

    import io

    reader = pypdf.PdfReader(io.BytesIO(content))
    pages: list[str] = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:  # noqa: BLE001 — extraction is best-effort per page
            pages.append("")
    return "\n".join(pages).strip()


def _resolve_fetch_url(ref: Reference) -> str:
    """Pick the URL to fetch for a Reference. Argument > ref.url > DOI."""
    if ref.url:
        return ref.url
    if ref.doi:
        # DOI resolves through doi.org — publisher landing page in
        # most cases. Tier-2 will route OA papers through OpenAlex /
        # arXiv first; for Phase 4b this is the simple path.
        return f"https://doi.org/{ref.doi.strip()}"
    raise ValueError(
        f"reference {ref.bibkey!r} has no `url` or `doi` to fetch from. "
        "Set one with `latris ref update`, or pass --url explicitly."
    )


_EXTRACT_CHARS = 2000


def fetch_reference_source(
    bibkey: str,
    *,
    url: str | None = None,
    http_get=None,  # injection seam for tests; defaults to httpx.get
    root: Path | None = None,
) -> tuple[Reference, str]:
    """Fetch a reference's full text and store it as a per-bibkey artefact.

    Phase 4b. Resolves the URL (argument > ``ref.url`` > DOI), fetches
    with httpx, and writes the extracted text to
    ``paths.references_extracts_dir / f"{bibkey}.txt"``. Updates the
    Reference's ``source_snapshot`` with ``kind="full_text_excerpt"``,
    ``extract`` = first ``_EXTRACT_CHARS`` of full text, retrieval URL,
    fetched_at, and the content hash of the full text.

    Refetches overwrite — git history preserves prior snapshots, the
    same git-native principle that drove Phase 3.

    The ``http_get`` parameter is an injection seam for tests; default
    uses ``httpx.get``. Tests pass a stub to stay hermetic.
    """
    import httpx

    from latris.schema.common import now_utc

    paths = require_project(root)
    library, library_path = load_library(paths)
    ref = _find_ref(library, bibkey)

    target_url = url or _resolve_fetch_url(ref)
    fetch = http_get if http_get is not None else httpx.get

    response = fetch(
        target_url,
        timeout=20,
        follow_redirects=True,
        headers={"User-Agent": "Latris/0.1 (source verification)"},
    )
    response.raise_for_status()

    content_type = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
    final_url = str(getattr(response, "url", None) or target_url)

    if content_type == "application/pdf" or final_url.lower().endswith(".pdf"):
        full_text = _extract_pdf_text(response.content)
    elif content_type in {"text/plain", ""}:
        # Some servers omit content-type for .txt; treat as plain text.
        full_text = response.text.strip()
    else:
        # Default: HTML/XHTML/etc. → strip tags.
        full_text = _strip_html(response.text)

    if not full_text:
        raise ValueError(
            f"fetched {target_url!r} but extracted empty text — the URL may "
            "be a paywall, login gate, or non-text resource."
        )

    # Persist artefact (gitignored).
    paths.references_extracts_dir.mkdir(parents=True, exist_ok=True)
    artefact = paths.references_extract_path(bibkey)
    artefact.write_text(full_text, encoding="utf-8", newline="")

    content_hash = "sha256:" + hashlib.sha256(full_text.encode("utf-8")).hexdigest()
    extract = full_text[:_EXTRACT_CHARS]
    ref.source_snapshot = SourceSnapshot(
        retrieval_url=final_url,
        fetched_at=now_utc(),
        content_hash=content_hash,
        extract=extract,
        kind="full_text_excerpt",
    )

    dump_model(library, library_path)
    sha = auto_commit(
        paths.root,
        subject=f'Fetched source for "{bibkey}" ({len(full_text)} chars)',
        body=(
            f"retrieval_url: {final_url}\n"
            f"content_hash: {content_hash}\n"
            f"chars: {len(full_text)}"
        ),
        paths=[library_path],
    )
    return ref, sha


# ── Update ────��───────────────────────────────��──────────────────────


def update_reference(
    bibkey: str,
    *,
    title: str | None = None,
    authors: list[str] | None = None,
    year: int | None = None,
    container: str | None = None,
    doi: str | None = None,
    url: str | None = None,
    notes: str | None = None,
    root: Path | None = None,
) -> tuple[Reference, str]:
    paths = require_project(root)
    library, library_path = load_library(paths)
    ref = _find_ref(library, bibkey)

    if title is not None:
        ref.title = title
    if authors is not None:
        ref.authors = authors
    if year is not None:
        ref.year = year
    if container is not None:
        ref.container = container
    if doi is not None:
        ref.doi = doi
    if url is not None:
        ref.url = url
    if notes is not None:
        ref.notes = notes

    dump_model(library, library_path)
    sha = auto_commit(
        paths.root,
        subject=f'Updated reference "{ref.bibkey}"',
        body="",
        paths=[library_path],
    )
    return ref, sha


# ── Delete ────────────���──────────────────────────────────────────────


def remove_reference(
    bibkey: str,
    *,
    root: Path | None = None,
) -> tuple[Reference, str]:
    """Remove a reference.  Raises ValueError if evidence links still cite it."""
    paths = require_project(root)
    library, library_path = load_library(paths)
    ref = _find_ref(library, bibkey)

    # Referential integrity: check evidence links.
    from latris.schema import EvidenceLinkSet

    evidence_path = paths.evidence_links_yaml
    if evidence_path.exists():
        evidence = load_model(EvidenceLinkSet, evidence_path)
        citing = [e for e in evidence.entries if e.bibkey == ref.bibkey]
        if citing:
            raise ValueError(f"cannot remove reference {ref.bibkey!r}: {len(citing)} evidence link(s) still cite it")

    library.entries = [r for r in library.entries if r.bibkey != ref.bibkey]
    dump_model(library, library_path)
    sha = auto_commit(
        paths.root,
        subject=f'Removed reference "{ref.bibkey}"',
        body="",
        paths=[library_path],
    )
    return ref, sha


# ── BibTeX import ─────────��──────────────────────────────────────────


def import_bibtex(
    bibtex_content: str,
    *,
    root: Path | None = None,
) -> tuple[list[Reference], str]:
    """Parse a BibTeX string and add new references.  Skips duplicates by bibkey."""
    import bibtexparser

    bib = bibtexparser.loads(bibtex_content)

    paths = require_project(root)
    library, library_path = load_library(paths)
    existing_keys = {r.bibkey for r in library.entries}

    added: list[Reference] = []
    for entry in bib.entries:
        key = entry.get("ID", "")
        if not key or key in existing_keys:
            continue

        # Map BibTeX fields → Reference fields.
        raw_author = entry.get("author", "")
        authors = [a.strip() for a in raw_author.split(" and ")] if raw_author else []

        year = None
        raw_year = entry.get("year", "")
        if raw_year:
            with suppress(ValueError, TypeError):
                year = int(raw_year)

        container = None
        for cfield in ("journal", "booktitle", "series"):
            val = entry.get(cfield)
            if val:
                container = val
                break

        title = entry.get("title", key)

        abstract = entry.get("abstract") or None

        ref = Reference(
            bibkey=key,
            title=title,
            authors=authors,
            year=year,
            container=container,
            doi=entry.get("doi"),
            url=entry.get("url"),
            abstract=abstract,
            imported_from="bibtex",
        )
        library.entries.append(ref)
        existing_keys.add(key)
        added.append(ref)

    if not added:
        return [], ""

    dump_model(library, library_path)
    sha = auto_commit(
        paths.root,
        subject=f"Imported {len(added)} reference(s) from BibTeX",
        body=", ".join(r.bibkey for r in added),
        paths=[library_path],
    )
    return added, sha


# ── Academic search (OpenAlex) ───────────────────────────────────────

_OPENALEX_SEARCH_URL = "https://api.openalex.org/works"
_OPENALEX_SELECT = "title,authorships,publication_year,doi,primary_location,abstract_inverted_index"
_OPENALEX_HEADERS = {"User-Agent": "Latris/0.1 (mailto:latris-dev@example.com)"}


def _reconstruct_abstract(inverted_index: dict[str, list[int]] | None) -> str | None:
    """Reconstruct plain text from an OpenAlex abstract_inverted_index."""
    if not inverted_index:
        return None
    # Build (position, word) pairs and sort by position.
    pairs: list[tuple[int, str]] = []
    for word, positions in inverted_index.items():
        for pos in positions:
            pairs.append((pos, word))
    if not pairs:
        return None
    pairs.sort()
    return " ".join(word for _, word in pairs)


def _openalex_paper_to_reference(paper: dict) -> Reference:
    """Convert a single OpenAlex work dict into an unsaved Reference."""
    author_names = [
        a["author"]["display_name"] for a in (paper.get("authorships") or []) if a.get("author", {}).get("display_name")
    ]

    doi_url = paper.get("doi") or ""
    doi = doi_url.replace("https://doi.org/", "") if doi_url else None

    loc = paper.get("primary_location") or {}
    source = loc.get("source") or {}
    venue = source.get("display_name") or None
    url = loc.get("landing_page_url") or doi_url or None

    first_surname = author_names[0].split()[-1].lower() if author_names else "unknown"
    year = paper.get("publication_year")
    bibkey = f"{first_surname}{year or 'nd'}"

    abstract = _reconstruct_abstract(paper.get("abstract_inverted_index"))

    return Reference(
        bibkey=bibkey,
        title=paper.get("title") or "",
        authors=author_names,
        year=year,
        container=venue,
        doi=doi,
        url=url,
        abstract=abstract,
        imported_from="openalex",
    )


_DOI_PATTERN = re.compile(r"(10\.\d{4,9}/[^\s]+)")


def _normalize_doi(raw: str) -> str:
    """Extract a clean DOI from various input formats.

    Accepts: ``10.xxxx/yyyy``, ``https://doi.org/10.xxxx/yyyy``,
    ``doi:10.xxxx/yyyy``, ``http://dx.doi.org/10.xxxx/yyyy``.
    Returns the bare DOI (e.g. ``10.xxxx/yyyy``).
    Raises ValueError if no DOI can be extracted.
    """
    raw = raw.strip()
    match = _DOI_PATTERN.search(raw)
    if not match:
        raise ValueError(f"could not extract a DOI from {raw!r}")
    return match.group(1)


def search_references(
    query: str,
    *,
    limit: int = 10,
) -> list[Reference]:
    """Search OpenAlex and return candidate Reference objects (not persisted)."""
    import httpx

    try:
        resp = httpx.get(
            _OPENALEX_SEARCH_URL,
            params={"search": query, "per_page": limit, "select": _OPENALEX_SELECT},
            headers=_OPENALEX_HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 429:
            return []
        raise
    except httpx.TimeoutException:
        return []

    results = resp.json().get("results") or []
    return [_openalex_paper_to_reference(paper) for paper in results[:limit]]


# ── DOI import ──────────────────────────────────────────────────────


def import_doi(
    raw_doi: str,
    *,
    root: Path | None = None,
) -> tuple[Reference, str]:
    """Fetch metadata from OpenAlex by DOI and add to the library.

    Raises ValueError if the DOI cannot be parsed, the lookup fails,
    or the DOI already exists in the library.
    """
    import httpx

    doi = _normalize_doi(raw_doi)

    paths = require_project(root)
    library, library_path = load_library(paths)

    # Duplicate check: DOI already in library.
    if any(r.doi == doi for r in library.entries):
        raise ValueError(f"a reference with DOI {doi!r} already exists")

    # Fetch from OpenAlex entity endpoint (single work).
    try:
        resp = httpx.get(
            f"{_OPENALEX_SEARCH_URL}/https://doi.org/{doi}",
            params={"select": _OPENALEX_SELECT},
            headers=_OPENALEX_HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise ValueError(f"DOI {doi!r} not found on OpenAlex") from exc
        raise
    except httpx.TimeoutException as exc:
        raise ValueError("OpenAlex request timed out") from exc

    ref = _openalex_paper_to_reference(resp.json())
    ref.imported_from = "doi"

    # Bibkey collision handling: append suffix if needed.
    existing_keys = {r.bibkey for r in library.entries}
    base_bibkey = ref.bibkey
    if base_bibkey in existing_keys:
        suffix = 2
        while f"{base_bibkey}_{suffix}" in existing_keys:
            suffix += 1
        ref.bibkey = f"{base_bibkey}_{suffix}"

    library.entries.append(ref)
    dump_model(library, library_path)

    sha = auto_commit(
        paths.root,
        subject=f'Imported reference "{ref.bibkey}" from DOI',
        body=f"doi: {doi}\ntitle: {ref.title}",
        paths=[library_path],
    )
    return ref, sha
