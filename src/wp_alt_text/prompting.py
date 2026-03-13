from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

PROMPT_VERSION = "2026-03-13"
MANUAL_REVIEW_CANDIDATE_TYPES: tuple[str, ...] = (
    "decorative",
    "functional",
    "text_heavy",
    "complex",
)


@dataclass(frozen=True)
class RoleRule:
    role: str
    when_to_use: str
    alt_strategy: str
    review_priority: str
    output_requirements: tuple[str, ...]


ROLE_RULES: tuple[RoleRule, ...] = (
    RoleRule(
        role="decorative",
        when_to_use=(
            "Use when the image adds no information, duplicates adjacent text, or exists only "
            "for layout, ambiance, branding chrome, or visual polish."
        ),
        alt_strategy="Return an empty alt string.",
        review_priority="high",
        output_requirements=(
            "suggested_alt_text must be an empty string",
            "candidate_type must be decorative",
            "mark requires_manual_review true if the image might have hidden function or text",
        ),
    ),
    RoleRule(
        role="functional",
        when_to_use=(
            "Use when the image is the control, link target, button, badge, or icon that initiates "
            "an action or navigation."
        ),
        alt_strategy="Describe the action, destination, or purpose, not the visual appearance.",
        review_priority="high",
        output_requirements=(
            "focus on what happens when activated",
            "do not describe colors, shapes, or styling unless essential to purpose",
            "include visible label text only if it is part of the function users need",
        ),
    ),
    RoleRule(
        role="informative",
        when_to_use=(
            "Use when the image adds simple context or meaning that can be conveyed in a short phrase "
            "or sentence."
        ),
        alt_strategy="Write a concise context-aware description of the meaning conveyed.",
        review_priority="medium",
        output_requirements=(
            "prefer the information the page is trying to communicate",
            "avoid boilerplate such as 'image of' or 'photo of' unless the medium itself matters",
            "do not repeat surrounding text unless it changes meaning",
        ),
    ),
    RoleRule(
        role="text_heavy",
        when_to_use=(
            "Use when the image contains meaningful text, a screenshot with UI copy, a poster, flyer, "
            "sign, or logo text that users need to understand."
        ),
        alt_strategy=(
            "Preserve the meaningful visible text word-for-word when practical, and add only the "
            "minimum context needed to explain function or format."
        ),
        review_priority="high",
        output_requirements=(
            "transcribe important visible text accurately",
            "ignore purely decorative visual effects",
            "mark requires_manual_review true when legibility or completeness is uncertain",
        ),
    ),
    RoleRule(
        role="complex",
        when_to_use=(
            "Use when the image contains substantial structured information such as charts, maps, "
            "diagrams, dense screenshots, tables, or multi-part infographics."
        ),
        alt_strategy=(
            "Provide a short alt summary of the image's purpose and set long_description_needed true."
        ),
        review_priority="critical",
        output_requirements=(
            "keep alt text brief and high-level",
            "do not attempt to compress every data point into alt text",
            "identify that a separate long description or human-authored summary is needed",
        ),
    ),
)

DECISION_PRIORITY: tuple[str, ...] = (
    "decorative",
    "functional",
    "text_heavy",
    "complex",
    "informative",
)

STYLE_RULES: tuple[str, ...] = (
    "Use the same language as the surrounding page content when it is clear from the context.",
    "Keep alt text concise and focused on equivalent purpose, not exhaustive appearance.",
    "Do not start with phrases like 'image of', 'photo of', 'graphic of', or 'screenshot of' unless that medium matters to understanding.",
    "Do not repeat surrounding text when the image is redundant to nearby copy.",
    "Prefer empty alt for decorative or fully redundant images.",
    "If the image functions as a control or link, describe the function or destination.",
    "If the image contains meaningful text, preserve that text accurately.",
    "If the image is complex, produce only a short summary in alt text and flag the need for a longer description.",
    "If confidence is low or the role is ambiguous, require manual review.",
)

OUTPUT_SCHEMA: dict[str, str] = {
    "candidate_type": "One of decorative, functional, informative, text_heavy, complex.",
    "suggested_alt_text": "String. Empty for decorative images.",
    "confidence": "One of low, medium, high.",
    "requires_manual_review": "Boolean.",
    "long_description_needed": "Boolean.",
    "reasoning_summary": "One or two sentences explaining the decision in plain language.",
    "warnings": "Array of short strings for risks such as ambiguous function, unreadable text, possible redundancy, or possible hard-coded front-end alt.",
}


def prompt_spec() -> dict[str, Any]:
    return {
        "prompt_version": PROMPT_VERSION,
        "decision_priority": list(DECISION_PRIORITY),
        "manual_review_candidate_types": list(MANUAL_REVIEW_CANDIDATE_TYPES),
        "style_rules": list(STYLE_RULES),
        "role_rules": [
            {
                "role": rule.role,
                "when_to_use": rule.when_to_use,
                "alt_strategy": rule.alt_strategy,
                "review_priority": rule.review_priority,
                "output_requirements": list(rule.output_requirements),
            }
            for rule in ROLE_RULES
        ],
        "output_schema": OUTPUT_SCHEMA,
    }


def build_suggestion_messages(review_record: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": build_system_prompt()},
        {"role": "user", "content": build_user_prompt(review_record)},
    ]


def build_system_prompt() -> str:
    return (
        "You generate review-first alt-text suggestions for WordPress images. "
        "Follow WCAG and WAI image guidance strictly.\n\n"
        "Decision order:\n"
        f"{_format_priority()}\n\n"
        "Style rules:\n"
        f"{_format_lines(STYLE_RULES)}\n\n"
        "Role rules:\n"
        f"{_format_role_rules()}\n\n"
        "Return valid JSON only with this schema:\n"
        f"{json.dumps(OUTPUT_SCHEMA, ensure_ascii=True, indent=2)}\n\n"
        "Policy overrides:\n"
        f"- Always set requires_manual_review true for candidate_type values in "
        f"{', '.join(MANUAL_REVIEW_CANDIDATE_TYPES)}.\n\n"
        "Never invent page facts that are not supported by the image or the provided context. "
        "When uncertain, lower confidence, add warnings, and require manual review."
    )


def build_user_prompt(review_record: dict[str, Any]) -> str:
    context_matches = review_record.get("context_matches") or []
    simplified_matches = [
        {
            "content_type": match.get("content_type", ""),
            "title": match.get("title", ""),
            "link": match.get("link", ""),
            "content_source": match.get("content_source", ""),
            "match_reason": match.get("match_reason", ""),
            "snippet": match.get("snippet", ""),
        }
        for match in context_matches[:5]
    ]

    payload = {
        "prompt_version": PROMPT_VERSION,
        "site_url": review_record.get("site_url", ""),
        "attachment_id": review_record.get("attachment_id", ""),
        "source_url": review_record.get("source_url", ""),
        "attachment_title": review_record.get("attachment_title", ""),
        "attachment_slug": review_record.get("attachment_slug", ""),
        "mime_type": review_record.get("mime_type", ""),
        "current_alt_text": review_record.get("current_alt_text", ""),
        "usage_count": review_record.get("usage_count", 0),
        "context_matches": simplified_matches,
        "instructions": {
            "task": (
                "Classify the image role, propose alt text if appropriate, and flag whether manual "
                "review or a long description is required."
            ),
            "special_cases": [
                "If decorative or fully redundant, return an empty alt string.",
                "If functional, describe the destination or action.",
                "If text-heavy, preserve meaningful visible text accurately.",
                "If complex, provide only a short summary and set long_description_needed true.",
            ],
        },
    }
    return json.dumps(payload, ensure_ascii=True, indent=2)


def _format_priority() -> str:
    return "\n".join(
        f"{index}. {role}" for index, role in enumerate(DECISION_PRIORITY, start=1)
    )


def _format_lines(lines: tuple[str, ...]) -> str:
    return "\n".join(f"- {line}" for line in lines)


def _format_role_rules() -> str:
    parts: list[str] = []
    for rule in ROLE_RULES:
        parts.append(
            "\n".join(
                [
                    f"- {rule.role}",
                    f"  when_to_use: {rule.when_to_use}",
                    f"  alt_strategy: {rule.alt_strategy}",
                    f"  review_priority: {rule.review_priority}",
                    f"  output_requirements: {'; '.join(rule.output_requirements)}",
                ]
            )
        )
    return "\n".join(parts)
