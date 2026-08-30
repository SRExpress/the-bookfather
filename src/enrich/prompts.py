"""Shared prompt fragments so every feature states the JSON contract the same way."""

from __future__ import annotations

JSON_CONTRACT = (
    "Respond with a SINGLE valid JSON object and nothing else - no prose, no markdown, "
    "no code fence. Use exactly the keys specified; do not add keys. If the blurb is too "
    "thin to answer well, still return the object and lower every confidence value."
)

SPOILER_FREE = (
    "SPOILER-FREE: do not reveal twists, the ending, character deaths, or any reveal from "
    "the back half of the book. Describe premise, setup, tone, and stakes only."
)

EVIDENCE_RULE = (
    "'evidence_span' must be a short verbatim quote (<= 200 chars) copied from the blurb "
    "above that most supports your answer."
)


def system_prompt(task: str, schema: str, *, spoiler_free: bool = False, rubric: str = "") -> str:
    """Assemble a system prompt: task -> optional rubric -> output schema -> contract."""
    parts = [task.strip()]
    if spoiler_free:
        parts.append(SPOILER_FREE)
    if rubric:
        parts.append("RUBRIC:\n" + rubric.strip())
    parts.append("OUTPUT SCHEMA (JSON):\n" + schema.strip())
    parts.append(EVIDENCE_RULE)
    parts.append(JSON_CONTRACT)
    return "\n\n".join(parts)


def user_prompt(book_block: str) -> str:
    return "Here is the book:\n\n" + book_block
