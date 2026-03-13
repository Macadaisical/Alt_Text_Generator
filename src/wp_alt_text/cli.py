from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from .apply import ApplyError, apply_reviewed_alt_text
from .config import load_openai_settings, load_settings
from .prompting import build_suggestion_messages, build_system_prompt, prompt_spec
from .reporting import build_review_report_records, write_review_report
from .review import AUTO_APPROVE_CANDIDATE_TYPES, ReviewError, apply_review_action
from .suggestion import SuggestionClient, apply_suggestions
from .wordpress import WordPressClient, WordPressError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wp-alt-text",
        description="Discover WordPress media and prepare alt-text workflows.",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(".env"),
        help="Path to the .env file with WordPress credentials.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser(
        "auth-check",
        help="Verify WordPress REST API authentication without changing data.",
    )

    discover_parser = subparsers.add_parser(
        "discover",
        help="List image attachments from WordPress without changing data.",
    )
    discover_parser.add_argument(
        "--page",
        type=int,
        default=1,
        help="REST page number to fetch.",
    )
    discover_parser.add_argument(
        "--per-page",
        type=int,
        default=20,
        choices=range(1, 101),
        metavar="1-100",
        help="Number of records to request from the API.",
    )
    discover_parser.add_argument(
        "--missing-alt-only",
        action="store_true",
        help="Filter results to images with empty alt text.",
    )
    discover_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON output.",
    )

    context_parser = subparsers.add_parser(
        "context-report",
        help="Map image attachments to likely post/page usage without changing data.",
    )
    context_parser.add_argument(
        "--page",
        type=int,
        default=1,
        help="REST page number to fetch for media attachments.",
    )
    context_parser.add_argument(
        "--per-page",
        type=int,
        default=20,
        choices=range(1, 101),
        metavar="1-100",
        help="Number of media records to request from the API.",
    )
    context_parser.add_argument(
        "--missing-alt-only",
        action="store_true",
        help="Filter media attachments to images with empty alt text.",
    )
    context_parser.add_argument(
        "--content-types",
        nargs="+",
        default=["posts", "pages"],
        help="WordPress REST content endpoints to scan for usage, for example: posts pages.",
    )
    context_parser.add_argument(
        "--content-per-page",
        type=int,
        default=100,
        choices=range(1, 101),
        metavar="1-100",
        help="Number of content records to request from each endpoint per page.",
    )
    context_parser.add_argument(
        "--max-content-pages",
        type=int,
        default=None,
        help="Optional cap on pages scanned per content endpoint.",
    )
    context_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON output.",
    )

    review_parser = subparsers.add_parser(
        "review-report",
        help="Export a review-first report as JSONL and CSV without changing WordPress data.",
    )
    review_parser.add_argument(
        "--page",
        type=int,
        default=1,
        help="REST page number to fetch for media attachments.",
    )
    review_parser.add_argument(
        "--per-page",
        type=int,
        default=20,
        choices=range(1, 101),
        metavar="1-100",
        help="Number of media records to request from the API.",
    )
    review_parser.add_argument(
        "--missing-alt-only",
        action="store_true",
        help="Filter media attachments to images with empty alt text.",
    )
    review_parser.add_argument(
        "--content-types",
        nargs="+",
        default=["posts", "pages"],
        help="WordPress REST content endpoints to scan for usage, for example: posts pages.",
    )
    review_parser.add_argument(
        "--content-per-page",
        type=int,
        default=100,
        choices=range(1, 101),
        metavar="1-100",
        help="Number of content records to request from each endpoint per page.",
    )
    review_parser.add_argument(
        "--max-content-pages",
        type=int,
        default=None,
        help="Optional cap on pages scanned per content endpoint.",
    )
    review_parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("reports/latest"),
        help="Directory where review-report.jsonl and review-report.csv will be written.",
    )

    prompt_parser = subparsers.add_parser(
        "prompt-spec",
        help="Print the current alt-text decision rules and reusable prompt templates.",
    )
    prompt_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the structured prompt specification as JSON.",
    )
    prompt_parser.add_argument(
        "--review-record",
        type=Path,
        help="Optional path to a review-report JSONL file; if provided, print prompt messages for the first record.",
    )

    suggest_parser = subparsers.add_parser(
        "suggest",
        help="Generate read-only alt-text suggestions from a review-report JSONL file.",
    )
    suggest_parser.add_argument(
        "--input-report",
        type=Path,
        default=Path("reports/latest/review-report.jsonl"),
        help="Path to the input review-report JSONL file.",
    )
    suggest_parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("reports/suggested"),
        help="Directory where suggestion-enriched review artifacts will be written.",
    )
    suggest_parser.add_argument(
        "--model",
        help="Optional OpenAI model override. Defaults to OPENAI_MODEL or gpt-4.1-mini.",
    )
    suggest_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional cap on how many records to send for suggestion generation.",
    )
    suggest_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Regenerate suggestions even if a record already has generated suggestion data.",
    )

    review_action_parser = subparsers.add_parser(
        "review",
        help="Record reviewer approval decisions into a new review-report artifact set.",
    )
    review_action_parser.add_argument(
        "--input-report",
        type=Path,
        default=Path("reports/suggested/review-report.jsonl"),
        help="Path to the input review-report JSONL file.",
    )
    review_action_parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("reports/reviewed"),
        help="Directory where reviewed JSONL and CSV artifacts will be written.",
    )
    review_action_parser.add_argument(
        "--action",
        required=True,
        choices=["approve", "edit", "skip"],
        help="Reviewer action to record.",
    )
    review_action_parser.add_argument(
        "--attachment-ids",
        nargs="+",
        type=int,
        help="One or more attachment IDs to update.",
    )
    review_action_parser.add_argument(
        "--all-records",
        action="store_true",
        help="Apply the review action to every record in the input report.",
    )
    review_action_parser.add_argument(
        "--final-alt-text",
        help="Explicit final alt text. Required for --action edit. Optional override for approve.",
    )
    review_action_parser.add_argument(
        "--reviewer",
        default="",
        help="Optional reviewer name recorded in the review metadata.",
    )
    review_action_parser.add_argument(
        "--notes",
        default="",
        help="Optional review notes recorded in the review metadata.",
    )
    review_action_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing reviewed records instead of skipping them.",
    )

    apply_parser = subparsers.add_parser(
        "apply",
        help="Write reviewer-approved alt text back to WordPress, dry-run by default.",
    )
    apply_parser.add_argument(
        "--input-report",
        type=Path,
        default=Path("reports/reviewed/review-report.jsonl"),
        help="Path to the input review-report JSONL file.",
    )
    apply_parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("reports/applied"),
        help="Directory where post-apply JSONL and CSV artifacts will be written.",
    )
    apply_parser.add_argument(
        "--attachment-ids",
        nargs="+",
        type=int,
        help="One or more reviewed attachment IDs to target.",
    )
    apply_parser.add_argument(
        "--all-approved",
        action="store_true",
        help="Target every reviewed record whose action is approve or edit.",
    )
    apply_parser.add_argument(
        "--auto-apply-high-confidence",
        action="store_true",
        help=(
            "Auto-approve and target eligible high-confidence suggestions. "
            f"Current policy only auto-approves: {', '.join(AUTO_APPROVE_CANDIDATE_TYPES)}."
        ),
    )
    apply_parser.add_argument(
        "--commit",
        action="store_true",
        help="Perform live WordPress updates. Without this flag, apply runs in dry-run mode.",
    )
    apply_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Re-run records already marked applied instead of skipping them.",
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "prompt-spec":
        try:
            if args.json:
                print(json.dumps(prompt_spec(), indent=2))
                return 0

            print("Prompt version:")
            print(prompt_spec()["prompt_version"])
            print()
            print("System prompt:")
            print(build_system_prompt())

            if args.review_record:
                record = _read_first_jsonl_record(args.review_record)
                print()
                print("Example messages:")
                print(json.dumps(build_suggestion_messages(record), indent=2))
            return 0
        except Exception as exc:
            print(f"Unexpected error: {exc}", file=sys.stderr)
            return 1

    if args.command == "suggest":
        try:
            settings = load_openai_settings(args.env_file)
        except ValueError as exc:
            print(f"Configuration error: {exc}", file=sys.stderr)
            return 2

        try:
            review_records = _read_jsonl_records(args.input_report)
            suggestion_client = SuggestionClient(settings)
            run_meta = apply_suggestions(
                review_records=review_records,
                suggestion_client=suggestion_client,
                model=args.model,
                limit=args.limit,
                overwrite=args.overwrite,
            )
            write_meta = write_review_report(
                output_dir=args.output_dir,
                report_records=review_records,
            )
            print(
                f"Wrote {write_meta['record_count']} suggestion-enriched review record(s) to "
                f"{write_meta['output_dir']}."
            )
            print(f"JSONL: {write_meta['jsonl_path']}")
            print(f"CSV: {write_meta['csv_path']}")
            print(
                f"Generated suggestions for {run_meta['generated']} record(s), "
                f"skipped {run_meta['skipped']}, failed {run_meta['failed']}."
            )
            print(f"Model: {args.model or settings.openai_model}")
            return 0
        except Exception as exc:
            print(f"Unexpected error: {exc}", file=sys.stderr)
            return 1

    if args.command == "review":
        try:
            review_records = _read_jsonl_records(args.input_report)
            run_meta = apply_review_action(
                review_records=review_records,
                action=args.action,
                attachment_ids=args.attachment_ids,
                all_records=args.all_records,
                reviewer=args.reviewer,
                notes=args.notes,
                final_alt_text=args.final_alt_text,
                overwrite=args.overwrite,
            )
            write_meta = write_review_report(
                output_dir=args.output_dir,
                report_records=review_records,
            )
            print(
                f"Wrote {write_meta['record_count']} reviewed record(s) to "
                f"{write_meta['output_dir']}."
            )
            print(f"JSONL: {write_meta['jsonl_path']}")
            print(f"CSV: {write_meta['csv_path']}")
            print(
                f"Action {run_meta['action']} targeted {run_meta['targeted']} record(s), "
                f"updated {run_meta['updated']}, skipped {run_meta['skipped']}."
            )
            return 0
        except ReviewError as exc:
            print(f"Review error: {exc}", file=sys.stderr)
            return 2
        except Exception as exc:
            print(f"Unexpected error: {exc}", file=sys.stderr)
            return 1

    try:
        settings = load_settings(args.env_file)
    except ValueError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    client = WordPressClient(settings)
    try:
        if args.command == "auth-check":
            payload = client.auth_check()
            print("Authentication succeeded.")
            print(f"Site: {settings.wp_site_url}")
            print(f"User ID: {payload['id']}")
            print(f"Name: {payload['name']}")
            print(f"Slug: {payload['slug']}")
            print(f"Roles: {', '.join(payload['roles']) if payload['roles'] else '(none)'}")
            return 0

        if args.command == "discover":
            records, meta = client.list_media(
                page=args.page,
                per_page=args.per_page,
                missing_alt_only=args.missing_alt_only,
            )
            if args.json:
                print(
                    json.dumps(
                        {
                            "meta": meta,
                            "records": [record.__dict__ for record in records],
                        },
                        indent=2,
                    )
                )
                return 0

            print(f"Site: {settings.wp_site_url}")
            summary = (
                "Fetched "
                f"{len(records)} image attachment(s) "
                f"(page {meta['page']} of {meta['total_pages'] or '?'}, "
                f"reported total {meta['total'] or '?'})"
            )
            if args.missing_alt_only:
                pages_scanned = meta.get("source_pages_scanned", [meta["page"]])
                summary += (
                    f" after scanning source page(s) {', '.join(str(page) for page in pages_scanned)}"
                )
            print(summary)
            for record in records:
                alt_state = "missing alt" if not record.alt_text else "has alt"
                print(
                    f"- id={record.attachment_id} "
                    f"{record.mime_type or record.media_type} "
                    f"[{alt_state}] "
                    f"{record.source_url}"
                )
            return 0

        if args.command == "context-report":
            media_records, media_meta = client.list_media(
                page=args.page,
                per_page=args.per_page,
                missing_alt_only=args.missing_alt_only,
            )
            content_records, content_meta = client.collect_content(
                endpoints=tuple(args.content_types),
                per_page=args.content_per_page,
                max_pages=args.max_content_pages,
            )
            matches = client.match_media_to_content(media_records, content_records)

            report_records = [
                {
                    "media": asdict(record),
                    "usage_count": len(matches[record.attachment_id]),
                    "matches": [asdict(match) for match in matches[record.attachment_id]],
                }
                for record in media_records
            ]

            if args.json:
                print(
                    json.dumps(
                        {
                            "media_meta": media_meta,
                            "content_meta": content_meta,
                            "records": report_records,
                        },
                        indent=2,
                    )
                )
                return 0

            print(f"Site: {settings.wp_site_url}")
            summary = (
                f"Scanned {len(media_records)} media attachment(s) and "
                f"{content_meta['content_items']} content item(s) from "
                f"{', '.join(args.content_types)}."
            )
            summary += (
                f" Public HTML fetched for {content_meta['public_html_fetched']} item(s)"
                f" with {content_meta['public_html_failed']} fetch failure(s)."
            )
            if args.missing_alt_only:
                pages_scanned = media_meta.get("source_pages_scanned", [media_meta["page"]])
                summary += (
                    f" Media source page(s): {', '.join(str(page) for page in pages_scanned)}."
                )
            print(summary)
            for item in report_records:
                media = item["media"]
                alt_state = "missing alt" if not media["alt_text"] else "has alt"
                print(
                    f"- id={media['attachment_id']} "
                    f"[{alt_state}] "
                    f"{item['usage_count']} match(es) "
                    f"{media['source_url']}"
                )
                for match in item["matches"]:
                    title = match["title"] or "(untitled)"
                    print(
                        f"  -> {match['content_type']}#{match['content_id']} "
                        f"{title} [{match['content_source']}:{match['match_reason']}] "
                        f"{match['link']}"
                    )
            return 0

        if args.command == "review-report":
            media_records, media_meta = client.list_media(
                page=args.page,
                per_page=args.per_page,
                missing_alt_only=args.missing_alt_only,
            )
            content_records, content_meta = client.collect_content(
                endpoints=tuple(args.content_types),
                per_page=args.content_per_page,
                max_pages=args.max_content_pages,
            )
            matches = client.match_media_to_content(media_records, content_records)
            report_records = build_review_report_records(
                site_url=settings.wp_site_url,
                media_records=media_records,
                matches_by_attachment=matches,
            )
            write_meta = write_review_report(
                output_dir=args.output_dir,
                report_records=report_records,
            )

            print(f"Site: {settings.wp_site_url}")
            print(
                f"Wrote {write_meta['record_count']} review record(s) to "
                f"{write_meta['output_dir']}."
            )
            print(f"JSONL: {write_meta['jsonl_path']}")
            print(f"CSV: {write_meta['csv_path']}")
            print(
                f"Scanned {len(media_records)} media attachment(s) and "
                f"{content_meta['content_items']} content item(s) from "
                f"{', '.join(args.content_types)}."
            )
            print(
                f"Public HTML fetched for {content_meta['public_html_fetched']} item(s)"
                f" with {content_meta['public_html_failed']} fetch failure(s)."
            )
            if args.missing_alt_only:
                pages_scanned = media_meta.get("source_pages_scanned", [media_meta["page"]])
                print(
                    "Media source page(s): "
                    f"{', '.join(str(page) for page in pages_scanned)}."
                )
            return 0

        if args.command == "apply":
            review_records = _read_jsonl_records(args.input_report)
            run_meta = apply_reviewed_alt_text(
                review_records=review_records,
                wordpress_client=client,
                attachment_ids=args.attachment_ids,
                all_approved=args.all_approved,
                auto_apply_high_confidence=args.auto_apply_high_confidence,
                dry_run=not args.commit,
                overwrite=args.overwrite,
            )
            write_meta = write_review_report(
                output_dir=args.output_dir,
                report_records=review_records,
            )

            print(f"Site: {settings.wp_site_url}")
            print(
                f"Wrote {write_meta['record_count']} post-apply record(s) to "
                f"{write_meta['output_dir']}."
            )
            print(f"JSONL: {write_meta['jsonl_path']}")
            print(f"CSV: {write_meta['csv_path']}")
            mode = "commit" if args.commit else "dry-run"
            print(
                f"Apply mode {mode} targeted {run_meta['targeted']} record(s), "
                f"applied {run_meta['applied']}, dry-run marked {run_meta['dry_run']}, "
                f"skipped {run_meta['skipped']}, failed {run_meta['failed']}."
            )
            if args.auto_apply_high_confidence:
                print(
                    "Auto-review eligible high-confidence records: "
                    f"targeted {run_meta['auto_review_targeted']}, "
                    f"reviewed {run_meta['auto_reviewed']}, "
                    f"skipped {run_meta['auto_review_skipped']}."
                )
            return 0

        parser.error(f"Unsupported command: {args.command}")
        return 2
    except ApplyError as exc:
        print(f"Apply error: {exc}", file=sys.stderr)
        return 2
    except WordPressError as exc:
        print(f"WordPress API error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return 1
    finally:
        client.close()


def _read_first_jsonl_record(path: Path) -> dict[str, object]:
    return _read_jsonl_records(path)[0]


def _read_jsonl_records(path: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                payload = json.loads(stripped)
                if not isinstance(payload, dict):
                    raise ValueError(f"Expected object record in {path}")
                records.append(payload)
    if not records:
        raise ValueError(f"No JSONL records found in {path}")
    return records


if __name__ == "__main__":
    raise SystemExit(main())
