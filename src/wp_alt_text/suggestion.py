from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from openai import OpenAI
from openai import OpenAIError
from pydantic import BaseModel, Field

from .config import OpenAISettings
from .prompting import (
    MANUAL_REVIEW_CANDIDATE_TYPES,
    PROMPT_VERSION,
    build_system_prompt,
    build_user_prompt,
)


class SuggestionError(RuntimeError):
    """Raised when suggestion generation cannot complete for a record."""


class SuggestionPayload(BaseModel):
    candidate_type: Literal[
        "decorative",
        "functional",
        "informative",
        "text_heavy",
        "complex",
    ]
    suggested_alt_text: str
    confidence: Literal["low", "medium", "high"]
    requires_manual_review: bool
    long_description_needed: bool
    reasoning_summary: str
    warnings: list[str] = Field(default_factory=list)


class SuggestionClient:
    def __init__(self, settings: OpenAISettings) -> None:
        self.settings = settings
        self.client = OpenAI(api_key=settings.openai_api_key)

    def generate_suggestion(
        self,
        review_record: dict[str, Any],
        *,
        model: str | None = None,
    ) -> dict[str, Any]:
        source_url = str(review_record.get("source_url") or "").strip()
        if not source_url:
            raise SuggestionError("Review record is missing source_url")

        try:
            response = self.client.responses.parse(
                model=model or self.settings.openai_model,
                instructions=build_system_prompt(),
                input=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": build_user_prompt(review_record),
                            },
                            {
                                "type": "input_image",
                                "image_url": source_url,
                                "detail": "auto",
                            },
                        ],
                    }
                ],
                text_format=SuggestionPayload,
                max_output_tokens=500,
                store=False,
            )
        except OpenAIError as exc:
            raise SuggestionError(str(exc)) from exc

        parsed = response.output_parsed
        if parsed is None:
            raise SuggestionError("Model returned no parsed suggestion payload")

        generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        warnings = list(parsed.warnings)
        requires_manual_review = parsed.requires_manual_review
        if parsed.candidate_type in MANUAL_REVIEW_CANDIDATE_TYPES:
            requires_manual_review = True
            policy_warning = (
                "Manual review required by policy for "
                f"{parsed.candidate_type} suggestions."
            )
            if policy_warning not in warnings:
                warnings.append(policy_warning)

        return {
            "status": "generated",
            "candidate_alt_text": parsed.suggested_alt_text,
            "candidate_type": parsed.candidate_type,
            "confidence": parsed.confidence,
            "rationale": parsed.reasoning_summary,
            "warnings": warnings,
            "requires_manual_review": requires_manual_review,
            "long_description_needed": parsed.long_description_needed,
            "model": response.model,
            "prompt_version": PROMPT_VERSION,
            "generated_at": generated_at,
            "error": "",
        }


def apply_suggestions(
    *,
    review_records: list[dict[str, Any]],
    suggestion_client: SuggestionClient,
    model: str | None = None,
    limit: int | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    generated = 0
    skipped = 0
    failed = 0

    for record in review_records:
        suggestion = record.setdefault("suggestion", {})
        already_generated = suggestion.get("status") == "generated"
        if already_generated and not overwrite:
            skipped += 1
            continue

        if limit is not None and generated >= limit:
            skipped += 1
            continue

        try:
            record["suggestion"] = suggestion_client.generate_suggestion(record, model=model)
            generated += 1
        except SuggestionError as exc:
            failed += 1
            record["suggestion"] = {
                "status": "error",
                "candidate_alt_text": "",
                "candidate_type": "",
                "confidence": "",
                "rationale": "",
                "warnings": [],
                "requires_manual_review": True,
                "long_description_needed": False,
                "model": model or suggestion_client.settings.openai_model,
                "prompt_version": PROMPT_VERSION,
                "generated_at": "",
                "error": str(exc),
            }

    return {
        "record_count": len(review_records),
        "generated": generated,
        "skipped": skipped,
        "failed": failed,
    }
