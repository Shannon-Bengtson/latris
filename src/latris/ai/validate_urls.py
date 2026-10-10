"""Post-hoc URL validation for AI-proposed references.

After the LLM proposes references, we check that their URLs actually
resolve (HEAD request with short timeout). References with broken URLs
are flagged so the frontend can warn the user.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

_TIMEOUT = 8  # seconds per request
_MAX_WORKERS = 4


def check_url(url: str) -> bool:
    """Return True if the URL responds with a non-error status (2xx/3xx)."""
    try:
        req = Request(
            url,
            method="HEAD",
            headers={
                "User-Agent": "Mozilla/5.0 (Latris reference checker)",
            },
        )
        resp = urlopen(req, timeout=_TIMEOUT)
        return resp.status < 400
    except HTTPError as e:
        # Some sites block HEAD but allow GET — try GET with range
        if e.code == 405 or e.code == 403:
            try:
                req = Request(
                    url,
                    method="GET",
                    headers={
                        "User-Agent": "Mozilla/5.0 (Latris reference checker)",
                        "Range": "bytes=0-0",
                    },
                )
                resp = urlopen(req, timeout=_TIMEOUT)
                return resp.status < 400
            except Exception:
                # 403 might just be access control, URL still exists
                return e.code == 403
        return False
    except (URLError, OSError, ValueError):
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
            except Exception:
                valid = False
            results.append({"index": idx, "url": url, "valid": valid})

    results.sort(key=lambda r: r["index"])
    return results
