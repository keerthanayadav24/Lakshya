"""Unit tests for Gemini Flash LLM client wrapper and safety rules."""

import logging
from unittest.mock import MagicMock, patch

import pytest

from llm.gemini import GeminiClient, GeminiError


def test_gemini_missing_api_key_raises_error() -> None:
    """Test initializing GeminiClient without an API key raises GeminiError."""
    with pytest.raises(GeminiError, match="Gemini API key is required"):
        GeminiClient(api_key="")


def test_generate_json_success() -> None:
    """Test successful JSON generation via mocked Gemini provider."""
    client = GeminiClient(api_key="fake_test_key_123")
    mock_genai_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = '{"tasks": [{"title": "Read Chapter 1"}]}'
    mock_genai_client.models.generate_content.return_value = mock_response

    with patch.object(client, "_get_client", return_value=mock_genai_client):
        result = client.generate_json(
            system_instruction="Extract tasks",
            user_input="Syllabus content...",
        )
        assert result == '{"tasks": [{"title": "Read Chapter 1"}]}'
        mock_genai_client.models.generate_content.assert_called_once()


def test_draft_message_success() -> None:
    """Test successful message drafting via mocked Gemini provider."""
    client = GeminiClient(api_key="fake_test_key_123")
    mock_genai_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "Hello! Here is your updated study plan."
    mock_genai_client.models.generate_content.return_value = mock_response

    with patch.object(client, "_get_client", return_value=mock_genai_client):
        result = client.draft_message(
            instruction="Draft a friendly notification",
        )
        assert result == "Hello! Here is your updated study plan."


def test_provider_error_becomes_gemini_error() -> None:
    """Test provider exception is converted to controlled GeminiError."""
    client = GeminiClient(api_key="fake_secret_key_456")
    mock_genai_client = MagicMock()
    err_msg = "API Quota Exceeded"
    mock_genai_client.models.generate_content.side_effect = Exception(err_msg)

    with patch.object(client, "_get_client", return_value=mock_genai_client):
        with pytest.raises(GeminiError, match="Gemini generation failed"):
            client.generate_json(
                system_instruction="System",
                user_input="Input",
            )


def test_api_key_not_exposed_in_errors_or_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify secret API keys are never exposed in error text or logs."""
    secret_key = "super_secret_gemini_key_999"
    caplog.set_level(logging.DEBUG)

    client = GeminiClient(api_key=secret_key)
    with patch("google.genai.Client", side_effect=Exception("Connection Failed")):
        with pytest.raises(GeminiError) as exc_info:
            client.generate_json("sys", "user")

        # Verify key is not present in exception message
        assert secret_key not in str(exc_info.value)

    # Verify key is not present in logged output
    for record in caplog.records:
        assert secret_key not in record.getMessage()


def test_gemini_has_no_calendar_mutation_capabilities() -> None:
    """Verify GeminiClient has NO methods to mutate calendar events."""
    client = GeminiClient(api_key="fake_key")
    forbidden_methods = [
        "create_study_block",
        "update_study_block",
        "delete_study_block",
        "create_event",
        "delete_event",
        "update_event",
        "calendar",
    ]
    for method_name in forbidden_methods:
        msg = f"GeminiClient must not have {method_name}"
        assert not hasattr(client, method_name), msg
