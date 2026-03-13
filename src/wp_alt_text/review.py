from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

AUTO_APPROVE_CANDIDATE_TYPES: tuple[str, ...] = ("informative",)


class ReviewError(RuntimeError):
    """Raised when a review decision cannot be applied safely."""


def apply_review_action(
    *,
    review_records: list[dict[str, Any]],
    action: str,
    attachment_ids: list[int] | None = None,
    all_records: bool = False,
    reviewer: str = "",
    notes: str = "",
    final_alt_text: str | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    _validate_targets(attachment_ids=attachment_ids, all_records=all_records)
    _validate_action(action=action, final_alt_text=final_alt_text)

    targeted = _select_records(
        review_records=review_records,
        attachment_ids=attachment_ids,
        all_records=all_records,
    )
    reviewed_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    updated = 0
    skipped = 0
    for record in targeted:
        review = record.setdefault("review", {})
        already_reviewed = review.get("status") == "reviewed"
        if already_reviewed and not overwrite:
            skipped += 1
            continue

        resolved_alt_text = _resolve_final_alt_text(
            record=record,
            action=action,
            explicit_final_alt_text=final_alt_text,
        )
        record["review"] = {
            "status": "reviewed",
            "action": action,
            "reviewer": reviewer.strip(),
            "reviewed_at": reviewed_at,
            "notes": notes.strip(),
            "final_alt_text": resolved_alt_text,
        }
        updated += 1

    return {
        "record_count": len(review_records),
        "targeted": len(targeted),
        "updated": updated,
        "skipped": skipped,
        "action": action,
    }


def auto_review_high_confidence(
    *,
    review_records: list[dict[str, Any]],
    attachment_ids: list[int] | None = None,
    reviewer: str = "auto-review",
    overwrite: bool = False,
) -> dict[str, Any]:
    targeted = _select_auto_review_records(
        review_records=review_records,
        attachment_ids=attachment_ids,
    )
    reviewed_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    updated = 0
    skipped = 0
    for record in targeted:
        review = record.setdefault("review", {})
        already_reviewed = review.get("status") == "reviewed"
        if already_reviewed and not overwrite:
            skipped += 1
            continue

        suggestion = record.get("suggestion") or {}
        record["review"] = {
            "status": "reviewed",
            "action": "approve",
            "reviewer": reviewer,
            "reviewed_at": reviewed_at,
            "notes": (
                "Auto-approved high-confidence informative suggestion."
            ),
            "final_alt_text": str(suggestion.get("candidate_alt_text") or ""),
        }
        updated += 1

    return {
        "record_count": len(review_records),
        "targeted": len(targeted),
        "updated": updated,
        "skipped": skipped,
    }


def _validate_targets(*, attachment_ids: list[int] | None, all_records: bool) -> None:
    if all_records and attachment_ids:
        raise ReviewError("Choose either --attachment-ids or --all-records, not both")
    if not all_records and not attachment_ids:
        raise ReviewError("Provide --attachment-ids or use --all-records")


def _validate_action(*, action: str, final_alt_text: str | None) -> None:
    if action == "edit" and final_alt_text is None:
        raise ReviewError("--final-alt-text is required when --action edit is used")


def _select_records(
    *,
    review_records: list[dict[str, Any]],
    attachment_ids: list[int] | None,
    all_records: bool,
) -> list[dict[str, Any]]:
    if all_records:
        return review_records

    wanted_ids = set(attachment_ids or [])
    matched = [
        record for record in review_records if int(record.get("attachment_id", -1)) in wanted_ids
    ]
    found_ids = {int(record.get("attachment_id", -1)) for record in matched}
    missing_ids = sorted(wanted_ids - found_ids)
    if missing_ids:
        raise ReviewError(
            "Attachment IDs not found in input report: "
            + ", ".join(str(attachment_id) for attachment_id in missing_ids)
        )
    return matched


def _resolve_final_alt_text(
    *,
    record: dict[str, Any],
    action: str,
    explicit_final_alt_text: str | None,
) -> str:
    if action == "skip":
        return ""

    if explicit_final_alt_text is not None:
        return explicit_final_alt_text

    suggestion = record.get("suggestion") or {}
    candidate_alt_text = str(suggestion.get("candidate_alt_text") or "")
    if action == "approve":
        if suggestion.get("status") != "generated":
            raise ReviewError(
                "Approve requires a generated suggestion or an explicit --final-alt-text override"
            )
        return candidate_alt_text

    raise ReviewError(f"Unsupported review action: {action}")


def _select_auto_review_records(
    *,
    review_records: list[dict[str, Any]],
    attachment_ids: list[int] | None,
) -> list[dict[str, Any]]:
    eligible_records = [
        record for record in review_records if is_auto_approvable_suggestion(record)
    ]

    if attachment_ids is None:
        return eligible_records

    wanted_ids = set(attachment_ids)
    matched = [
        record for record in eligible_records if int(record.get("attachment_id", -1)) in wanted_ids
    ]
    found_ids = {int(record.get("attachment_id", -1)) for record in matched}
    missing_ids = sorted(wanted_ids - found_ids)
    if missing_ids:
        raise ReviewError(
            "Auto-approvable attachment IDs not found in input report: "
            + ", ".join(str(attachment_id) for attachment_id in missing_ids)
        )
    return matched


def is_auto_approvable_suggestion(record: dict[str, Any]) -> bool:
    suggestion = record.get("suggestion") or {}
    candidate_alt_text = str(suggestion.get("candidate_alt_text") or "").strip()
    warnings = suggestion.get("warnings") or []
    return (
        suggestion.get("status") == "generated"
        and suggestion.get("candidate_type") in AUTO_APPROVE_CANDIDATE_TYPES
        and suggestion.get("confidence") == "high"
        and not suggestion.get("requires_manual_review")
        and not suggestion.get("long_description_needed")
        and not suggestion.get("error")
        and not warnings
        and bool(candidate_alt_text)
    )
