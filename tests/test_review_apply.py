from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from wp_alt_text.apply import apply_reviewed_alt_text
from wp_alt_text.review import auto_review_high_confidence, is_auto_approvable_suggestion
from wp_alt_text.review_html import validate_review_records, write_review_html


class _StubWordPressClient:
    def update_media_alt_text(self, *, attachment_id: int, alt_text: str) -> dict[str, str | int]:
        return {
            "attachment_id": attachment_id,
            "alt_text": alt_text,
            "modified": "2026-03-13T00:00:00",
        }


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

    def test_review_record_validation_rejects_missing_sections(self) -> None:
        record = _base_record(
            attachment_id=1,
            candidate_type="informative",
            candidate_alt_text="Exterior of courthouse building.",
        )
        del record["review"]

        with self.assertRaises(ValueError):
            validate_review_records([record])


if __name__ == "__main__":
    unittest.main()
