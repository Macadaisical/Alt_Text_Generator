from __future__ import annotations

import csv
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .wordpress import MediaContextMatch, MediaRecord

REPORT_SCHEMA_VERSION = "2026-03-13"


def build_review_report_records(
    *,
    site_url: str,
    media_records: list[MediaRecord],
    matches_by_attachment: dict[int, list[MediaContextMatch]],
) -> list[dict[str, Any]]:
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    report_records: list[dict[str, Any]] = []

    for media in media_records:
        matches = matches_by_attachment.get(media.attachment_id, [])
        report_records.append(
            {
                "schema_version": REPORT_SCHEMA_VERSION,
                "generated_at": generated_at,
                "site_url": site_url,
                "attachment_id": media.attachment_id,
                "source_url": media.source_url,
                "mime_type": media.mime_type,
                "media_type": media.media_type,
                "attachment_title": media.title,
                "attachment_slug": media.slug,
                "attachment_date": media.date,
                "current_alt_text": media.alt_text,
                "current_alt_status": _alt_status(media.alt_text),
                "usage_count": len(matches),
                "usage_sources": sorted({match.content_source for match in matches}),
                "context_matches": [asdict(match) for match in matches],
                "context_summary": _build_context_summary(matches),
                "suggestion": {
                    "status": "pending",
                    "candidate_alt_text": "",
                    "candidate_type": "",
                    "confidence": "",
                    "rationale": "",
                    "warnings": [],
                    "requires_manual_review": False,
                    "long_description_needed": False,
                    "model": "",
                    "prompt_version": "",
                    "generated_at": "",
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
        )

    return report_records


def write_review_report(
    *,
    output_dir: Path,
    report_records: list[dict[str, Any]],
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = output_dir / "review-report.jsonl"
    csv_path = output_dir / "review-report.csv"

    with jsonl_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in report_records:
            handle.write(json.dumps(record, ensure_ascii=True))
            handle.write("\n")

    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=_csv_fieldnames())
        writer.writeheader()
        for record in report_records:
            writer.writerow(_flatten_record_for_csv(record))

    return {
        "output_dir": str(output_dir),
        "jsonl_path": str(jsonl_path),
        "csv_path": str(csv_path),
        "record_count": len(report_records),
    }


def _alt_status(alt_text: str) -> str:
    return "missing" if not alt_text.strip() else "present"


def _build_context_summary(matches: list[MediaContextMatch]) -> list[dict[str, Any]]:
    summary: list[dict[str, Any]] = []
    for match in matches:
        summary.append(
            {
                "content_id": match.content_id,
                "content_type": match.content_type,
                "title": match.title,
                "link": match.link,
                "content_source": match.content_source,
                "match_reason": match.match_reason,
            }
        )
    return summary


def _csv_fieldnames() -> list[str]:
    return [
        "schema_version",
        "generated_at",
        "site_url",
        "attachment_id",
        "source_url",
        "mime_type",
        "media_type",
        "attachment_title",
        "current_alt_text",
        "current_alt_status",
        "usage_count",
        "top_context_type",
        "top_context_title",
        "top_context_link",
        "top_context_source",
        "top_match_reason",
        "suggestion_status",
        "candidate_alt_text",
        "candidate_type",
        "confidence",
        "requires_manual_review",
        "long_description_needed",
        "suggestion_warnings",
        "suggestion_error",
        "review_status",
        "review_action",
        "reviewer",
        "reviewed_at",
        "review_notes",
        "final_alt_text",
        "apply_status",
        "applied_at",
        "apply_target_alt_text",
        "apply_error",
    ]


def _flatten_record_for_csv(record: dict[str, Any]) -> dict[str, Any]:
    top_context = (record.get("context_summary") or [{}])[0]
    suggestion = record.get("suggestion") or {}
    review = record.get("review") or {}
    apply_state = record.get("apply") or {}
    return {
        "schema_version": record.get("schema_version", ""),
        "generated_at": record.get("generated_at", ""),
        "site_url": record.get("site_url", ""),
        "attachment_id": record.get("attachment_id", ""),
        "source_url": record.get("source_url", ""),
        "mime_type": record.get("mime_type", ""),
        "media_type": record.get("media_type", ""),
        "attachment_title": record.get("attachment_title", ""),
        "current_alt_text": record.get("current_alt_text", ""),
        "current_alt_status": record.get("current_alt_status", ""),
        "usage_count": record.get("usage_count", 0),
        "top_context_type": top_context.get("content_type", ""),
        "top_context_title": top_context.get("title", ""),
        "top_context_link": top_context.get("link", ""),
        "top_context_source": top_context.get("content_source", ""),
        "top_match_reason": top_context.get("match_reason", ""),
        "suggestion_status": suggestion.get("status", ""),
        "candidate_alt_text": suggestion.get("candidate_alt_text", ""),
        "candidate_type": suggestion.get("candidate_type", ""),
        "confidence": suggestion.get("confidence", ""),
        "requires_manual_review": suggestion.get("requires_manual_review", False),
        "long_description_needed": suggestion.get("long_description_needed", False),
        "suggestion_warnings": " | ".join(suggestion.get("warnings", [])),
        "suggestion_error": suggestion.get("error", ""),
        "review_status": review.get("status", ""),
        "review_action": review.get("action", ""),
        "reviewer": review.get("reviewer", ""),
        "reviewed_at": review.get("reviewed_at", ""),
        "review_notes": review.get("notes", ""),
        "final_alt_text": review.get("final_alt_text", ""),
        "apply_status": apply_state.get("status", ""),
        "applied_at": apply_state.get("applied_at", ""),
        "apply_target_alt_text": apply_state.get("target_alt_text", ""),
        "apply_error": apply_state.get("error", ""),
    }
