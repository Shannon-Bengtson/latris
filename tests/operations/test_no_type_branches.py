"""Shared code never branches on a model type's name: what sets a type apart is declared on its formalism.

A new type then needs no edits to shared code, and an old type's special treatment is visible in one
place (its module in ``operations/formalisms/``). This scans the shared layers (operations, exporters, server, ai,
diff) for comparisons against a registered model-type id. A type's own operations module (``operations/sd.py``, ``operations/mcda.py``,
…) is its implementation and may of course name it; so may the modules listed below, with why.
"""

from __future__ import annotations

import re
from pathlib import Path

from latris.schema.model_types import list_model_types

SRC = Path(__file__).resolve().parents[2] / "src" / "latris"

LAYERS = ("operations", "exporters", "server", "ai", "diff")

# Modules that legitimately name types, and why.
ALLOWED = {
    "operations/risk_uncertainty.py": "the Monte Carlo engine the three risk types share (their implementation)",
    "operations/psa.py": "the probabilistic sensitivity analysis decision trees and Markov models share (theirs)",
    "operations/init.py": "scaffolds each causal type's view files in a new project (data paths)",
}


def _pattern() -> re.Pattern[str]:
    ids = "|".join(sorted((s.id for s in list_model_types(include_planned=True)), key=len, reverse=True))
    return re.compile(
        rf"""(model_type|mt|view)\s*(==|!=)\s*["'](?:{ids})["']"""
        rf"""|(model_type|mt|view)\s+(?:not\s+)?in\s+[(\[{{][^\n]*["'](?:{ids})["']"""
        rf"""|["'](?:{ids})["']\s+(?:not\s+)?in\s+(?:types|selected|chosen|foundation\.selected_model_types)"""
    )


def _shared_modules() -> list[Path]:
    own = {f"operations/{s.id}.py" for s in list_model_types(include_planned=True)}
    files = [p for layer in LAYERS for p in SRC.joinpath(layer).rglob("*.py")]
    out = []
    for p in files:
        rel = p.relative_to(SRC).as_posix()
        if rel.startswith("operations/formalisms/") or rel in own or rel in ALLOWED:
            continue
        out.append(p)
    return out


def test_shared_code_has_no_model_type_branches():
    pat = _pattern()
    hits = [f"{p.relative_to(SRC)}:{i}: {line.strip()}"
            for p in _shared_modules() for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
            if pat.search(line)]
    assert not hits, "declare it on the formalism instead (operations/formalisms/__init__.py):\n" + "\n".join(hits)


def test_the_guard_catches_a_branch():
    assert _pattern().search('    if model_type == "sd":')
    assert _pattern().search('    if model_type in ("cld", "fcm") and causal:')
    assert _pattern().search('    if "bn" in types:')
    assert not _pattern().search('    direction = plugin.diagram_direction if plugin else "LR"')
