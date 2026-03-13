# WordPress Alt Text Generator

Initial scaffold for a review-first CLI that discovers WordPress images and prepares an alt-text workflow.

## Commands

Install locally:

```bash
python3 -m pip install -e .
```

Verify WordPress REST authentication:

```bash
wp-alt-text auth-check
```

List image attachments:

```bash
wp-alt-text discover --per-page 20
```

List only images missing alt text as JSON:

```bash
wp-alt-text discover --missing-alt-only --json
```

When `--missing-alt-only` is used, the CLI scans forward across media pages until it collects up to the requested number of missing-alt attachments, and reports which source pages were scanned.

Generate a read-only context report by scanning published posts/pages for likely usage:

```bash
wp-alt-text context-report --per-page 20 --max-content-pages 2
```

`context-report` now scans both WordPress REST-rendered content and fetched public page HTML, which improves coverage for builder-driven pages such as Elementor.

Export a review-first report as JSONL plus CSV:

```bash
wp-alt-text review-report --missing-alt-only --per-page 20 --output-dir reports/latest
```

`review-report` writes:

- `review-report.jsonl`: full-fidelity records with media metadata, context matches, and placeholder `suggestion`, `review`, and `apply` states for later workflow stages.
- `review-report.csv`: spreadsheet-friendly queue with one row per attachment and the top matched context item.

Inspect the current decision rules and reusable prompt contract:

```bash
wp-alt-text prompt-spec --json
```

Preview the system prompt plus example messages from an exported review report:

```bash
wp-alt-text prompt-spec --review-record reports/latest/review-report.jsonl
```

Generate read-only alt-text suggestions from an exported review report:

```bash
wp-alt-text suggest --input-report reports/latest/review-report.jsonl --output-dir reports/suggested
```

The `suggest` command sends each review record's context plus the image URL to the OpenAI Responses API, records the model output back into the existing `suggestion` section, and writes a new JSONL + CSV artifact family without changing WordPress data.

High-risk suggestion types are policy-gated for manual review even if the model returns high confidence. The current manual-review defaults are `decorative`, `functional`, `text_heavy`, and `complex`.

Record reviewer decisions into a new reviewed artifact set:

```bash
wp-alt-text review --input-report reports/suggested/review-report.jsonl --attachment-ids 11111 --action approve --reviewer "TJ"
```

Use `--action edit --final-alt-text "..."` to override the model suggestion, or `--action skip` to mark a record as intentionally not approved for apply.

Generate a browser-based local review app from an exported report:

```bash
wp-alt-text review-html --input-report reports/suggested/review-report.jsonl --output-path reports/review-ui/review-report.html
```

`review-html` writes a static HTML file you can open locally to review image previews, inspect context, filter records, set approve/edit/skip decisions inline, and export an updated reviewed JSONL artifact for the next stage.

Import the browser-exported reviewed JSONL back into a managed artifact directory:

```bash
wp-alt-text review-import --input-report /path/to/review-report-reviewed.jsonl --output-dir reports/reviewed
```

`review-import` validates the reviewed JSONL structure, rewrites it as the canonical `review-report.jsonl`, and regenerates the matching CSV summary so the next `apply` step can use a normal managed artifact directory again.

Dry-run reviewer-approved writes back to WordPress:

```bash
wp-alt-text apply --input-report reports/reviewed/review-report.jsonl --all-approved
```

`apply` only targets records already marked `reviewed` with action `approve` or `edit`. It runs in dry-run mode by default and writes a new artifact set showing intended apply status and target alt text. Use `--commit` to perform live WordPress updates.

There is also an explicit opt-in automation path:

```bash
wp-alt-text apply --input-report reports/suggested/review-report.jsonl --auto-apply-high-confidence
```

That path still runs dry-run by default. It first auto-approves only eligible high-confidence suggestions, then feeds them through the normal apply stage and audit fields. Current policy keeps this narrow: only `informative` suggestions are auto-approvable, and only when they are high confidence, have no warnings, do not require manual review, do not need a long description, and have non-empty candidate alt text.

## Configuration

The CLI loads credentials from the repo-root `.env` file and currently expects:

- `WP_SITE_URL`
- `WP_USERNAME`
- `WP_APP_PASSWORD`
- `OPENAI_API_KEY` for `suggest`
- `OPENAI_MODEL` optional override for `suggest`

## Current Scope

- `auth-check`: read-only WordPress REST auth verification
- `discover`: read-only image attachment discovery
- `context-report`: read-only attachment-to-content matching using rendered post/page content
- `review-report`: read-only JSONL and CSV export for human review workflows
- `prompt-spec`: local inspection of alt-text role rules and prompt templates
- `suggest`: read-only model-backed suggestion generation against exported review reports
- `review`: records reviewer decisions such as approve, edit, and skip into a new artifact set
- `review-html`: generates a local browser-based review app from a review-report JSONL artifact
- `review-import`: imports a browser-edited reviewed JSONL file back into a managed JSONL + CSV artifact directory
- `apply`: dry-run-first write-back stage for reviewed approved/edit records

Live write-back is intentionally gated behind `wp-alt-text apply --commit`.
