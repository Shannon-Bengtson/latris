#!/usr/bin/env python3
"""The weekly health report: the code-quality measurements that aren't run on every push.

CI already enforces the rules that matter per change (lint, the suite, the coverage floor, the
complexity, type and route guards). This report looks at the whole codebase from further back, the way
a periodic review would: known vulnerabilities in the dependencies, risky patterns, how complexity,
size, duplication, dead code and type errors stand, and how far each ratchet list has shrunk. It runs
from ``.github/workflows/health.yml`` (weekly, and on demand), writes Markdown to stdout and to the
job summary, and exits 1 only on what can go wrong without any change to this repository: a known
vulnerability in a dependency, or a test that fails with today's releases of the dependencies.
Everything else is information.

    python scripts/health_report.py --src src/latris --ratchet tests/complexity_exceptions.txt ...

Each section runs on its own: a tool that is missing or fails is reported as such and the rest go on.
The Latris app keeps a copy of this script (``scripts/health_report.py`` there); change both together.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path.cwd()


def run(cmd: list[str], *, cwd: Path | None = None, timeout: int = 1800) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd or ROOT, capture_output=True, text=True, timeout=timeout)


def have(tool: str) -> bool:
    return shutil.which(tool) is not None


class Report:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.failed = False  # a known vulnerability: the run goes red
        self.headline: list[str] = []  # one line per section, at the top

    def section(self, title: str) -> None:
        self.lines += ["", f"## {title}", ""]

    def add(self, *lines: str) -> None:
        self.lines += lines

    def table(self, header: list[str], rows: list[list[object]]) -> None:
        self.lines.append("| " + " | ".join(header) + " |")
        self.lines.append("|" + "|".join("---" for _ in header) + "|")
        for row in rows:
            self.lines.append("| " + " | ".join(str(c).replace("|", "\\|") for c in row) + " |")

    def note(self, label: str, value: str) -> None:
        self.headline.append(f"| {label} | {value} |")

    def markdown(self, title: str) -> str:
        head = [f"# {title}", "", "| Check | Result |", "|---|---|", *self.headline]
        return "\n".join(head + self.lines) + "\n"


# ── Dependencies ─────────────────────────────────────────────────────────────


def pip_dependencies(rep: Report) -> None:
    rep.section("Python dependencies: known vulnerabilities (pip-audit)")
    if not have("pip-audit"):
        rep.add("_pip-audit is not installed._")
        rep.note("Python dependencies", "not checked")
        return
    out = run(["pip-audit", "--format", "json", "--progress-spinner", "off", "--skip-editable"])
    try:
        deps = json.loads(out.stdout)["dependencies"]
    except (ValueError, KeyError):
        rep.add("_pip-audit didn't run:_", "", "```", (out.stderr or out.stdout)[-2000:], "```")
        rep.note("Python dependencies", "pip-audit failed")
        return
    found = [(d["name"], d["version"], v) for d in deps for v in d.get("vulns", [])]
    if not found:
        rep.add(f"No known vulnerabilities in {len(deps)} installed packages.")
        rep.note("Python dependencies", f"✅ none known ({len(deps)} packages)")
        return
    rep.failed = True
    rep.table(["Package", "Installed", "Advisory", "Fixed in"],
              [[n, ver, v["id"], ", ".join(v.get("fix_versions", [])) or "—"] for n, ver, v in found])
    rep.note("Python dependencies", f"❌ {len(found)} known vulnerabilit{'y' if len(found) == 1 else 'ies'}")


def npm_dependencies(rep: Report, package_dir: Path) -> None:
    rep.section(f"npm dependencies: known vulnerabilities ({package_dir})")
    if not have("npm"):
        rep.add("_npm is not installed._")
        rep.note("npm dependencies", "not checked")
        return
    counts = {}
    for label, extra in (("everything", []), ("what ships (runtime only)", ["--omit=dev"])):
        out = run(["npm", "audit", "--json", *extra], cwd=package_dir)
        try:
            data = json.loads(out.stdout)
        except ValueError:
            rep.add(f"_npm audit didn't run:_ {(out.stderr or out.stdout)[-500:]}")
            rep.note("npm dependencies", "npm audit failed")
            return
        counts[label] = data
    total = counts["everything"]["metadata"]["vulnerabilities"]
    shipped = counts["what ships (runtime only)"]["metadata"]["vulnerabilities"]
    rep.table(["Scope", "critical", "high", "moderate", "low"],
              [[label, d["metadata"]["vulnerabilities"]["critical"], d["metadata"]["vulnerabilities"]["high"],
                d["metadata"]["vulnerabilities"]["moderate"], d["metadata"]["vulnerabilities"]["low"]]
               for label, d in counts.items()])
    rows = []
    for name, v in sorted(counts["everything"]["vulnerabilities"].items(),
                          key=lambda kv: ("critical", "high", "moderate", "low", "info").index(kv[1]["severity"])):
        advisories = [x["title"] for x in v["via"] if isinstance(x, dict)]
        fix = v.get("fixAvailable")
        if isinstance(fix, dict):
            fix_text = f"{fix['name']}@{fix['version']}" + (" (major)" if fix.get("isSemVerMajor") else "")
        else:
            fix_text = "yes" if fix else "no"
        if advisories:
            rows.append([name, v["severity"], "; ".join(a[:70] for a in advisories[:2]), fix_text])
    if rows:
        rep.add("")
        rep.table(["Package", "Severity", "Advisory", "Fix"], rows)
    serious = total["critical"] + total["high"]
    if shipped["total"] or serious:
        rep.failed = True
        rep.note("npm dependencies", f"❌ {shipped['total']} in what ships, {serious} critical/high in tooling")
    else:
        rep.note("npm dependencies", f"✅ none in what ships; {total['total']} moderate/low in tooling")


# ── Code ─────────────────────────────────────────────────────────────────────


def security_patterns(rep: Report, srcs: list[str]) -> None:
    rep.section("Risky code patterns (bandit, medium and high)")
    if not have("bandit"):
        rep.add("_bandit is not installed._")
        return
    out = run(["bandit", "-r", *srcs, "-f", "json", "-q", "-ll"])
    try:
        data = json.loads(out.stdout)
    except ValueError:
        rep.add(f"_bandit didn't run:_ {out.stderr[-500:]}")
        return
    issues = data["results"]
    totals = data["metrics"]["_totals"]
    rep.add(f"High {totals['SEVERITY.HIGH']}, medium {totals['SEVERITY.MEDIUM']}, low {totals['SEVERITY.LOW']} "
            "(low not listed). Each needs a look, not necessarily a change: a flagged `exec` on a whitelisted "
            "AST, or SHA-1 used as a cache key, is fine.")
    if issues:
        rep.add("")
        rep.table(["Severity", "Where", "What"],
                  [[i["issue_severity"].lower(), f"`{i['filename']}:{i['line_number']}`", i["issue_text"][:90]]
                   for i in sorted(issues, key=lambda i: (i["issue_severity"] != "HIGH", i["filename"]))])
    rep.note("Risky patterns (bandit)", f"{totals['SEVERITY.HIGH']} high, {totals['SEVERITY.MEDIUM']} medium")


def complexity(rep: Report, srcs: list[str]) -> None:
    rep.section("Complexity (radon)")
    if not have("radon"):
        rep.add("_radon is not installed._")
        return
    out = run(["radon", "cc", *srcs, "-j"])
    try:
        data = json.loads(out.stdout)
    except ValueError:
        rep.add(f"_radon didn't run:_ {out.stderr[-500:]}")
        return
    blocks = [(b["complexity"], f, b.get("classname") or "", b["name"], b["rank"])
              for f, bs in data.items() if isinstance(bs, list) for b in bs if isinstance(b, dict)]
    grades = Counter(b[4] for b in blocks)
    mean = sum(b[0] for b in blocks) / len(blocks) if blocks else 0
    rep.add(f"{len(blocks)} functions and methods; mean cyclomatic complexity {mean:.1f}. By grade (A best, "
            "F worst; E and F are over 30, the complexity guard's limit):", "")
    rep.table(["A", "B", "C", "D", "E", "F"], [[grades.get(g, 0) for g in "ABCDEF"]])
    rep.add("", "The ten most complex:", "")
    worst = sorted(blocks, reverse=True)[:10]
    rep.table(["Complexity", "Function"],
              [[c, f"`{f}::{(cls + '.') if cls else ''}{name}`"] for c, f, cls, name, _ in worst])
    rep.note("Complexity", f"mean {mean:.1f}; {grades.get('E', 0) + grades.get('F', 0)} functions over 30")

    out = run(["radon", "mi", *srcs, "-j"])
    try:
        mi = json.loads(out.stdout)
    except ValueError:
        return
    low = sorted((v["mi"], f) for f, v in mi.items() if isinstance(v, dict) and v.get("rank") in ("B", "C"))
    rep.add("", f"Maintainability index: {len(mi) - len(low)} files rated A, {len(low)} rated B or C (lowest first):")
    if low:
        rep.add("", *[f"- `{f}` ({m:.0f})" for m, f in low[:12]])


def sizes(rep: Report, srcs: list[str]) -> None:
    rep.section("Size")
    files = [(sum(1 for _ in p.open(encoding="utf-8", errors="replace")), p)
             for s in srcs for p in Path(s).rglob("*.py")]
    total = sum(n for n, _ in files)
    big = sorted(files, reverse=True)
    rep.add(f"{len(files)} Python files, {total:,} lines. Over 1,000 lines: "
            f"{sum(1 for n, _ in files if n > 1000)}. The largest:", "")
    rep.table(["Lines", "File"], [[f"{n:,}", f"`{p.as_posix()}`"] for n, p in big[:8]])
    rep.note("Size", f"{total:,} lines; largest file {big[0][0]:,}" if big else "—")


def dead_code(rep: Report, srcs: list[str]) -> None:
    rep.section("Dead code (vulture, 80% confidence and over)")
    if not have("vulture"):
        rep.add("_vulture is not installed._")
        return
    out = run(["vulture", *srcs, "--min-confidence", "80"])
    found = [ln for ln in out.stdout.splitlines() if ln.strip()]
    rep.add(*(f"- `{ln}`" for ln in found[:30])) if found else rep.add("Nothing found.")
    rep.note("Dead code (vulture)", f"{len(found)} found")


def lint_breadth(rep: Report, srcs: list[str]) -> None:
    rep.section("Lint beyond the project's rules (ruff, information only)")
    if not have("ruff"):
        rep.add("_ruff is not installed._")
        return
    out = run(["ruff", "check", *srcs, "--isolated", "--line-length", "120", "--statistics",
               "--select", "C90,PL,ARG,PERF,BLE,TRY,S", "--exit-zero"])
    rows = [ln.split(None, 2) for ln in out.stdout.splitlines() if re.match(r"\s*\d+\s+\w+", ln)]
    rep.add("Rule sets the project doesn't enforce, to see where the code leans. Most are style; "
            "`BLE001` (catching every exception) and `ARG` (unused arguments) are worth a look.", "")
    rep.table(["Count", "Rule", "What"], [[r[0], f"`{r[1]}`", r[2].replace("[*] ", "").replace("[ ] ", "").strip()]
                                         for r in rows[:12]])


def duplication(rep: Report, label: str, src: str, ignore: str = "") -> None:
    if not have("npx"):
        return
    with tempfile.TemporaryDirectory() as out_dir:
        cmd = ["npx", "--yes", "jscpd@4.0.5", src, "--silent", "--min-tokens", "70", "--reporters", "json",
               "--output", out_dir]
        if ignore:
            cmd += ["--ignore", ignore]
        run(cmd, timeout=900)
        report = Path(out_dir) / "jscpd-report.json"
        if not report.exists():
            rep.add(f"- {label}: _jscpd didn't run_")
            return
        total = json.loads(report.read_text())["statistics"]["total"]
    rep.add(f"- {label} (`{src}`): {total['percentage']}% duplicated, {total['clones']} clones")
    rep.note(f"Duplication ({label})", f"{total['percentage']}%")


# ── Tests and the ratchets ───────────────────────────────────────────────────


def tests_and_coverage(rep: Report, pytest_args: list[str]) -> None:
    rep.section("Tests and coverage (with today's dependency versions)")
    cov_json = ROOT / ".health-coverage.json"
    out = run([sys.executable, "-m", "pytest", *pytest_args, "-q", "-p", "no:cacheprovider", "--cov",
               "--cov-report=term", f"--cov-report=json:{cov_json}", "--cov-fail-under=0"], timeout=3600)
    summary = next((ln for ln in reversed(out.stdout.splitlines()) if re.search(r"\d+ (passed|failed)", ln)), "")
    total = next((ln.split()[-1] for ln in out.stdout.splitlines() if ln.startswith("TOTAL")), "?")
    failures = [ln for ln in out.stdout.splitlines() if ln.startswith(("FAILED", "ERROR"))]
    rep.add(f"`{summary.strip('= ')}`", "", f"Coverage: **{total}**.")
    if failures:
        rep.add("", "A failure here and not on the last push usually means a new release of a dependency "
                "changed something:", "", *(f"- `{f[:160]}`" for f in failures[:20]))
    least_covered(rep, cov_json)
    if failures or out.returncode:
        rep.failed = True
    rep.note("Tests", ("❌ " if failures or out.returncode else "✅ ") + f"{summary.strip('= ')}; coverage {total}")


def least_covered(rep: Report, cov_json: Path, *, count: int = 10, min_statements: int = 40) -> None:
    """The files with the lowest coverage (of those big enough to matter), so the trend shows week to week."""
    if not cov_json.exists():
        return
    try:
        files = json.loads(cov_json.read_text(encoding="utf-8"))["files"]
    finally:
        cov_json.unlink()
    rows = sorted(
        ([v["summary"]["percent_covered"], v["summary"]["num_statements"], v["summary"]["missing_lines"], name]
         for name, v in files.items() if v["summary"]["num_statements"] >= min_statements),
        key=lambda r: r[0],
    )[:count]
    if rows:
        rep.add("", f"The {len(rows)} least-covered files ({min_statements} statements and over):", "")
        rep.table(["Coverage", "Statements", "Missing", "File"],
                  [[f"{pct:.0f}%", n, miss, f"`{name}`"] for pct, n, miss, name in rows])


def ratchets(rep: Report, files: list[str]) -> None:
    rep.section("Ratchet lists (they only shrink)")
    rows = []
    for name in files:
        path = Path(name)
        if not path.exists():
            continue
        if path.suffix == ".json":
            data = json.loads(path.read_text(encoding="utf-8"))
            count = len(data) if isinstance(data, list | dict) else "?"
        else:
            entries = [ln.split() for ln in path.read_text(encoding="utf-8").splitlines()
                       if ln.strip() and not ln.lstrip().startswith("#")]
            numeric = all(len(e) == 2 and e[1].isdigit() for e in entries) and name.endswith("type_errors.txt")
            count = f"{sum(int(e[1]) for e in entries)} errors in {len(entries)} files" if numeric else len(entries)
        rows.append([f"`{name}`", count])
    rep.table(["List", "Entries"], rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--title", default="Health report")
    ap.add_argument("--src", action="append", required=True, help="a Python source folder (repeat)")
    ap.add_argument("--ratchet", action="append", default=[], help="a list that only shrinks (repeat)")
    ap.add_argument("--npm", help="a folder with package.json to audit")
    ap.add_argument("--js-src", help="a JS/TS source folder to measure duplication in")
    ap.add_argument("--pytest-args", default="", help="arguments for the test run, e.g. 'tests -n auto'")
    ap.add_argument("--skip-tests", action="store_true", help="leave out the test run (quicker, for trying it)")
    ap.add_argument("--out", help="also write the report here")
    args = ap.parse_args()

    rep = Report()

    def dup() -> None:
        rep.section("Duplication (jscpd, 70 tokens and over)")
        for s in args.src:
            duplication(rep, "Python", s)
        if args.js_src:
            duplication(rep, "TypeScript", args.js_src, "**/generated/**,**/*.test.*,**/__tests__/**")

    steps = [lambda: pip_dependencies(rep)]
    if args.npm:
        steps.append(lambda: npm_dependencies(rep, Path(args.npm)))
    if not args.skip_tests:
        steps.append(lambda: tests_and_coverage(rep, args.pytest_args.split()))
    steps += [lambda: security_patterns(rep, args.src), lambda: complexity(rep, args.src),
              lambda: sizes(rep, args.src), lambda: dead_code(rep, args.src), dup,
              lambda: lint_breadth(rep, args.src), lambda: ratchets(rep, args.ratchet)]
    for step in steps:
        try:
            step()
        except Exception as exc:  # noqa: BLE001 — one tool's failure is reported, and the rest still run
            rep.add("", f"_This section failed: {type(exc).__name__}: {exc}_")

    text = rep.markdown(args.title)
    print(text)
    for target in filter(None, (args.out, os.environ.get("GITHUB_STEP_SUMMARY"))):
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(text)
    return 1 if rep.failed else 0


if __name__ == "__main__":
    sys.exit(main())
