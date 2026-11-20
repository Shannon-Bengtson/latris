"""Shared code asks a model type's registry entry; it doesn't test the type's id (latris#3).

Each model type declares what differs about it in ``operations/formalisms/`` — its outcome, membership,
wording, scenario store, diagram direction, link attribute, readiness when empty. A branch like ``model_type == "sd"`` in shared
code would bring back the per-type wiring the registry replaced, so this test fails on one.
Data locations (``view_attribute_path("cld", "polarity")``) and defaults (``or "cld"``) are not branches.
"""

from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "latris"
TYPES = r"(cld|dag|fcm|bn|sd|mcda|ach|decision_tree|markov|theory_of_change|fault_tree|event_tree|bow_tie)"
BRANCH = re.compile(
    rf"""(model_type|spec\.id|view|kind)\s*(==|!=)\s*["']{TYPES}["']"""
    rf"""|(model_type|spec\.id)\s+(not\s+)?in\s+\(["']{TYPES}["']"""
    rf"""|["']{TYPES}["']\s+(not\s+)?in\s+(types\b|selected\b|set\(|[a-z_.]*selected_model_types)"""
)
# Modules that are one type's own code (its operations, CLI, routes, registry entry) may name it.
OWN = ("operations/formalisms/", "cli/", "server/routes/", "operations/sd", "operations/bn", "operations/fcm",
       "operations/mcda", "operations/ach", "operations/decision_tree", "operations/markov", "operations/toc",
       "operations/fault_tree", "operations/event_tree", "operations/bow_tie", "operations/process_tracing",
       "operations/estimation", "operations/impact", "operations/risk_uncertainty", "schema/")


def test_shared_code_has_no_model_type_branches():
    hits = []
    for path in SRC.rglob("*.py"):
        rel = path.relative_to(SRC).as_posix()
        if rel.startswith(OWN):
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if BRANCH.search(line):
                hits.append(f"{rel}:{n}: {line.strip()}")
    assert hits == [], "ask the type's Formalism instead:\n" + "\n".join(hits)
