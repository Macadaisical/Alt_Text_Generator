# Alt Text Prompt Rules

This file records the prompt contract and accessibility decision rules that the future `suggest` stage will use.

## Decision Order

1. Decorative
2. Functional
3. Text-heavy
4. Complex
5. Informative

This order is intentional. It reduces the most common failure modes:

- decorative images getting unnecessary descriptions
- linked or button images being described visually instead of functionally
- screenshots, posters, and logos losing meaningful text
- charts and diagrams being overcompressed into misleading short alt text

## Role Rules

### Decorative
- Use when the image is only visual polish, spacing, ambiance, or redundant to adjacent text.
- Output rule: empty alt text.
- Escalate to human review if the image may contain meaningful text or hidden function.

### Functional
- Use when the image itself is a control, button, badge, or link target.
- Output rule: describe the action, destination, or purpose.
- Avoid visual-only descriptions unless appearance changes meaning.

### Informative
- Use when the image adds simple meaning that can be expressed briefly.
- Output rule: concise context-aware description of the meaning conveyed.
- Avoid repeating surrounding text without adding value.

### Text-heavy
- Use for screenshots with copy, flyers, posters, notices, signs, logos with meaningful text, and other images where reading text is essential.
- Output rule: preserve meaningful visible text accurately and add only the minimum context needed.
- Escalate to human review when text is cropped, blurry, partial, or likely incomplete.

### Complex
- Use for charts, maps, diagrams, tables, dense screenshots, and multi-part infographics.
- Output rule: short summary in alt text plus a flag that a longer description is needed.
- Do not try to compress all data points into alt text.

## Style Rules

- Match the page language when the context makes it clear.
- Keep alt text concise and purpose-driven.
- Avoid boilerplate such as `image of` unless the medium matters.
- Prefer empty alt text when the image is decorative or fully redundant.
- Preserve meaningful visible text when text is essential.
- Require manual review when confidence is low or the role is ambiguous.

## Structured Output Shape

The prompt contract expects:

- `candidate_type`
- `suggested_alt_text`
- `confidence`
- `requires_manual_review`
- `long_description_needed`
- `reasoning_summary`
- `warnings`

## Source Basis

- W3C WAI Image Tutorial decision tree: https://www.w3.org/WAI/tutorials/images/decision-tree/
- W3C WAI decorative images: https://www.w3.org/WAI/tutorials/images/decorative/
- W3C WAI functional images: https://www.w3.org/WAI/tutorials/images/functional/
- W3C WAI images of text: https://www.w3.org/WAI/tutorials/images/textual/
- W3C WAI complex images: https://www.w3.org/WAI/tutorials/images/complex/
- WCAG 2.2 Success Criterion 1.1.1 Non-text Content: https://www.w3.org/TR/WCAG22/#non-text-content
- Section 508 alt text guidance: https://www.section508.gov/create/alternative-text/
