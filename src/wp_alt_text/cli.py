from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import load_settings
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

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

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
            print(
                "Fetched "
                f"{len(records)} image attachment(s) "
                f"(page {meta['page']} of {meta['total_pages'] or '?'}, "
                f"reported total {meta['total'] or '?'})"
            )
            for record in records:
                alt_state = "missing alt" if not record.alt_text else "has alt"
                print(
                    f"- id={record.attachment_id} "
                    f"{record.mime_type or record.media_type} "
                    f"[{alt_state}] "
                    f"{record.source_url}"
                )
            return 0

        parser.error(f"Unsupported command: {args.command}")
        return 2
    except WordPressError as exc:
        print(f"WordPress API error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return 1
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
