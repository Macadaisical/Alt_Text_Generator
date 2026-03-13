# Project Memory

## Purpose
- Preserve stable project context between sessions so future work does not require a full repo re-scan.

## Session Instructions
1. Read `status.md` first at the start of every session.
2. Read this file second for durable context and standing decisions.
3. Read the `Tasks` section in `status.md`, select the next incomplete task, and implement only that task.
4. During the session, update `status.md` with progress, attempts, blockers, and next actions.
5. During the session, update this file only with durable information that should survive across sessions.
6. Before ending the session, make sure both files reflect the current state.

## Current Durable Decisions
- This project is a greenfield build as of 2026-03-12.
- The preferred first milestone is an external review-first script rather than a WordPress plugin.
- Python is now the favored implementation language because the repo already contains a Python integration script and shared environment-loading pattern.
- Python is the confirmed implementation language for the first build.
- The repository now contains a packaged Python CLI scaffold with `wp-alt-text auth-check` and `wp-alt-text discover`.
- The CLI now also includes `wp-alt-text context-report`, which scans published `posts` and `pages` and maps attachments to likely front-end usage via attachment ID and source URL matching in rendered content.
- `wp-alt-text context-report` now also fetches public page HTML and matches against both REST-rendered content and front-end markup, which is important for Elementor-heavy pages.
- The first production-safe mode should be `dry-run` by default.
- Human review must remain part of the workflow because alt text correctness depends on context and image role.
- The initial targeting scope now includes both missing alt text and weak existing alt text.
- The target site uses Elementor.
- Until a better deployment need emerges, the default operating assumption is a local runner rather than CI or a server-side deployment.

## Product Intent
- Scan a WordPress site for image attachments and likely front-end usage.
- Generate candidate alt text that is context-aware rather than pure visual captioning.
- Support approval, editing, skip, and bulk operations.
- Write approved alt text back to WordPress safely with logs and reversibility.

## Non-Negotiable Requirements
- Maintain `status.md` and `memory.md` every session.
- Use official or primary documentation when making technical or compliance-sensitive decisions.
- Keep an audit trail for generated and written alt text.
- Avoid bulk writes without a review path or explicit overwrite mode.

## Architecture Bias
- Short term: external script/app.
- Long term: possibly hybrid, with external worker plus lightweight WordPress plugin/admin UI.

## Technical Notes
- `.env` already contains `WP_SITE_URL`, `WP_USERNAME`, `WP_APP_PASSWORD`, and FTP credentials.
- `assets/upload_via_ftp.py` already uses `python-dotenv` and a repo-root `.env`, which should be mirrored by the alt-text tool for consistency.
- GitHub remote `origin` points to `https://github.com/Macadaisical/Alt_Text_Generator.git`, and the local branch now tracks `origin/main`.
- The configured `WP_SITE_URL` uses `www`, but the site canonicalizes to the non-`www` host. Authenticated REST calls must resolve the canonical REST root first or Basic Auth may be lost across the redirect.
- The media endpoint on this site is safer when discovery requests use `_fields` to limit the response payload to only required fields.
- `--missing-alt-only` now scans forward across REST media pages until it accumulates the requested number of missing-alt attachments, instead of filtering only the first fetched page.
- WordPress REST API media endpoint includes `alt_text` and supports update operations.
- WordPress core attachment alt text is tied to `_wp_attachment_image_alt`.
- Front-end behavior may vary because some pages/builders may store literal `<img alt="...">` markup in content instead of relying on attachment metadata at render time.
- Elementor is confirmed on the target site, so usage-context discovery should assume builder-managed markup and metadata may need special handling.
- For large media libraries, async batching is desirable to control cost and throughput.
- Current context mapping heuristics are read-only and conservative: they look for `wp-image-<id>`, attachment-related data attributes/classes, and direct source URL references inside rendered content.
- Current context mapping heuristics are read-only and conservative: they look for `wp-image-<id>`, attachment-related data attributes/classes, and direct source URL references inside both rendered content and fetched public HTML.

## Accessibility Notes
- WCAG 2.2 non-text content requirements apply.
- Good alt text depends on context, function, and whether the image is decorative, informative, functional, or complex.
- Decorative images may require empty alt text, not descriptive text.
- Images containing text may need transcription of the text.

## Likely First Build
- Python CLI tool.
- Input: WordPress base URL, auth credentials, optional filters.
- Output: report file plus optional approved write-back.
- Modes:
  - `discover`
  - `suggest`
  - `review`
  - `apply`

## Verified Commands
- `wp-alt-text auth-check` succeeds against the configured site.
- `wp-alt-text discover --per-page 5` succeeds against the configured site.
- `wp-alt-text discover --per-page 5 --missing-alt-only` succeeds and currently surfaces at least one Elementor screenshot attachment without alt text.
- `wp-alt-text context-report --per-page 2 --max-content-pages 1` succeeds and scans published post/page content for likely attachment usage matches.
- `wp-alt-text discover --per-page 3 --missing-alt-only` succeeds and currently finds missing-alt attachments after scanning forward to later media pages.
- `wp-alt-text context-report --per-page 1 --missing-alt-only --content-per-page 5 --max-content-pages 1` succeeds and fetches public HTML for scanned content items.

## Known Unknowns
- Builder/theme landscape on the target site.
- Desired review UX: CSV, JSONL, local HTML report, or admin UI later.
- Whether multilingual content is in scope.
