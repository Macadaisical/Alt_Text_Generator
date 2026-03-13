# Project Status

## Project
- Name: WordPress Alt Text Generator
- Goal: Scan a WordPress site for images, generate ADA/WCAG-aligned alt text suggestions, support review, and write approved alt text back to WordPress safely.
- Repository state: Greenfield as of 2026-03-12.

## Session Rules
1. At the beginning of every session, read this file before doing any work.
2. During every session, keep both `status.md` and `memory.md` updated.
3. Record major decisions, attempted approaches, outcomes, blockers, and next actions here before ending the session.
4. Do not treat AI-generated alt text as automatically compliant. Keep a human-review path in scope.
5. Prefer reversible changes, dry runs, and audit logs before any bulk write to WordPress.

## Current Status
- Phase: Read-only discovery and context mapping
- Status: In progress
- Last updated: 2026-03-13

## Research Summary
- WordPress exposes media records through the REST API at `/wp/v2/media`, including the `alt_text` field, and supports updating media items through the same endpoint.
- WordPress core stores attachment alt text in attachment metadata used by `wp_get_attachment_image()`, which reads `_wp_attachment_image_alt`.
- WP-CLI can update post meta, which makes a server-side or remote CLI workflow viable for writing alt text to attachments.
- WCAG 2.2 Success Criterion 1.1.1 requires text alternatives for non-text content. W3C guidance makes clear that correct alt text depends on context, and some images should have empty alt text rather than descriptive text.
- Section 508 guidance warns against generic computer-generated descriptions and emphasizes concise, context-relevant text in the same language as page content.

## Recommended Architecture
- Preferred path: A review-first tool with two stages.
- Stage 1: Discover images and usage context from WordPress.
- Stage 2: Generate candidate alt text with a vision-capable model plus page/post context, then require review or high-confidence approval rules before writing back.

## Implementation Options

### Option A: External script using WordPress REST API
- Best for: Fastest delivery, least invasive deployment, works without installing custom WordPress code if REST auth is available.
- Flow:
  - Authenticate to WordPress REST API.
  - List media from `/wp/v2/media`.
  - Pull referencing posts/pages for context.
  - Fetch image URLs and send image + surrounding content to a vision model.
  - Store suggested alt text in a local report.
  - Write approved values back with `POST /wp/v2/media/<id>`.
- Pros:
  - Simple deployment.
  - Language/runtime flexibility.
  - Easy to run locally or in CI.
- Cons:
  - Context gathering can be incomplete if images are injected by builders, shortcodes, or custom fields outside standard content.
  - Depends on REST auth and site exposure.

### Option B: WordPress plugin with admin review UI
- Best for: Deepest WordPress integration and highest editor trust.
- Flow:
  - Run discovery from inside WordPress.
  - Inspect attachment usage, featured images, and post content server-side.
  - Queue jobs for AI analysis.
  - Show suggestions in wp-admin for approval, edit, skip, or bulk apply.
- Pros:
  - Best access to WordPress internals.
  - Easier editorial workflow.
  - Can hook directly into upload/edit flows for new images.
- Cons:
  - More code and testing.
  - Harder to ship quickly than an external script.

### Option C: Hybrid system
- Best for: Long-term production choice.
- Shape:
  - External worker handles AI, rate limits, batching, logs, and retries.
  - Small WordPress plugin exposes a queue/review UI and secure site-side context endpoint.
- Pros:
  - Clean separation of concerns.
  - Easier scaling and observability.
  - Better security than putting all logic inside WordPress.
- Cons:
  - Highest implementation complexity.

### Option D: Server-side WP-CLI command
- Best for: Sites with shell access and ops comfort.
- Flow:
  - Implement a custom WP-CLI command or shell workflow on the WordPress host.
  - Read attachments and usage directly from WordPress.
  - Call the AI service from the server.
  - Update `_wp_attachment_image_alt` via WordPress functions or `wp post meta update`.
- Pros:
  - Strong access to WordPress internals.
  - Good for large batches and cron.
- Cons:
  - Requires shell access.
  - Operationally less friendly for non-technical editors.

## Recommended Plan
1. Build a proof of concept as an external script first.
2. Make it review-first, with `--dry-run` as the default mode.
3. Generate suggestions only when one of these is true:
   - existing alt text is missing
   - existing alt text is suspiciously low quality
   - user explicitly requests overwrite
4. Include page or post context when prompting the model.
5. Keep a CSV or JSONL audit log with attachment ID, URL, prior alt text, suggested alt text, confidence, reviewer action, and write status.
6. Add a second pass for complex or risky cases:
   - charts
   - screenshots with text
   - logos
   - linked or functional images
   - decorative images
7. Only after the script is stable, decide whether to keep it external or wrap it in a plugin/admin UI.

## Key Risks
- ADA/WCAG compliance is not guaranteed by image recognition alone because meaning depends on page context.
- Some rendered `<img>` tags may contain hard-coded `alt` attributes in post content or builder output, so updating attachment alt text may not fix every front-end instance.
- Decorative images should often use empty alt text, which a naive captioning workflow will get wrong.
- Images containing text may need transcription, not description.
- Batch processing can become costly without rate limiting, caching, and model-tier controls.

## Initial Delivery Scope
- CLI script or small app that:
  - authenticates to WordPress
  - enumerates image attachments
  - finds likely usage context
  - generates candidate alt text
  - outputs reviewable report
  - optionally writes approved alt text back
- Supporting files:
  - `status.md`
  - `memory.md`
  - later: `README.md`, config template, prompt templates, sample reports

## What Has Been Tried
- 2026-03-12: Inspected workspace. Result: repository was empty.
- 2026-03-12: Researched official WordPress REST API, WP-CLI, WCAG/WAI, Section 508, and OpenAI image-analysis documentation. Result: enough information gathered to define implementation options and initial architecture.
- 2026-03-12: Inspected local integration assets. Result: `.env` already contains `WP_SITE_URL`, `WP_USERNAME`, and `WP_APP_PASSWORD`, and `assets/upload_via_ftp.py` establishes a Python + `python-dotenv` pattern for shared configuration.
- 2026-03-12: Scaffolded a Python CLI with `auth-check` and `discover` commands. Result: package installs and compiles successfully.
- 2026-03-12: Ran live REST validation against the target WordPress site. Result: authentication succeeded using the existing application password credentials.
- 2026-03-12: Investigated early REST failures. Result: the configured `www` host redirects to the canonical non-`www` host, which caused auth loss during redirects; client now resolves the canonical REST root before authenticated requests.
- 2026-03-12: Investigated media endpoint instability. Result: broad media responses were failing site-side; restricting discovery to required `_fields` made the endpoint reliable for current discovery use.
- 2026-03-13: Prepared repository for first GitHub push. Result: added `.gitignore` to exclude secrets and local build artifacts.
- 2026-03-13: Created the initial git commit and pushed to GitHub. Result: repository is now tracking `origin/main`.
- 2026-03-13: Added a read-only `context-report` CLI command. Result: the tool can now scan published `posts` and `pages` and report likely attachment usage matches using attachment ID and source URL heuristics.
- 2026-03-13: Ran live validation for `context-report` against the configured site. Result: command works against production data and scanned 54 published content items with `--max-content-pages 1`.
- 2026-03-13: Fixed paginated `--missing-alt-only` discovery behavior. Result: missing-alt discovery and context reports now scan forward across source media pages until they fill the requested batch or exhaust the endpoint.
- 2026-03-13: Clarified product-direction open questions with user input. Result: Python is confirmed, the target site is Elementor-based, initial rewrite scope includes missing and weak alt text, and the working deployment default is a local runner.
- 2026-03-13: Expanded context mapping beyond REST-rendered content. Result: `context-report` now fetches public page HTML and matches media against both rendered content and front-end markup for better Elementor coverage.

## Resolved Issues
- Need for persistent session continuity files: resolved by creating `status.md` and `memory.md`.
- Need for an initial architecture direction: resolved by selecting a review-first external script as the preferred first milestone.
- WordPress authentication uncertainty: partially resolved by confirming likely REST API access via application password in `.env`.
- Live WordPress REST authentication: resolved by validating read-only authenticated access with the existing credentials.
- Redirect-related auth failure: resolved in the CLI by resolving the canonical REST base URL before authenticated calls.
- Media discovery endpoint reliability: partially resolved by requesting only the fields needed for discovery.
- Initial repository publishing: resolved by creating the first commit and pushing it to GitHub.
- Need for a first attachment-to-content mapping workflow: partially resolved by adding a read-only context report over rendered post/page content.
- Paged missing-alt discovery returning empty batches despite later matches: resolved by scan-forward filtering across source media pages.
- Need to inspect builder-managed front-end markup beyond REST-rendered content: partially resolved by adding public-page HTML fetching to `context-report`.

## Open Questions
- Authentication method available for WordPress: confirmed working via application passwords, with canonical-host resolution required.
- Hosting path after the first local-runner milestone: keep local-only, move to CI, or move closer to WordPress?
- How should usage context be gathered for Elementor-generated images and other builder-managed assets?

## Next Actions
1. Design a review report format, likely JSONL plus CSV summary, around the new context-report data model.
2. Define prompt and decision rules for decorative, functional, informative, text-heavy, and complex images.
3. Add suggestion generation in a read-only mode.
4. Add explicit approval and apply stages after the review format is stable.

## Tasks
- [x] Expand context mapping beyond rendered post/page content into builder-heavy or custom-field-driven image usage where REST-rendered HTML is incomplete.
- [ ] Design a review report format, likely JSONL plus CSV summary, around the new context-report data model.
- [ ] Define prompt and decision rules for decorative, functional, informative, text-heavy, and complex images.
- [ ] Add suggestion generation in a read-only mode.
- [ ] Add explicit approval and apply stages after the review format is stable.

## Sources
- WordPress REST API media reference: https://developer.wordpress.org/rest-api/reference/media/
- WordPress REST API overview: https://developer.wordpress.org/rest-api/
- WordPress `wp_get_attachment_image()` reference: https://developer.wordpress.org/reference/functions/wp_get_attachment_image/
- WordPress `wp_get_attachment_image_attributes` hook: https://developer.wordpress.org/reference/hooks/wp_get_attachment_image_attributes/
- WP-CLI `wp post meta update`: https://developer.wordpress.org/cli/commands/post/meta/update/
- WP-CLI commands index: https://developer.wordpress.org/cli/commands/
- W3C alt decision tree: https://www.w3.org/WAI/tutorials/images/decision-tree/
- WCAG 2.2: https://www.w3.org/TR/WCAG22/
- Section 508 alt text guidance: https://www.section508.gov/create/alternative-text/
- OpenAI images and vision guide: https://platform.openai.com/docs/guides/images-vision
- OpenAI Batch API guide: https://platform.openai.com/docs/guides/batch
