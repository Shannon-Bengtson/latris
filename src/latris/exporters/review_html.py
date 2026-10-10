"""Self-contained HTML review pack exporter.

Generates a single HTML file that a reviewer can open in any browser,
add structured feedback (challenges, questions, signoffs) per element
or at project level, then save the annotated file. Feedback is embedded
in a ``<script type="application/json">`` tag that Latris can parse
on import.

No external dependencies — all CSS and JS are inline.
"""

from __future__ import annotations

import html
from datetime import UTC, datetime

from latris.exporters._format import actor_name as _actor_name
from latris.exporters.diagram import render_svg
from latris.exporters.packs import get_pack
from latris.repo.git import head_sha
from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import load_model
from latris.schema import (
    AssumptionLog,
    ChallengeLog,
    ConfidenceSet,
    DescriptionSet,
    EvidenceLinkSet,
    HumanActor,
    PolaritySet,
    ProjectFoundation,
    QuestionLog,
    ReferenceLibrary,
    Substrate,
    new_id,
)
from latris.schema.ids import id_timestamp
from latris.schema.review import ReviewManifest


def _h(text: str) -> str:
    """HTML-escape a string."""
    return html.escape(str(text), quote=True)


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

_CSS = """\
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
  line-height: 1.6; color: #2d2d2d; background: #f4f1eb;
  max-width: 900px; margin: 0 auto; padding: 24px 32px 64px;
}
h1 { font-size: 1.7em; color: #2a6b5e; margin-bottom: 4px; }
h2 { font-size: 1.25em; color: #2a6b5e; margin-top: 32px; border-bottom: 2px solid #2a6b5e; padding-bottom: 4px; }
h3 { font-size: 1.05em; color: #444; margin-top: 18px; }
.meta { color: #666; font-size: 0.9em; margin-bottom: 24px; }
.noscript-banner {
  background: #fff3cd; border: 1px solid #ffc107; padding: 12px 16px;
  border-radius: 6px; margin-bottom: 20px; font-size: 0.95em;
}
.diagram-container { margin: 20px 0; overflow-x: auto; }
.diagram-container svg { max-width: 100%; height: auto; }
table { width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 0.9em; }
th { background: #2a6b5e; color: #fff; text-align: left; padding: 8px 10px; font-weight: 600; }
td { padding: 7px 10px; border-bottom: 1px solid #ddd; vertical-align: top; }
tr:hover td { background: #f0ede6; }
.empty { color: #999; font-style: italic; margin: 8px 0; }
ul.prov { list-style: none; padding: 0; }
ul.prov li { padding: 5px 0; border-bottom: 1px solid #eee; font-size: 0.9em; }
/* Feedback controls */
.fb-btn {
  background: none; border: 1px solid #c9845e; color: #c9845e;
  border-radius: 4px; padding: 2px 8px; font-size: 0.78em;
  cursor: pointer; margin-left: 8px; vertical-align: middle;
}
.fb-btn:hover { background: #c9845e; color: #fff; }
.fb-form {
  display: none; background: #fff; border: 1px solid #ddd;
  border-radius: 6px; padding: 12px; margin: 8px 0;
}
.fb-form.open { display: block; }
.fb-form select, .fb-form textarea {
  width: 100%; padding: 6px 8px; border: 1px solid #ccc;
  border-radius: 4px; font-family: inherit; font-size: 0.9em;
  margin-top: 4px;
}
.fb-form textarea { min-height: 60px; resize: vertical; }
.fb-form label { font-size: 0.85em; font-weight: 600; color: #555; display: block; margin-top: 8px; }
.fb-form .fb-actions { margin-top: 8px; display: flex; gap: 8px; }
.fb-form .fb-save {
  background: #2a6b5e; color: #fff; border: none; border-radius: 4px;
  padding: 5px 14px; cursor: pointer; font-size: 0.85em;
}
.fb-form .fb-cancel {
  background: none; border: 1px solid #ccc; border-radius: 4px;
  padding: 5px 14px; cursor: pointer; font-size: 0.85em; color: #666;
}
.fb-item {
  background: #fdf6ef; border-left: 3px solid #c9845e;
  padding: 8px 12px; margin: 6px 0; border-radius: 0 4px 4px 0;
  font-size: 0.88em; position: relative;
}
.fb-item .fb-type { font-weight: 600; color: #c9845e; text-transform: uppercase; font-size: 0.8em; }
.fb-item .fb-remove {
  position: absolute; top: 6px; right: 8px; background: none;
  border: none; color: #999; cursor: pointer; font-size: 1.1em;
}
.fb-item .fb-remove:hover { color: #c00; }
/* Reviewer form */
.reviewer-section {
  background: #fff; border: 1px solid #2a6b5e; border-radius: 8px;
  padding: 20px; margin-top: 32px;
}
.reviewer-section h2 { border: none; margin-top: 0; }
.reviewer-section input, .reviewer-section select {
  width: 100%; padding: 8px 10px; border: 1px solid #ccc;
  border-radius: 4px; font-family: inherit; font-size: 0.95em; margin-top: 4px;
}
.reviewer-section label { display: block; margin-top: 12px; font-weight: 600; color: #555; font-size: 0.9em; }
.save-btn {
  display: block; width: 100%; margin-top: 20px; padding: 12px;
  background: #2a6b5e; color: #fff; border: none; border-radius: 6px;
  font-size: 1.05em; font-weight: 600; cursor: pointer;
}
.save-btn:hover { background: #1f5349; }
.save-btn:disabled { background: #999; cursor: not-allowed; }
.status-bar {
  position: fixed; bottom: 0; left: 0; right: 0; background: #2a6b5e;
  color: #fff; padding: 8px 16px; font-size: 0.85em; text-align: center;
  z-index: 100;
}
.count-badge {
  display: inline-block; background: #c9845e; color: #fff;
  border-radius: 10px; padding: 1px 8px; font-size: 0.8em; margin-left: 4px;
}
@media print {
  .fb-btn, .fb-form, .reviewer-section, .save-btn, .status-bar,
  .noscript-banner { display: none !important; }
  body { background: #fff; max-width: none; padding: 0; }
  h2 { page-break-after: avoid; }
}
"""

# ---------------------------------------------------------------------------
# JavaScript
# ---------------------------------------------------------------------------

_JS = """\
(function() {
  'use strict';
  var feedbackItems = [];
  var counter = 0;

  function addFeedbackForm(targetId, parentEl) {
    var form = document.createElement('div');
    form.className = 'fb-form open';
    form.innerHTML =
      '<label>Type' +
      '<select class="fb-type-sel">' +
      '<option value="challenge">Challenge</option>' +
      '<option value="question">Question</option>' +
      '<option value="signoff">Sign-off</option>' +
      '</select></label>' +
      '<label>Feedback<textarea class="fb-text" placeholder="Enter your feedback..."></textarea></label>' +
      '<div class="fb-actions">' +
      '<button type="button" class="fb-save">Add</button>' +
      '<button type="button" class="fb-cancel">Cancel</button>' +
      '</div>';
    parentEl.appendChild(form);

    form.querySelector('.fb-save').addEventListener('click', function() {
      var text = form.querySelector('.fb-text').value.trim();
      if (!text) { form.querySelector('.fb-text').focus(); return; }
      var type = form.querySelector('.fb-type-sel').value;
      var item = { target_id: targetId, feedback_type: type, text: text };
      feedbackItems.push(item);
      renderFeedbackItem(item, parentEl);
      form.remove();
      updateStatusBar();
    });

    form.querySelector('.fb-cancel').addEventListener('click', function() {
      form.remove();
    });

    form.querySelector('.fb-text').focus();
  }

  function renderFeedbackItem(item, parentEl) {
    var div = document.createElement('div');
    div.className = 'fb-item';
    div.innerHTML =
      '<span class="fb-type">' + escHtml(item.feedback_type) + '</span> ' +
      escHtml(item.text) +
      '<button class="fb-remove" title="Remove">&times;</button>';
    div.querySelector('.fb-remove').addEventListener('click', function() {
      var idx = feedbackItems.indexOf(item);
      if (idx >= 0) feedbackItems.splice(idx, 1);
      div.remove();
      updateStatusBar();
    });
    parentEl.appendChild(div);
  }

  function escHtml(s) {
    var d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
  }

  function updateStatusBar() {
    var bar = document.getElementById('status-bar');
    if (!bar) return;
    var c = feedbackItems.filter(function(i) { return i.feedback_type === 'challenge'; }).length;
    var q = feedbackItems.filter(function(i) { return i.feedback_type === 'question'; }).length;
    var s = feedbackItems.filter(function(i) { return i.feedback_type === 'signoff'; }).length;
    bar.textContent = 'Feedback: ' + c + ' challenge(s), ' + q + ' question(s), ' + s + ' sign-off(s)';
  }

  // Wire up all feedback buttons
  document.addEventListener('DOMContentLoaded', function() {
    // Per-element buttons
    document.querySelectorAll('.fb-btn').forEach(function(btn) {
      btn.addEventListener('click', function() {
        var targetId = btn.getAttribute('data-target') || null;
        var container = btn.closest('tr') || btn.closest('li') || btn.parentElement;
        addFeedbackForm(targetId, container);
      });
    });

    // Project-level button
    var projBtn = document.getElementById('project-feedback-btn');
    if (projBtn) {
      projBtn.addEventListener('click', function() {
        addFeedbackForm(null, document.getElementById('project-feedback-area'));
      });
    }

    // Save button
    var saveBtn = document.getElementById('save-review-btn');
    if (saveBtn) {
      saveBtn.addEventListener('click', saveReview);
    }

    updateStatusBar();
  });

  function saveReview() {
    var nameEl = document.getElementById('reviewer-name');
    var emailEl = document.getElementById('reviewer-email');
    var roleEl = document.getElementById('reviewer-role');

    if (!nameEl || !nameEl.value.trim()) {
      alert('Please enter your name before saving.');
      if (nameEl) nameEl.focus();
      return;
    }

    // Update the manifest
    var manifestEl = document.getElementById('review-manifest');
    var manifest = JSON.parse(manifestEl.textContent);
    manifest.reviewer = {
      name: nameEl.value.trim(),
      email: emailEl ? emailEl.value.trim() || null : null,
      role: roleEl ? roleEl.value.trim() || 'Reviewer' : 'Reviewer'
    };
    manifest.items = feedbackItems;
    manifest.completed_at = new Date().toISOString();
    manifestEl.textContent = JSON.stringify(manifest, null, 2);

    // Download the HTML
    var blob = new Blob(
      ['<!DOCTYPE html>\\n' + document.documentElement.outerHTML],
      { type: 'text/html' }
    );
    var a = document.createElement('a');
    var reviewer = nameEl.value.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-');
    a.download = 'review-' + manifest.project_name + '-' + reviewer + '.html';
    a.href = URL.createObjectURL(blob);
    a.click();
    URL.revokeObjectURL(a.href);

    // Visual confirmation
    var saveBtn = document.getElementById('save-review-btn');
    if (saveBtn) {
      saveBtn.textContent = 'Saved! Send this file back to the model owner.';
      saveBtn.disabled = true;
    }
  }
})();
"""


# ---------------------------------------------------------------------------
# HTML builder
# ---------------------------------------------------------------------------


def _feedback_btn(element_id: str | None) -> str:
    """Render an inline feedback button for a model element."""
    data = f' data-target="{_h(element_id)}"' if element_id else ""
    return f'<button class="fb-btn"{data}>+ Feedback</button>'


def render(
    paths: ProjectPaths,
    *,
    pack: str = "review",
    sections: list[str] | None = None,
    model_type: str | None = None,
) -> str:
    """Build the self-contained HTML review document.

    When ``model_type`` is given the pack is scoped to that formalism: the
    substrate (and therefore the diagram and feedback targets), findings, and
    interpretation are filtered to that formalism's view. The session/manifest
    record the formalism. ``model_type=None`` exports the whole project."""
    from latris.exporters._scope import view_member_ids

    included = None
    if sections:
        included = set(sections)
    elif pack:
        included = set(get_pack(pack).sections)

    def _include(section: str) -> bool:
        return included is None or section in included

    # Load project data (mirrors word.py loading pattern)
    foundation = load_model(ProjectFoundation, paths.project_yaml)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    members = view_member_ids(paths, model_type)
    if members is not None:
        substrate.entities = [e for e in substrate.entities if e.id in members]
        substrate.edges = [e for e in substrate.edges if e.id in members]
    descriptions = {(e.target_id, e.attribute): e for e in load_model(DescriptionSet, paths.descriptions_yaml).entries}
    confidence = {(e.target_id, e.attribute): e for e in load_model(ConfidenceSet, paths.confidence_yaml).entries}
    pol_path = paths.view_attribute_path("cld", "polarity")
    pol_set = load_model(PolaritySet, pol_path) if pol_path.exists() else PolaritySet()
    polarity = {(e.target_id, e.attribute): e for e in pol_set.entries}
    evidence = load_model(EvidenceLinkSet, paths.evidence_links_yaml)
    references = load_model(ReferenceLibrary, paths.references_yaml).entries
    assumptions = load_model(AssumptionLog, paths.assumptions_yaml).entries
    questions = load_model(QuestionLog, paths.questions_yaml).entries
    challenges = load_model(ChallengeLog, paths.challenges_yaml).entries

    labels = {n.id: n.label for n in substrate.entities}

    # Build element_ids map for the manifest
    element_ids: dict[str, str] = {}
    for n in substrate.entities:
        element_ids[n.id] = n.label
    for e in substrate.edges:
        src = labels.get(e.from_id, e.from_id[:12])
        dst = labels.get(e.to_id, e.to_id[:12])
        element_ids[e.id] = f"{src} -> {dst}"

    # Build manifest
    try:
        commit_sha = head_sha(paths.root)
    except Exception:
        commit_sha = "unknown"

    try:
        from latris.repo.git import ensure_identity

        name, email = ensure_identity(paths.root)
        exporter = HumanActor(name=name, email=email)
    except Exception:
        exporter = HumanActor(name="Unknown")

    session_id = new_id("review-session")
    now = datetime.now(UTC)
    manifest = ReviewManifest(
        review_session_id=session_id,
        project_name=foundation.name or paths.root.name,
        export_commit_sha=commit_sha,
        exported_at=now,
        exported_by=exporter,
        pack=pack or "all",
        model_type=model_type or "",
        sections=list(included) if included else [],
        element_ids=element_ids,
    )
    manifest_json = manifest.model_dump_json(indent=2)

    # SVG diagram — scoped to the formalism's view when one is given.
    svg_content = render_svg(paths, view=model_type or "system_map")
    if svg_content:
        diagram_html = f'<div class="diagram-container">{svg_content}</div>'
    else:
        # Text fallback
        lines = []
        for edge in substrate.edges:
            src = labels.get(edge.from_id, edge.from_id[:12])
            dst = labels.get(edge.to_id, edge.to_id[:12])
            lines.append(f"<li>{_h(src)} &rarr; {_h(dst)} ({_h(edge.kind)})</li>")
        if lines:
            diagram_html = '<div class="diagram-container"><ul>' + "\n".join(lines) + "</ul></div>"
        else:
            diagram_html = '<p class="empty">No model structure to display.</p>'

    # Build sections
    body_parts: list[str] = []

    # Foundation
    if _include("foundation"):
        body_parts.append("<h2>Foundation</h2>")
        body_parts.append(f"<p><strong>Modelling question:</strong> {_h(foundation.statement)}</p>")
        if foundation.boundary:
            body_parts.append(f"<p><strong>Boundary:</strong> {_h(foundation.boundary)}</p>")

    # Diagram (always included if nodes exist)
    if substrate.entities:
        body_parts.append("<h2>Model Diagram</h2>")
        body_parts.append(diagram_html)

    # Nodes
    if _include("nodes"):
        body_parts.append("<h2>Nodes</h2>")
        if substrate.entities:
            rows = []
            for n in substrate.entities:
                desc = descriptions.get((n.id, "description"))
                conf = confidence.get((n.id, "confidence"))
                rows.append(
                    f'<tr data-element-id="{_h(n.id)}">'
                    f"<td>{_h(n.label)}</td>"
                    f"<td>{_h(n.kind)}</td>"
                    f"<td>{_h(desc.value if desc else '')}</td>"
                    f"<td>{_h(conf.value if conf else '')}</td>"
                    f"<td>{_feedback_btn(n.id)}</td>"
                    f"</tr>"
                )
            body_parts.append(
                "<table><thead><tr>"
                "<th>Label</th><th>Kind</th><th>Description</th>"
                "<th>Confidence</th><th>Review</th>"
                "</tr></thead><tbody>" + "\n".join(rows) + "</tbody></table>"
            )
        else:
            body_parts.append('<p class="empty">No nodes.</p>')

    # Edges
    if _include("edges"):
        body_parts.append("<h2>Edges</h2>")
        if substrate.edges:
            rows = []
            for e in substrate.edges:
                src = labels.get(e.from_id, e.from_id[:12])
                dst = labels.get(e.to_id, e.to_id[:12])
                pol = polarity.get((e.id, "polarity"))
                conf = confidence.get((e.id, "confidence"))
                rows.append(
                    f'<tr data-element-id="{_h(e.id)}">'
                    f"<td>{_h(src)} &rarr; {_h(dst)}</td>"
                    f"<td>{_h(e.kind)}</td>"
                    f"<td>{_h(pol.value if pol else '')}</td>"
                    f"<td>{_h(conf.value if conf else '')}</td>"
                    f"<td>{_feedback_btn(e.id)}</td>"
                    f"</tr>"
                )
            body_parts.append(
                "<table><thead><tr>"
                "<th>From &rarr; To</th><th>Kind</th><th>Polarity</th>"
                "<th>Confidence</th><th>Review</th>"
                "</tr></thead><tbody>" + "\n".join(rows) + "</tbody></table>"
            )
        else:
            body_parts.append('<p class="empty">No edges.</p>')

    # Evidence
    if _include("evidence"):
        body_parts.append("<h2>Evidence</h2>")
        if evidence.entries:
            rows = []
            for link in evidence.entries:
                target_label = labels.get(link.target_id, link.target_id) if link.target_id else "Model"
                rows.append(
                    f'<tr data-element-id="{_h(link.target_id or "")}">'
                    f"<td>{_h(target_label)}</td>"
                    f"<td>{_h(link.attribute)}</td>"
                    f"<td>{_h(link.bibkey)}</td>"
                    f"<td>{_h(link.notes or '')}</td>"
                    f"</tr>"
                )
            body_parts.append(
                "<table><thead><tr>"
                "<th>Target</th><th>Attribute</th><th>Reference</th><th>Notes</th>"
                "</tr></thead><tbody>" + "\n".join(rows) + "</tbody></table>"
            )
        else:
            body_parts.append('<p class="empty">No evidence attached.</p>')

    # Challenges
    if _include("challenges"):
        body_parts.append("<h2>Challenges</h2>")
        if challenges:
            items = []
            for c in challenges:
                target = labels.get(c.target_id, c.target_id) if c.target_id else "Project"
                items.append(
                    f'<li data-element-id="{_h(c.id)}">'
                    f"<strong>[{_h(c.state)}]</strong> {_h(c.argument)} "
                    f"(target: {_h(target)}, by {_h(_actor_name(c.opened_by))})"
                    f"</li>"
                )
            body_parts.append('<ul class="prov">' + "\n".join(items) + "</ul>")
        else:
            body_parts.append('<p class="empty">No challenges.</p>')

    # Questions
    if _include("questions"):
        open_qs = [q for q in questions if q.disposition == "open"]
        body_parts.append("<h2>Open Questions</h2>")
        if open_qs:
            items = []
            for q in open_qs:
                items.append(
                    f'<li data-element-id="{_h(q.id)}">'
                    f"{_h(q.question)} "
                    f"(by {_h(_actor_name(q.raised_by))}, {id_timestamp(q.id).date().isoformat()})"
                    f"</li>"
                )
            body_parts.append('<ul class="prov">' + "\n".join(items) + "</ul>")
        else:
            body_parts.append('<p class="empty">No open questions.</p>')

    # Findings
    if _include("findings"):
        from latris.repo.yaml_io import iter_jsonl
        from latris.schema.findings import Finding

        all_findings = list(iter_jsonl(Finding, paths.findings_jsonl))
        if model_type is not None:
            all_findings = [f for f in all_findings if f.model_type == model_type]
        body_parts.append("<h2>Findings</h2>")
        if all_findings:
            items = []
            for f in all_findings:
                items.append(
                    f'<li data-element-id="{_h(f.id)}"><strong>[{_h(f.category)}]</strong> {_h(f.statement)}</li>'
                )
            body_parts.append('<ul class="prov">' + "\n".join(items) + "</ul>")
        else:
            body_parts.append('<p class="empty">No findings.</p>')

    # Assumptions
    if _include("assumptions"):
        body_parts.append("<h2>Assumptions</h2>")
        if assumptions:
            items = []
            for a in assumptions:
                items.append(
                    f"<li>{_h(a.statement)}"
                    f" &mdash; by {_h(_actor_name(a.authored_by))}, "
                    f"{id_timestamp(a.id).date().isoformat()}</li>"
                )
            body_parts.append('<ul class="prov">' + "\n".join(items) + "</ul>")
        else:
            body_parts.append('<p class="empty">No assumptions.</p>')

    # Interpretation (Answer / Confidence / Limitations / etc.)
    if _include("interpretation"):
        from latris.operations.interpret_registry import (
            INTERPRET_SECTION_REGISTRY,
            get_section_spec,
        )
        from latris.schema.interpretation import InterpretationStore

        interp_path = paths.interpretation_yaml
        if interp_path.exists():
            store = load_model(InterpretationStore, interp_path)
            scoped = [s for s in store.sections if model_type is None or s.model_type == model_type]
            if scoped:
                body_parts.append("<h2>Interpretation</h2>")
                section_order = list(INTERPRET_SECTION_REGISTRY.keys())
                by_type: dict[str, list] = {}
                for s in scoped:
                    by_type.setdefault(s.section_type, []).append(s)
                for section_type in section_order:
                    for s in by_type.get(section_type, []):
                        try:
                            title = get_section_spec(s.section_type).display_name
                        except ValueError:
                            title = s.section_type.replace("_", " ").title()
                        # Disambiguate by model only in the unscoped (aggregate) pack.
                        suffix = "" if model_type is not None else f" ({s.model_type.upper()})"
                        body_parts.append(f'<h3>{_h(title)}{_h(suffix)}</h3>')
                        if s.prose:
                            # Render prose with paragraph breaks but escape HTML
                            paragraphs = [
                                f"<p>{_h(p)}</p>"
                                for p in s.prose.split("\n\n")
                                if p.strip()
                            ]
                            body_parts.append("\n".join(paragraphs))
                        else:
                            body_parts.append('<p class="empty">No prose generated yet.</p>')
                        if s.claims:
                            body_parts.append("<details><summary>Claims (from analysis)</summary>")
                            body_parts.append('<ul class="prov">')
                            for c in s.claims:
                                body_parts.append(f"<li>{_h(c)}</li>")
                            body_parts.append("</ul></details>")

    # References
    if _include("references"):
        body_parts.append("<h2>References</h2>")
        if references:
            items = []
            for r in references:
                authors = ", ".join(r.authors) if r.authors else "Unknown"
                items.append(
                    f"<li><strong>{_h(r.bibkey)}</strong>: "
                    f"{_h(authors)} ({r.year or 'n.d.'}). "
                    f"<em>{_h(r.title)}</em></li>"
                )
            body_parts.append('<ul class="prov">' + "\n".join(items) + "</ul>")
        else:
            body_parts.append('<p class="empty">No references.</p>')

    # Assemble final HTML
    body_content = "\n".join(body_parts)
    export_date = now.strftime("%d %B %Y")
    project_name = _h(foundation.name or paths.root.name)

    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Review: {project_name}</title>
<style>
{_CSS}
</style>
</head>
<body>

<noscript>
<div class="noscript-banner">
<strong>JavaScript is required for the review form.</strong>
If your email system stripped the scripts, save this file to disk and
open it directly in your browser, or ask the sender to provide it as
a .zip file. You can still read the report content below.
</div>
</noscript>

<h1>Review Pack: {project_name}</h1>
<div class="meta">
Exported {export_date} by {_h(_actor_name(exporter))}<br>
Model version: <code>{_h(commit_sha[:12])}</code>
</div>

{body_content}

<!-- Project-level feedback -->
<h2>Project-Level Feedback</h2>
<p>Use this section for feedback about the model as a whole.</p>
<div id="project-feedback-area">
<button id="project-feedback-btn" class="fb-btn" style="margin-left:0">+ Add project-level feedback</button>
</div>

<!-- Reviewer identity -->
<div class="reviewer-section">
<h2>Your Details</h2>
<label>Name (required)
<input type="text" id="reviewer-name" placeholder="Your full name">
</label>
<label>Email
<input type="email" id="reviewer-email" placeholder="your@email.com">
</label>
<label>Role
<input type="text" id="reviewer-role" value="Reviewer" placeholder="e.g. Domain Expert, Auditor, Client">
</label>
<button id="save-review-btn" class="save-btn">Save Review</button>
<p style="margin-top:8px;font-size:0.85em;color:#666">
Clicking Save will download an annotated copy of this file.
Send it back to the model owner.
</p>
</div>

<div id="status-bar" class="status-bar">Feedback: 0 challenge(s), 0 question(s), 0 sign-off(s)</div>

<script type="application/json" id="review-manifest">
{manifest_json}
</script>
<script>
{_JS}
</script>

</body>
</html>"""
