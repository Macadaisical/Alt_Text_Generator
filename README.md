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

## Configuration

The CLI loads credentials from the repo-root `.env` file and currently expects:

- `WP_SITE_URL`
- `WP_USERNAME`
- `WP_APP_PASSWORD`

## Current Scope

- `auth-check`: read-only WordPress REST auth verification
- `discover`: read-only image attachment discovery

Write-back and AI-generated suggestion flows are intentionally not implemented yet.
