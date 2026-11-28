"""Post-hoc URL validation for AI-proposed references.

After the LLM proposes references, we check that their URLs actually
resolve (HEAD request with short timeout, through the SSRF guard). References with broken URLs
are flagged so the frontend can warn the user.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

_TIMEOUT = 8  # seconds per request
_MAX_WORKERS = 4
_USER_AGENT = "Mozilla/5.0 (Latris reference checker)"


def check_url(url: str) -> bool:
    """Return True if the URL responds with a non-error status (2xx/3xx).

    URLs come from model output, so every request is guarded: http(s) only,
    public addresses only (no probing loopback, other sessions or cloud
    metadata), on the first request and after every redirect. A blocked URL
    counts as not valid.
    """
    import httpx

    from latris._net_guard import safe_status

    try:
        status = safe_status(url, method="HEAD", timeout=_TIMEOUT, headers={"User-Agent": _USER_AGENT})
        if status < 400:
            return True
        if status not in (403, 405):
            return False
        # Some sites block HEAD but allow GET — try GET with range
        try:
            retry = safe_status(
                url, method="GET", timeout=_TIMEOUT, headers={"User-Agent": _USER_AGENT, "Range": "bytes=0-0"}
            )
        except (httpx.HTTPError, ValueError):  # a blocked URL is a ValueError too
            retry = None
        if retry is not None and retry < 400:
            return True
        # 403 might just be access control, URL still exists
        return status == 403
    except (httpx.HTTPError, ValueError, OSError):
        return False


def validate_reference_urls(
    references: list,
) -> list[dict]:
    """Validate URLs for a list of CitationSuggestion-like objects.

    Returns a list of dicts with {index, url, valid} for each reference
    that has a url field. References without URLs get valid=False.
    """
    results: list[dict] = []

    # Collect URLs to check
    tasks: list[tuple[int, str]] = []
    for i, ref in enumerate(references):
        url = getattr(ref, "url", None) or (getattr(ref, "doi", None) and f"https://doi.org/{ref.doi}")
        if url:
            tasks.append((i, url))
        else:
            results.append({"index": i, "url": None, "valid": False})

    if not tasks:
        return results

    # Check URLs in parallel
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        futures = {pool.submit(check_url, url): (idx, url) for idx, url in tasks}
        for future in as_completed(futures):
            idx, url = futures[future]
            try:
                valid = future.result()
            except Exception:  # noqa: BLE001 — check_url handles the expected errors; one bad URL can't fail the batch
                logger.warning("checking %s failed unexpectedly", url, exc_info=True)
                valid = False
            results.append({"index": idx, "url": url, "valid": valid})

    results.sort(key=lambda r: r["index"])
    return results
