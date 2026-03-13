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

Write-back is intentionally not implemented yet.
