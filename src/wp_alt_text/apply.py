from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .review import ReviewError, auto_review_high_confidence
from .wordpress import WordPressClient, WordPressError


class ApplyError(RuntimeError):
    """Raised when approved review records cannot be applied safely."""


def apply_reviewed_alt_text(
    *,
    review_records: list[dict[str, Any]],
    wordpress_client: WordPressClient,
    attachment_ids: list[int] | None = None,
    all_approved: bool = False,
    auto_apply_high_confidence: bool = False,
    dry_run: bool = True,
    overwrite: bool = False,
) -> dict[str, Any]:
    _validate_targets(
        attachment_ids=attachment_ids,
        all_approved=all_approved,
        auto_apply_high_confidence=auto_apply_high_confidence,
    )
    auto_review_meta = {
        "targeted": 0,
        "updated": 0,
        "skipped": 0,
    }
    if auto_apply_high_confidence:
        try:
            auto_review_meta = auto_review_high_confidence(
                review_records=review_records,
                attachment_ids=attachment_ids,
                overwrite=overwrite,
            )
        except ReviewError as exc:
            raise ApplyError(str(exc)) from exc

    targeted_records = _select_approved_records(
        review_records=review_records,
        attachment_ids=attachment_ids,
        all_approved=all_approved or (auto_apply_high_confidence and attachment_ids is None),
    )

    applied = 0
    skipped = 0
    failed = 0
    dry_run_count = 0

    for record in targeted_records:
        apply_state = record.setdefault("apply", {})
        if apply_state.get("status") == "applied" and not overwrite:
            skipped += 1
            continue

        target_alt_text = _target_alt_text(record)
        timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

        if dry_run:
            record["apply"] = {
                "status": "dry_run",
                "target_alt_text": target_alt_text,
                "applied_at": timestamp,
                "error": "",
            }
            dry_run_count += 1
            continue

        try:
            result = wordpress_client.update_media_alt_text(
                attachment_id=int(record.get("attachment_id", 0)),
                alt_text=target_alt_text,
            )
            record["apply"] = {
                "status": "applied",
                "target_alt_text": result["alt_text"],
                "applied_at": timestamp,
                "error": "",
            }
            applied += 1
        except WordPressError as exc:
            record["apply"] = {
                "status": "error",
                "target_alt_text": target_alt_text,
                "applied_at": "",
                "error": str(exc),
            }
            failed += 1

    return {
        "record_count": len(review_records),
        "targeted": len(targeted_records),
        "applied": applied,
        "dry_run": dry_run_count,
        "skipped": skipped,
        "failed": failed,
        "auto_review_targeted": auto_review_meta["targeted"],
        "auto_reviewed": auto_review_meta["updated"],
        "auto_review_skipped": auto_review_meta["skipped"],
    }


def _validate_targets(
    *,
    attachment_ids: list[int] | None,
    all_approved: bool,
    auto_apply_high_confidence: bool,
) -> None:
    if all_approved and attachment_ids:
        raise ApplyError("Choose either --attachment-ids or --all-approved, not both")
    if auto_apply_high_confidence and all_approved:
        raise ApplyError(
            "--auto-apply-high-confidence cannot be combined with --all-approved"
        )
    if not auto_apply_high_confidence and not all_approved and not attachment_ids:
        raise ApplyError("Provide --attachment-ids or use --all-approved")


def _select_approved_records(
    *,
    review_records: list[dict[str, Any]],
    attachment_ids: list[int] | None,
    all_approved: bool,
) -> list[dict[str, Any]]:
    eligible_records = []
    for record in review_records:
        review = record.get("review") or {}
        if review.get("status") != "reviewed":
            continue
        if review.get("action") not in {"approve", "edit"}:
            continue
        eligible_records.append(record)

    if all_approved:
        return eligible_records

    wanted_ids = set(attachment_ids or [])
    matched = [
        record for record in eligible_records if int(record.get("attachment_id", -1)) in wanted_ids
    ]
    found_ids = {int(record.get("attachment_id", -1)) for record in matched}
    missing_ids = sorted(wanted_ids - found_ids)
    if missing_ids:
        raise ApplyError(
            "Approved reviewed attachment IDs not found in input report: "
            + ", ".join(str(attachment_id) for attachment_id in missing_ids)
        )
    return matched


def _target_alt_text(record: dict[str, Any]) -> str:
    review = record.get("review") or {}
    final_alt_text = review.get("final_alt_text")
    if final_alt_text is None:
        raise ApplyError(
            f"Attachment {record.get('attachment_id')} is missing review.final_alt_text"
        )
    return str(final_alt_text)
