"""Strict output validation guard for LLM generated JSON data."""

import json

from pydantic import ValidationError

from llm.schemas import LLMTaskBreakdown


class OutputValidationError(Exception):
    """Raised when LLM output fails JSON parsing or schema validation."""

    pass


def parse_task_breakdown(raw_json: str) -> LLMTaskBreakdown:
    """Strictly parse raw LLM JSON string into LLMTaskBreakdown schema.

    Rejects markdown code fences, malformed JSON, missing fields, or invalid schemas.
    No partial parsing or fallback coercion is performed.
    """
    if not raw_json or not raw_json.strip():
        raise OutputValidationError("LLM response is empty")

    trimmed = raw_json.strip()

    # Reject markdown code fences
    if "```" in trimmed:
        raise OutputValidationError(
            "LLM output contains markdown code fences, which are not permitted"
        )

    # Strict JSON parsing
    try:
        data = json.loads(trimmed)
    except json.JSONDecodeError as e:
        raise OutputValidationError(f"Invalid JSON string from LLM: {e}") from e

    if not isinstance(data, dict):
        raise OutputValidationError("LLM output JSON must be a top-level JSON object")

    # Strict Pydantic schema validation
    try:
        return LLMTaskBreakdown.model_validate(data)
    except ValidationError as e:
        raise OutputValidationError(f"LLM output schema validation failed: {e}") from e
