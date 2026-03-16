from __future__ import annotations

import contextlib
import io
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from wp_alt_text import cli
from wp_alt_text.apply import apply_reviewed_alt_text
from wp_alt_text.config import Settings
from wp_alt_text.review import auto_review_high_confidence, is_auto_approvable_suggestion
from wp_alt_text.review_html import validate_review_records, write_review_html
from wp_alt_text.wordpress import (
    ContentRecord,
    MediaContextMatch,
    MediaRecord,
    WordPressClient,
    WordPressError,
)


class _StubWordPressClient:
    def update_media_alt_text(self, *, attachment_id: int, alt_text: str) -> dict[str, str | int]:
        return {
            "attachment_id": attachment_id,
            "alt_text": alt_text,
            "modified": "2026-03-13T00:00:00",
        }


class _CliFakeWordPressClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.closed = False

    def collect_media(
        self,
        *,
        page: int = 1,
        per_page: int = 20,
        max_pages: int | None = None,
        missing_alt_only: bool = False,
        media_type: str = "image",
    ) -> tuple[list[object], dict[str, object]]:
        del media_type
        records = [
            MediaRecord(
                attachment_id=11,
                date="2026-03-13T00:00:00",
                slug="first-image",
                media_type="image",
                mime_type="image/jpeg",
                source_url="https://example.com/uploads/first.jpg",
                alt_text="",
                title="First",
            ),
            MediaRecord(
                attachment_id=12,
                date="2026-03-13T00:00:00",
                slug="second-image",
                media_type="image",
                mime_type="image/jpeg",
                source_url="https://example.com/uploads/second.jpg",
                alt_text="Existing alt",
                title="Second",
            ),
        ]
        if missing_alt_only:
            records = [record for record in records if not record.alt_text]
        return records, {
            "total": 2,
            "total_pages": 2,
            "page": page,
            "per_page": per_page,
            "filtered": missing_alt_only,
            "pages_scanned": [1, 2] if max_pages is None else [1],
            "source_records_examined": 2,
            "returned_records": len(records),
            "max_pages": max_pages,
        }

    def list_media(
        self,
        *,
        page: int = 1,
        per_page: int = 20,
        missing_alt_only: bool = False,
        media_type: str = "image",
    ) -> tuple[list[object], dict[str, object]]:
        return self.collect_media(
            page=page,
            per_page=per_page,
            max_pages=1,
            missing_alt_only=missing_alt_only,
            media_type=media_type,
        )

    def collect_content(
        self,
        *,
        endpoints: tuple[str, ...] = ("posts", "pages"),
        per_page: int = 100,
        max_pages: int | None = None,
        status: str = "publish",
    ) -> tuple[list[object], dict[str, object]]:
        del per_page, max_pages, status
        records = [
            ContentRecord(
                content_id=201,
                content_type="page",
                status="publish",
                slug="about",
                link="https://example.com/about",
                title="About",
                rendered_content='<img class="wp-image-11" src="https://example.com/uploads/first.jpg">',
                public_html="",
            )
        ]
        return records, {
            "endpoints": endpoints,
            "per_page": 100,
            "max_pages": None,
            "status": "publish",
            "pages_scanned": {"pages": 1},
            "totals": {"pages": 1},
            "content_items": len(records),
            "public_html_fetched": 0,
            "public_html_failed": 0,
        }

    def match_media_to_content(
        self,
        media_records: list[object],
        content_records: list[object],
    ) -> dict[int, list[object]]:
        del content_records
        return {
            int(record.attachment_id): [
                MediaContextMatch(
                    content_id=201,
                    content_type="page",
                    status="publish",
                    slug="about",
                    link="https://example.com/about",
                    title="About",
                    content_source="rendered_content",
                    match_reason="attachment_id",
                    snippet="wp-image-11",
                )
            ]
            if int(record.attachment_id) == 11
            else []
            for record in media_records
        }

    def close(self) -> None:
        self.closed = True


class _FakeResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        json_data: object | None = None,
        text: str = "",
        headers: dict[str, str] | None = None,
        url: str = "",
    ) -> None:
        self.status_code = status_code
        self._json_data = json_data
        self.text = text
        self.headers = headers or {}
        self.url = url

    def json(self) -> object:
        if self._json_data is None:
            raise ValueError("No JSON payload configured")
        return self._json_data


class _FakeSession:
    def __init__(
        self,
        *,
        root_response: _FakeResponse,
        request_responses: list[_FakeResponse],
    ) -> None:
        self.root_response = root_response
        self.request_responses = list(request_responses)
        self.auth: tuple[str, str] | None = None
        self.headers: dict[str, str] = {}
        self.get_calls: list[tuple[str, dict[str, object]]] = []
        self.request_calls: list[tuple[str, str, dict[str, object]]] = []
        self.closed = False

    def get(self, url: str, **kwargs: object) -> _FakeResponse:
        self.get_calls.append((url, kwargs))
        return self.root_response

    def request(self, method: str, url: str, **kwargs: object) -> _FakeResponse:
        self.request_calls.append((method, url, kwargs))
        if not self.request_responses:
            raise AssertionError(f"No fake response configured for {method} {url}")
        return self.request_responses.pop(0)

    def close(self) -> None:
        self.closed = True


def _base_record(*, attachment_id: int, candidate_type: str, candidate_alt_text: str) -> dict:
    return {
        "attachment_id": attachment_id,
        "current_alt_text": "",
        "suggestion": {
            "status": "generated",
            "candidate_alt_text": candidate_alt_text,
            "candidate_type": candidate_type,
            "confidence": "high",
            "rationale": "",
            "warnings": [],
            "requires_manual_review": False,
            "long_description_needed": False,
            "model": "gpt-4.1-mini",
            "prompt_version": "2026-03-13",
            "generated_at": "2026-03-13T00:00:00",
            "error": "",
        },
        "review": {
            "status": "pending",
            "action": "",
            "reviewer": "",
            "reviewed_at": "",
            "notes": "",
            "final_alt_text": "",
        },
        "apply": {
            "status": "not_attempted",
            "target_alt_text": "",
            "applied_at": "",
            "error": "",
        },
    }


class ReviewApplyPolicyTests(unittest.TestCase):
    def test_auto_approvable_requires_strict_informative_signal(self) -> None:
        informative = _base_record(
            attachment_id=1,
            candidate_type="informative",
            candidate_alt_text="Exterior of courthouse building.",
        )
        self.assertTrue(is_auto_approvable_suggestion(informative))

        text_heavy = _base_record(
            attachment_id=2,
            candidate_type="text_heavy",
            candidate_alt_text="Flyer text",
        )
        self.assertFalse(is_auto_approvable_suggestion(text_heavy))

        warned = _base_record(
            attachment_id=3,
            candidate_type="informative",
            candidate_alt_text="Exterior of courthouse building.",
        )
        warned["suggestion"]["warnings"] = ["possible ambiguity"]
        self.assertFalse(is_auto_approvable_suggestion(warned))

    def test_auto_review_high_confidence_only_updates_eligible_records(self) -> None:
        records = [
            _base_record(
                attachment_id=1,
                candidate_type="informative",
                candidate_alt_text="Exterior of courthouse building.",
            ),
            _base_record(
                attachment_id=2,
                candidate_type="functional",
                candidate_alt_text="Email button",
            ),
        ]

        meta = auto_review_high_confidence(review_records=records)

        self.assertEqual(meta["targeted"], 1)
        self.assertEqual(meta["updated"], 1)
        self.assertEqual(records[0]["review"]["action"], "approve")
        self.assertEqual(records[0]["review"]["reviewer"], "auto-review")
        self.assertEqual(
            records[0]["review"]["final_alt_text"],
            "Exterior of courthouse building.",
        )
        self.assertEqual(records[1]["review"]["status"], "pending")

    def test_apply_auto_high_confidence_dry_run_records_review_and_apply_state(self) -> None:
        records = [
            _base_record(
                attachment_id=1,
                candidate_type="informative",
                candidate_alt_text="Exterior of courthouse building.",
            ),
            _base_record(
                attachment_id=2,
                candidate_type="text_heavy",
                candidate_alt_text="Important flyer text.",
            ),
        ]
        records[1]["suggestion"]["requires_manual_review"] = True

        meta = apply_reviewed_alt_text(
            review_records=records,
            wordpress_client=_StubWordPressClient(),
            auto_apply_high_confidence=True,
            dry_run=True,
        )

        self.assertEqual(meta["auto_review_targeted"], 1)
        self.assertEqual(meta["auto_reviewed"], 1)
        self.assertEqual(meta["targeted"], 1)
        self.assertEqual(meta["dry_run"], 1)
        self.assertEqual(records[0]["review"]["status"], "reviewed")
        self.assertEqual(records[0]["apply"]["status"], "dry_run")
        self.assertEqual(
            records[0]["apply"]["target_alt_text"],
            "Exterior of courthouse building.",
        )
        self.assertEqual(records[1]["review"]["status"], "pending")
        self.assertEqual(records[1]["apply"]["status"], "not_attempted")

    def test_review_html_writer_outputs_expected_markup(self) -> None:
        record = _base_record(
            attachment_id=1,
            candidate_type="informative",
            candidate_alt_text="Exterior of courthouse building.",
        )
        record["attachment_title"] = "Courthouse"
        record["source_url"] = "https://example.com/image.jpg"
        record["context_summary"] = [
            {
                "title": "About",
                "content_type": "page",
                "link": "https://example.com/about",
                "content_source": "rendered_content",
                "match_reason": "attachment_id",
            }
        ]

        with TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "review-report.html"
            write_review_html(output_path=output_path, report_records=[record])
            html = output_path.read_text(encoding="utf-8")

        self.assertIn("Review Alt Text", html)
        self.assertIn("Courthouse", html)
        self.assertIn("review-report-reviewed.jsonl", html)
        self.assertIn("wp-alt-text review-import", html)
        self.assertIn("Copy JSONL", html)
        self.assertIn("Export Fallback", html)

    def test_review_record_validation_rejects_missing_sections(self) -> None:
        record = _base_record(
            attachment_id=1,
            candidate_type="informative",
            candidate_alt_text="Exterior of courthouse building.",
        )
        del record["review"]

        with self.assertRaises(ValueError):
            validate_review_records([record])


class CliIntegrationTests(unittest.TestCase):
    def test_prompt_spec_json_command_prints_structured_output(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        with (
            patch("sys.argv", ["wp-alt-text", "prompt-spec", "--json"]),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            exit_code = cli.main()

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        payload = json.loads(stdout.getvalue())
        self.assertIn("prompt_version", payload)
        self.assertIn("role_rules", payload)
        self.assertIn("output_schema", payload)

    def test_review_import_rewrites_managed_artifacts(self) -> None:
        record = _base_record(
            attachment_id=11,
            candidate_type="informative",
            candidate_alt_text="Exterior of courthouse building.",
        )
        record["source_url"] = "https://example.com/image.jpg"
        record["review"] = {
            "status": "reviewed",
            "action": "approve",
            "reviewer": "TJ",
            "reviewed_at": "2026-03-13T00:00:00Z",
            "notes": "ready",
            "final_alt_text": "Exterior of courthouse building.",
        }

        with TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "reviewed.jsonl"
            input_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
            output_dir = Path(temp_dir) / "normalized"

            stdout = io.StringIO()
            stderr = io.StringIO()
            with (
                patch(
                    "sys.argv",
                    [
                        "wp-alt-text",
                        "review-import",
                        "--input-report",
                        str(input_path),
                        "--output-dir",
                        str(output_dir),
                    ],
                ),
                contextlib.redirect_stdout(stdout),
                contextlib.redirect_stderr(stderr),
            ):
                exit_code = cli.main()

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr.getvalue(), "")
            self.assertIn("Imported 1 reviewed record(s).", stdout.getvalue())
            self.assertTrue((output_dir / "review-report.jsonl").exists())
            self.assertTrue((output_dir / "review-report.csv").exists())

    def test_review_report_all_pages_writes_csv_from_full_media_scan(self) -> None:
        with TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "report"
            stdout = io.StringIO()
            stderr = io.StringIO()

            with (
                patch(
                    "sys.argv",
                    [
                        "wp-alt-text",
                        "review-report",
                        "--all-pages",
                        "--output-dir",
                        str(output_dir),
                    ],
                ),
                patch(
                    "wp_alt_text.cli.load_settings",
                    return_value=Settings(
                        wp_site_url="https://example.com",
                        wp_username="user",
                        wp_app_password="pass",
                    ),
                ),
                patch("wp_alt_text.cli.WordPressClient", _CliFakeWordPressClient),
                contextlib.redirect_stdout(stdout),
                contextlib.redirect_stderr(stderr),
            ):
                exit_code = cli.main()

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr.getvalue(), "")
            self.assertIn("Wrote 2 review record(s)", stdout.getvalue())
            self.assertIn("Media page(s): 1, 2.", stdout.getvalue())

            csv_path = output_dir / "review-report.csv"
            jsonl_path = output_dir / "review-report.jsonl"
            self.assertTrue(csv_path.exists())
            self.assertTrue(jsonl_path.exists())

            csv_text = csv_path.read_text(encoding="utf-8")
            self.assertIn("attachment_id", csv_text)
            self.assertIn("11", csv_text)
            self.assertIn("12", csv_text)


class WordPressClientTests(unittest.TestCase):
    def test_collect_media_scans_all_pages_and_filters_missing_alt(self) -> None:
        client = WordPressClient(
            Settings(
                wp_site_url="https://www.example.com",
                wp_username="user",
                wp_app_password="pass",
            )
        )
        fake_session = _FakeSession(
            root_response=_FakeResponse(
                json_data={"name": "Example"},
                url="https://example.com/wp-json/",
            ),
            request_responses=[
                _FakeResponse(
                    json_data=[
                        {
                            "id": 1,
                            "date": "2026-03-13T00:00:00",
                            "slug": "first",
                            "media_type": "image",
                            "mime_type": "image/jpeg",
                            "source_url": "https://example.com/1.jpg",
                            "alt_text": "",
                            "title": {"rendered": "First"},
                        },
                        {
                            "id": 2,
                            "date": "2026-03-13T00:00:00",
                            "slug": "second",
                            "media_type": "image",
                            "mime_type": "image/jpeg",
                            "source_url": "https://example.com/2.jpg",
                            "alt_text": "Existing alt",
                            "title": {"rendered": "Second"},
                        },
                    ],
                    headers={"X-WP-Total": "5", "X-WP-TotalPages": "3"},
                ),
                _FakeResponse(
                    json_data=[
                        {
                            "id": 3,
                            "date": "2026-03-13T00:00:00",
                            "slug": "third",
                            "media_type": "image",
                            "mime_type": "image/jpeg",
                            "source_url": "https://example.com/3.jpg",
                            "alt_text": "",
                            "title": {"rendered": "Third"},
                        },
                        {
                            "id": 4,
                            "date": "2026-03-13T00:00:00",
                            "slug": "fourth",
                            "media_type": "image",
                            "mime_type": "image/jpeg",
                            "source_url": "https://example.com/4.jpg",
                            "alt_text": "",
                            "title": {"rendered": "Fourth"},
                        },
                    ],
                    headers={"X-WP-Total": "5", "X-WP-TotalPages": "3"},
                ),
                _FakeResponse(
                    json_data=[
                        {
                            "id": 5,
                            "date": "2026-03-13T00:00:00",
                            "slug": "fifth",
                            "media_type": "image",
                            "mime_type": "image/jpeg",
                            "source_url": "https://example.com/5.jpg",
                            "alt_text": "Already set",
                            "title": {"rendered": "Fifth"},
                        }
                    ],
                    headers={"X-WP-Total": "5", "X-WP-TotalPages": "3"},
                ),
            ],
        )
        client.session = fake_session

        records, meta = client.collect_media(
            page=1,
            per_page=2,
            missing_alt_only=True,
        )

        self.assertEqual([record.attachment_id for record in records], [1, 3, 4])
        self.assertEqual(meta["pages_scanned"], [1, 2, 3])
        self.assertEqual(meta["source_records_examined"], 5)
        self.assertEqual(meta["returned_records"], 3)

    def test_update_media_alt_text_uses_canonical_rest_root_and_retries_stale_reads(self) -> None:
        client = WordPressClient(
            Settings(
                wp_site_url="https://www.example.com",
                wp_username="user",
                wp_app_password="pass",
            )
        )
        fake_session = _FakeSession(
            root_response=_FakeResponse(
                json_data={"name": "Example"},
                url="https://example.com/wp-json/",
            ),
            request_responses=[
                _FakeResponse(json_data={"id": 22, "alt_text": "old", "modified": "m1"}),
                _FakeResponse(json_data={"id": 22, "alt_text": "old", "modified": "m1"}),
                _FakeResponse(
                    json_data={"id": 22, "alt_text": "New alt text", "modified": "m2"}
                ),
            ],
        )
        client.session = fake_session

        with patch("wp_alt_text.wordpress.time.sleep") as sleep_mock:
            payload = client.update_media_alt_text(
                attachment_id=22,
                alt_text="New alt text",
            )

        self.assertEqual(payload["alt_text"], "New alt text")
        self.assertEqual(
            fake_session.get_calls[0][0],
            "https://www.example.com/wp-json/",
        )
        self.assertEqual(
            fake_session.request_calls[0][1],
            "https://example.com/wp-json/wp/v2/media/22",
        )
        self.assertEqual(fake_session.request_calls[0][2]["json"], {"alt_text": "New alt text"})
        self.assertEqual(len(fake_session.request_calls), 3)
        self.assertEqual(sleep_mock.call_count, 1)

    def test_update_media_alt_text_raises_after_retry_budget_exhausted(self) -> None:
        client = WordPressClient(
            Settings(
                wp_site_url="https://www.example.com",
                wp_username="user",
                wp_app_password="pass",
            )
        )
        fake_session = _FakeSession(
            root_response=_FakeResponse(
                json_data={"name": "Example"},
                url="https://example.com/wp-json/",
            ),
            request_responses=[
                _FakeResponse(json_data={"id": 22, "alt_text": "still old", "modified": "m1"}),
                _FakeResponse(json_data={"id": 22, "alt_text": "still old", "modified": "m1"}),
                _FakeResponse(json_data={"id": 22, "alt_text": "still old", "modified": "m1"}),
                _FakeResponse(json_data={"id": 22, "alt_text": "still old", "modified": "m1"}),
                _FakeResponse(json_data={"id": 22, "alt_text": "still old", "modified": "m1"}),
                _FakeResponse(json_data={"id": 22, "alt_text": "still old", "modified": "m1"}),
            ],
        )
        client.session = fake_session

        with patch("wp_alt_text.wordpress.time.sleep") as sleep_mock:
            with self.assertRaises(WordPressError) as exc_info:
                client.update_media_alt_text(
                    attachment_id=22,
                    alt_text="New alt text",
                )

        self.assertIn("requested='New alt text'", str(exc_info.exception))
        self.assertIn("confirmed='still old'", str(exc_info.exception))
        self.assertEqual(sleep_mock.call_count, 4)


if __name__ == "__main__":
    unittest.main()
