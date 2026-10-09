"""Gemini Flash client wrapper for Lakshya syllabus breakdown and messaging."""

from typing import Any

from google import genai

from config import settings


class GeminiError(Exception):
    """Raised when Gemini API request or initialization fails."""

    pass


class GeminiClient:
    """Wrapper around Google Gemini API for task breakdown and messaging."""

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str = "gemini-2.5-flash",
    ) -> None:
        key = api_key or settings.gemini_api_key
        if not key or not key.strip():
            raise GeminiError(
                "Gemini API key is required. Set GEMINI_API_KEY environment variable."
            )
        self.api_key = key
        self.model_name = model_name
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                self._client = genai.Client(api_key=self.api_key)
            except Exception as e:
                # Do not expose API key in error messages
                raise GeminiError(
                    f"Failed to initialize Gemini client: {type(e).__name__}"
                ) from e
        return self._client

    def generate_json(
        self,
        system_instruction: str,
        user_input: str,
    ) -> str:
        """Generate structured JSON output from Gemini Flash."""
        try:
            client = self._get_client()
            prompt = (
                f"System Instruction: {system_instruction}\nUser Input: {user_input}"
            )
            response = client.models.generate_content(
                model=self.model_name,
                contents=prompt,
            )
            if not response or not getattr(response, "text", None):
                raise GeminiError("Empty response received from Gemini model")
            return str(response.text)
        except Exception as e:
            if isinstance(e, GeminiError):
                raise
            raise GeminiError(f"Gemini generation failed: {type(e).__name__}") from e

    def draft_message(
        self,
        instruction: str,
    ) -> str:
        """Draft a short human-readable message using Gemini Flash."""
        try:
            client = self._get_client()
            response = client.models.generate_content(
                model=self.model_name,
                contents=instruction,
            )
            if not response or not getattr(response, "text", None):
                raise GeminiError("Empty response received from Gemini model")
            return str(response.text)
        except Exception as e:
            if isinstance(e, GeminiError):
                raise
            raise GeminiError(f"Gemini drafting failed: {type(e).__name__}") from e
