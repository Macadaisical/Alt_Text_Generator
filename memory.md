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
- The CLI now also includes `wp-alt-text review-report`, which exports the current media/context scan into `review-report.jsonl` and `review-report.csv` for downstream review, suggestion, and apply stages.
- The CLI now also includes `wp-alt-text prompt-spec`, which exposes the current alt-text decision rules and reusable prompt templates without needing live WordPress access.
- The CLI now also includes `wp-alt-text suggest`, which reads exported review-report JSONL records, sends image URL plus usage context to the OpenAI Responses API, and writes suggestion-enriched JSONL + CSV artifacts without changing WordPress.
- The CLI now also includes `wp-alt-text review`, which records reviewer `approve`, `edit`, and `skip` decisions into exported review-report JSONL records and writes reviewed JSONL + CSV artifacts without changing WordPress.
- The CLI now also includes `wp-alt-text apply`, which consumes reviewed artifacts, marks dry-run or applied outcomes in the `apply` section, and only performs live WordPress updates when `--commit` is supplied.
- The CLI now also supports `wp-alt-text apply --auto-apply-high-confidence`, which auto-approves only narrow eligible suggestions into the normal review/apply audit trail and still defaults to dry-run.
- The CLI now also includes `wp-alt-text review-html`, which renders exported `review-report.jsonl` artifacts into a local static HTML review app for browser-based review and JSONL export.
- The CLI now also includes `wp-alt-text review-import`, which validates a browser-exported reviewed JSONL file and rewrites it into a managed JSONL + CSV artifact directory for later apply steps.
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
- The report schema is intentionally forward-compatible: each JSONL record already reserves `suggestion`, `review`, and `apply` sections so later workflow stages can update the same artifact family rather than inventing a new format.
- Prompting is now versioned via `PROMPT_VERSION`, with an explicit role order of decorative, functional, text-heavy, complex, then informative.
- The prompt contract expects structured output fields for role, suggested alt text, confidence, manual-review flag, long-description flag, rationale, and warnings.
- Suggestion generation is now artifact-first rather than live-site-first: it operates on exported `review-report.jsonl` files so discovery/context scans and model generation stay decoupled.
- Review decisions are also artifact-first: the `review` stage updates the existing `review` section in copied report artifacts so the later apply stage can consume reviewer-approved records without re-scanning WordPress.
- Apply is dry-run first by default: it only targets records whose review status is `reviewed` and whose action is `approve` or `edit`, and it writes a new artifact family whether or not live updates are committed.
- Live write verification is now explicit in the client: after a media alt-text update, the tool performs a follow-up read and only treats the apply as successful if the confirmed `alt_text` matches the requested value.
- This site can return stale `alt_text` values immediately after a successful update; the client now retries read-after-write verification briefly before marking an apply as failed.
- Manual-review policy is enforced in code, not left to the model alone: `decorative`, `functional`, `text_heavy`, and `complex` suggestions are always marked `requires_manual_review`.
- Auto-approval policy is intentionally narrow: only high-confidence `informative` suggestions with no warnings, no manual-review requirement, no long-description requirement, and non-empty candidate alt text are eligible.
- The intended write-back behavior is selective, not bulk by default: only reviewer-approved records should be applied to WordPress.
- Higher-risk suggestion types such as decorative, functional, text-heavy, and complex should remain in the manual-review path by default.
- Any future automatic apply mode should be explicitly opt-in and limited to high-confidence suggestions after the approval/apply workflow is stable.

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
- `wp-alt-text review-report --per-page 2 --missing-alt-only --content-per-page 5 --max-content-pages 1 --output-dir reports/smoke` succeeds and writes JSONL + CSV review artifacts.
- `wp-alt-text prompt-spec --json` succeeds locally without WordPress credentials.
- `wp-alt-text prompt-spec --review-record reports/smoke/review-report.jsonl` succeeds and renders example model messages from an exported review record.
- `wp-alt-text review --input-report reports/suggested/review-report.jsonl --output-dir reports/review-smoke --attachment-ids 11111 --action approve --reviewer 'TJ' --notes 'smoke test'` succeeds locally and writes reviewed JSONL + CSV artifacts.
- `wp-alt-text apply --input-report reports/review-smoke/review-report.jsonl --output-dir reports/apply-smoke --attachment-ids 11111` succeeds locally in dry-run mode and writes post-apply JSONL + CSV artifacts.
- `python3 -m unittest discover -s tests -v` succeeds locally and currently covers auto-review and dry-run apply policy behavior.
- `wp-alt-text apply --input-report reports/suggested/review-report.jsonl --output-dir reports/live-commit-trial --attachment-ids 10969 10973 --auto-apply-high-confidence --commit` succeeded against the live site, and follow-up reads confirmed the expected alt text values on attachment IDs `10969` and `10973`.
- `wp-alt-text review-html --input-report reports/suggested/review-report.jsonl --output-path reports/review-ui/review-report.html` succeeds locally and writes a browser-openable review app for the current artifact set.
- `wp-alt-text review-import --input-report reports/review-ui/review-report-reviewed.jsonl --output-dir reports/reviewed-import-smoke` succeeds locally and rewrites normalized JSONL + CSV reviewed artifacts.

## Known Unknowns
- Builder/theme landscape on the target site.
- Desired review UX: CSV, JSONL, local HTML report, or admin UI later.
- Whether multilingual content is in scope.
