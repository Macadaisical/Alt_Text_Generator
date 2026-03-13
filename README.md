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

## Configuration

The CLI loads credentials from the repo-root `.env` file and currently expects:

- `WP_SITE_URL`
- `WP_USERNAME`
- `WP_APP_PASSWORD`

## Current Scope

- `auth-check`: read-only WordPress REST auth verification
- `discover`: read-only image attachment discovery
- `context-report`: read-only attachment-to-content matching using rendered post/page content

Write-back and AI-generated suggestion flows are intentionally not implemented yet.
