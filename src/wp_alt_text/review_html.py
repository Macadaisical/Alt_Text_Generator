from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REQUIRED_TOP_LEVEL_KEYS: tuple[str, ...] = (
    "attachment_id",
    "source_url",
    "suggestion",
    "review",
    "apply",
)


def write_review_html(*, output_path: Path, report_records: list[dict[str, Any]]) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    document = _build_document(report_records)
    output_path.write_text(document, encoding="utf-8", newline="\n")
    return output_path


def validate_review_records(report_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    validated_records: list[dict[str, Any]] = []
    for index, record in enumerate(report_records, start=1):
        missing = [key for key in REQUIRED_TOP_LEVEL_KEYS if key not in record]
        if missing:
            joined = ", ".join(missing)
            raise ValueError(f"Record {index} is missing required keys: {joined}")
        if not isinstance(record.get("suggestion"), dict):
            raise ValueError(f"Record {index} has non-object suggestion field")
        if not isinstance(record.get("review"), dict):
            raise ValueError(f"Record {index} has non-object review field")
        if not isinstance(record.get("apply"), dict):
            raise ValueError(f"Record {index} has non-object apply field")
        validated_records.append(record)
    if not validated_records:
        raise ValueError("No review records found")
    return validated_records


def _build_document(report_records: list[dict[str, Any]]) -> str:
    escaped_data = _json_for_script_tag(report_records)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Alt Text Review</title>
  <style>
    :root {{
      --bg: #f3efe6;
      --panel: #fffaf2;
      --panel-strong: #fffdf8;
      --ink: #182126;
      --muted: #59656d;
      --line: #d7cdbf;
      --accent: #006d77;
      --accent-soft: #d9f0ef;
      --warn: #a65b00;
      --warn-soft: #ffe6cc;
      --ok: #2f6b2f;
      --ok-soft: #dff0df;
      --skip: #6a4c93;
      --skip-soft: #ece2f8;
      --shadow: 0 14px 40px rgba(24, 33, 38, 0.08);
      --radius: 18px;
    }}

    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Georgia, "Times New Roman", serif;
      background:
        radial-gradient(circle at top left, rgba(0,109,119,0.12), transparent 28%),
        linear-gradient(180deg, #f9f4ea 0%, var(--bg) 100%);
      color: var(--ink);
    }}
    a {{ color: var(--accent); }}
    .shell {{
      max-width: 1400px;
      margin: 0 auto;
      padding: 28px 20px 40px;
    }}
    .hero {{
      background: linear-gradient(135deg, rgba(0,109,119,0.10), rgba(255,250,242,0.92));
      border: 1px solid var(--line);
      border-radius: 28px;
      box-shadow: var(--shadow);
      padding: 24px;
      margin-bottom: 22px;
    }}
    .hero h1 {{
      margin: 0 0 8px;
      font-size: clamp(2rem, 4vw, 3.6rem);
      line-height: 0.95;
      letter-spacing: -0.03em;
    }}
    .hero p {{
      margin: 0;
      max-width: 70ch;
      color: var(--muted);
      font-size: 1rem;
    }}
    .toolbar {{
      display: grid;
      grid-template-columns: 1.4fr 1fr 1fr 1fr auto;
      gap: 12px;
      background: rgba(255,253,248,0.94);
      position: sticky;
      top: 0;
      z-index: 5;
      padding: 14px;
      border: 1px solid var(--line);
      border-radius: 20px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(8px);
      margin-bottom: 18px;
    }}
    .toolbar label {{
      display: block;
      font-size: 0.78rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--muted);
      margin-bottom: 4px;
    }}
    .toolbar input, .toolbar select, .toolbar button, textarea {{
      width: 100%;
      border: 1px solid #b6aca1;
      border-radius: 12px;
      padding: 10px 12px;
      font: inherit;
      color: var(--ink);
      background: white;
    }}
    .toolbar button {{
      align-self: end;
      background: var(--accent);
      color: white;
      border: 0;
      cursor: pointer;
      font-weight: 600;
    }}
    .summary {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-bottom: 18px;
    }}
    .pill {{
      padding: 8px 12px;
      border-radius: 999px;
      background: var(--panel);
      border: 1px solid var(--line);
      color: var(--muted);
      font-size: 0.92rem;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
      gap: 18px;
    }}
    .card {{
      display: grid;
      grid-template-columns: 140px 1fr;
      gap: 16px;
      background: var(--panel-strong);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      padding: 16px;
    }}
    .thumb {{
      display: flex;
      flex-direction: column;
      gap: 10px;
    }}
    .thumb img {{
      width: 100%;
      aspect-ratio: 1 / 1;
      object-fit: cover;
      border-radius: 16px;
      border: 1px solid var(--line);
      background: #f8f4eb;
    }}
    .meta {{
      font-size: 0.84rem;
      color: var(--muted);
      word-break: break-word;
    }}
    .content h2 {{
      margin: 0 0 8px;
      font-size: 1.25rem;
      line-height: 1.05;
    }}
    .row {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 10px;
    }}
    .tag {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 6px 10px;
      border-radius: 999px;
      font-size: 0.78rem;
      border: 1px solid var(--line);
      background: #f7efe1;
    }}
    .tag.warn {{ background: var(--warn-soft); color: var(--warn); border-color: #f0ba80; }}
    .tag.ok {{ background: var(--ok-soft); color: var(--ok); border-color: #b6d6b6; }}
    .tag.skip {{ background: var(--skip-soft); color: var(--skip); border-color: #cdbde6; }}
    .section {{
      margin-top: 12px;
      padding-top: 12px;
      border-top: 1px dashed var(--line);
    }}
    .section h3 {{
      margin: 0 0 8px;
      font-size: 0.92rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--muted);
    }}
    .context-item {{
      padding: 10px 12px;
      border-radius: 12px;
      background: #f9f4ea;
      border: 1px solid #eadfce;
      margin-bottom: 8px;
    }}
    .context-item strong {{
      display: block;
      margin-bottom: 4px;
    }}
    textarea {{
      min-height: 88px;
      resize: vertical;
    }}
    .review-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
      margin-top: 10px;
    }}
    .full {{
      grid-column: 1 / -1;
    }}
    .empty {{
      padding: 24px;
      border: 1px dashed var(--line);
      border-radius: 18px;
      text-align: center;
      color: var(--muted);
      background: rgba(255,250,242,0.75);
    }}
    .status-bar {{
      margin-top: 16px;
      color: var(--muted);
      font-size: 0.92rem;
    }}
    @media (max-width: 860px) {{
      .toolbar {{ grid-template-columns: 1fr; }}
      .card {{ grid-template-columns: 1fr; }}
      .review-grid {{ grid-template-columns: 1fr; }}
      .thumb img {{ max-width: 200px; }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <section class="hero">
      <h1>Review Alt Text</h1>
      <p>Filter records, inspect image context, set approve/edit/skip decisions inline, then export an updated <code>review-report-reviewed.jsonl</code> without touching WordPress.</p>
    </section>

    <section class="toolbar">
      <div>
        <label for="search">Search</label>
        <input id="search" type="search" placeholder="Search title, alt text, context">
      </div>
      <div>
        <label for="review-filter">Review Status</label>
        <select id="review-filter">
          <option value="all">All</option>
          <option value="pending">Pending</option>
          <option value="reviewed">Reviewed</option>
        </select>
      </div>
      <div>
        <label for="type-filter">Candidate Type</label>
        <select id="type-filter">
          <option value="all">All</option>
        </select>
      </div>
      <div>
        <label for="manual-filter">Manual Review</label>
        <select id="manual-filter">
          <option value="all">All</option>
          <option value="true">Required</option>
          <option value="false">Not Required</option>
        </select>
      </div>
      <div>
        <label>&nbsp;</label>
        <button id="export-btn" type="button">Export Reviewed JSONL</button>
      </div>
    </section>

    <div class="summary" id="summary"></div>
    <div class="pill">Next step after export: run <code>wp-alt-text review-import --input-report /path/to/review-report-reviewed.jsonl --output-dir reports/reviewed</code></div>
    <div class="grid" id="cards"></div>
    <div class="empty" id="empty-state" hidden>No records match the current filters.</div>
    <div class="status-bar" id="status-bar"></div>
  </div>

  <script id="seed-data" type="application/json">{escaped_data}</script>
  <script>
    const records = JSON.parse(document.getElementById("seed-data").textContent);
    const state = {{
      search: "",
      reviewFilter: "all",
      typeFilter: "all",
      manualFilter: "all",
    }};

    const cardsEl = document.getElementById("cards");
    const emptyEl = document.getElementById("empty-state");
    const summaryEl = document.getElementById("summary");
    const statusBarEl = document.getElementById("status-bar");
    const typeFilterEl = document.getElementById("type-filter");

    init();

    function init() {{
      hydrateTypeOptions();
      bindToolbar();
      render();
    }}

    function hydrateTypeOptions() {{
      const types = Array.from(new Set(records.map((record) => record.suggestion?.candidate_type || "").filter(Boolean))).sort();
      for (const type of types) {{
        const option = document.createElement("option");
        option.value = type;
        option.textContent = type;
        typeFilterEl.appendChild(option);
      }}
    }}

    function bindToolbar() {{
      document.getElementById("search").addEventListener("input", (event) => {{
        state.search = event.target.value.trim().toLowerCase();
        render();
      }});
      document.getElementById("review-filter").addEventListener("change", (event) => {{
        state.reviewFilter = event.target.value;
        render();
      }});
      typeFilterEl.addEventListener("change", (event) => {{
        state.typeFilter = event.target.value;
        render();
      }});
      document.getElementById("manual-filter").addEventListener("change", (event) => {{
        state.manualFilter = event.target.value;
        render();
      }});
      document.getElementById("export-btn").addEventListener("click", exportJsonl);
    }}

    function filteredRecords() {{
      return records.filter((record) => {{
        const suggestion = record.suggestion || {{}};
        const review = record.review || {{}};
        const haystack = [
          record.attachment_title,
          record.current_alt_text,
          suggestion.candidate_alt_text,
          suggestion.rationale,
          ...(suggestion.warnings || []),
          ...(record.context_summary || []).flatMap((item) => [item.title, item.link, item.match_reason]),
        ].join(" ").toLowerCase();

        if (state.search && !haystack.includes(state.search)) {{
          return false;
        }}
        if (state.reviewFilter !== "all" && (review.status || "pending") !== state.reviewFilter) {{
          return false;
        }}
        if (state.typeFilter !== "all" && (suggestion.candidate_type || "") !== state.typeFilter) {{
          return false;
        }}
        if (state.manualFilter !== "all" && String(Boolean(suggestion.requires_manual_review)) !== state.manualFilter) {{
          return false;
        }}
        return true;
      }});
    }}

    function render() {{
      const visible = filteredRecords();
      renderSummary(visible);
      cardsEl.innerHTML = "";
      emptyEl.hidden = visible.length !== 0;
      for (const record of visible) {{
        cardsEl.appendChild(renderCard(record));
      }}
      statusBarEl.textContent = `${{visible.length}} visible record(s) of ${{records.length}} total. Exports include every record with your current in-browser edits.`;
    }}

    function renderSummary(visible) {{
      const reviewed = visible.filter((record) => (record.review?.status || "pending") === "reviewed").length;
      const manual = visible.filter((record) => Boolean(record.suggestion?.requires_manual_review)).length;
      const pending = visible.length - reviewed;
      summaryEl.innerHTML = "";
      [
        `Visible: ${{visible.length}}`,
        `Pending: ${{pending}}`,
        `Reviewed: ${{reviewed}}`,
        `Manual Review Required: ${{manual}}`,
      ].forEach((text) => {{
        const pill = document.createElement("div");
        pill.className = "pill";
        pill.textContent = text;
        summaryEl.appendChild(pill);
      }});
    }}

    function renderCard(record) {{
      const suggestion = record.suggestion || {{}};
      const review = record.review || {{}};
      const card = document.createElement("article");
      card.className = "card";

      const thumb = document.createElement("div");
      thumb.className = "thumb";
      thumb.innerHTML = `
        <img src="${{escapeHtml(record.source_url || "")}}" alt="">
        <div class="meta">
          <div><strong>ID:</strong> ${{record.attachment_id}}</div>
          <div><strong>Type:</strong> ${{escapeHtml(suggestion.candidate_type || "pending")}}</div>
          <div><strong>Confidence:</strong> ${{escapeHtml(suggestion.confidence || "n/a")}}</div>
          <div><strong>Usage:</strong> ${{record.usage_count || 0}}</div>
        </div>
      `;

      const content = document.createElement("div");
      content.className = "content";
      content.innerHTML = `
        <h2>${{escapeHtml(record.attachment_title || "(untitled)")}}</h2>
        <div class="row">
          ${{tagHtml(`Current Alt: ${{record.current_alt_text ? "Present" : "Missing"}}`, record.current_alt_text ? "ok" : "")}}
          ${{tagHtml(`Review: ${{review.status || "pending"}}`, review.status === "reviewed" ? "ok" : "")}}
          ${{tagHtml(`Manual Review: ${{suggestion.requires_manual_review ? "Yes" : "No"}}`, suggestion.requires_manual_review ? "warn" : "ok")}}
          ${{tagHtml(`Apply: ${{(record.apply || {{}}).status || "not_attempted"}}`, ((record.apply || {{}}).status || "") === "applied" ? "ok" : "")}}
        </div>
        <div class="section">
          <h3>Suggested Alt Text</h3>
          <div>${{escapeHtml(suggestion.candidate_alt_text || "(empty)")}}</div>
        </div>
        <div class="section">
          <h3>Rationale</h3>
          <div>${{escapeHtml(suggestion.rationale || "(none)")}}</div>
        </div>
        <div class="section">
          <h3>Warnings</h3>
          <div>${{(suggestion.warnings || []).length ? suggestion.warnings.map((warning) => `<div class="tag warn">${{escapeHtml(warning)}}</div>`).join(" ") : '<span class="meta">No warnings</span>'}}</div>
        </div>
        <div class="section">
          <h3>Context</h3>
          <div>${{renderContext(record.context_summary || [])}}</div>
        </div>
      `;

      const form = document.createElement("div");
      form.className = "section";
      form.innerHTML = `
        <h3>Review Decision</h3>
        <div class="review-grid">
          <div>
            <label>Action</label>
            <select data-field="action">
              <option value="">Pending</option>
              <option value="approve">Approve</option>
              <option value="edit">Edit</option>
              <option value="skip">Skip</option>
            </select>
          </div>
          <div>
            <label>Reviewer</label>
            <input data-field="reviewer" type="text" placeholder="Your name">
          </div>
          <div class="full">
            <label>Final Alt Text</label>
            <textarea data-field="final_alt_text" placeholder="Approve/edit alt text here"></textarea>
          </div>
          <div class="full">
            <label>Notes</label>
            <textarea data-field="notes" placeholder="Optional review notes"></textarea>
          </div>
        </div>
      `;

      seedForm(form, record);
      bindForm(form, record);
      content.appendChild(form);
      card.appendChild(thumb);
      card.appendChild(content);
      return card;
    }}

    function seedForm(form, record) {{
      const review = record.review || {{}};
      form.querySelector('[data-field="action"]').value = review.action || "";
      form.querySelector('[data-field="reviewer"]').value = review.reviewer || "";
      form.querySelector('[data-field="final_alt_text"]').value = review.final_alt_text || record.suggestion?.candidate_alt_text || "";
      form.querySelector('[data-field="notes"]').value = review.notes || "";
    }}

    function bindForm(form, record) {{
      form.querySelectorAll("[data-field]").forEach((element) => {{
        element.addEventListener("input", () => updateRecordFromForm(form, record));
        element.addEventListener("change", () => updateRecordFromForm(form, record));
      }});
    }}

    function updateRecordFromForm(form, record) {{
      const action = form.querySelector('[data-field="action"]').value;
      const reviewer = form.querySelector('[data-field="reviewer"]').value.trim();
      const finalAltText = form.querySelector('[data-field="final_alt_text"]').value;
      const notes = form.querySelector('[data-field="notes"]').value;

      if (!action) {{
        record.review = {{
          status: "pending",
          action: "",
          reviewer: reviewer,
          reviewed_at: "",
          notes: notes,
          final_alt_text: finalAltText,
        }};
      }} else {{
        record.review = {{
          status: "reviewed",
          action: action,
          reviewer: reviewer,
          reviewed_at: new Date().toISOString(),
          notes: notes,
          final_alt_text: action === "skip" ? "" : finalAltText,
        }};
      }}
      render();
    }}

    function renderContext(items) {{
      if (!items.length) {{
        return '<span class="meta">No matched context</span>';
      }}
      return items.slice(0, 3).map((item) => `
        <div class="context-item">
          <strong>${{escapeHtml(item.title || "(untitled)")}}</strong>
          <div class="meta">${{escapeHtml(item.content_type || "")}} · ${{escapeHtml(item.content_source || "")}} · ${{escapeHtml(item.match_reason || "")}}</div>
          <div><a href="${{escapeHtml(item.link || "#")}}" target="_blank" rel="noreferrer">Open context page</a></div>
        </div>
      `).join("");
    }}

    function exportJsonl() {{
      const lines = records.map((record) => JSON.stringify(record));
      const blob = new Blob([lines.join("\\n") + "\\n"], {{ type: "application/x-ndjson" }});
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "review-report-reviewed.jsonl";
      anchor.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    }}

    function tagHtml(text, cls) {{
      const className = cls ? `tag ${{cls}}` : "tag";
      return `<span class="${{className}}">${{escapeHtml(text)}}</span>`;
    }}

    function escapeHtml(value) {{
      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
    }}
  </script>
</body>
</html>
"""


def _json_for_script_tag(report_records: list[dict[str, Any]]) -> str:
    return (
        json.dumps(report_records, ensure_ascii=True)
        .replace("</", "<\\/")
        .replace("<!--", "<\\!--")
    )
