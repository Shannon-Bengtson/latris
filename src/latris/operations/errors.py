"""Exceptions shared by operations, mapped to HTTP statuses in one place (``server/app.py``).

- ``ValueError`` — the request is refused as asked (400).
- :class:`NotFoundError` — the thing named doesn't exist (404). Also a
  ``ValueError`` so callers that catch that keep working.
"""

from __future__ import annotations


class NotFoundError(LookupError, ValueError):
    """The element, run or record a request names doesn't exist."""
