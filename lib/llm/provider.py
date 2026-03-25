"""LLM provider protocol definition."""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    """Minimal interface that every LLM backend must satisfy."""

    provider_name: str
    model: str

    def complete(self, prompt: str, max_tokens: int = 2000) -> tuple[str, int]:
        """Send *prompt* to the model and return (response_text, tokens_used).

        Args:
            prompt: The prompt text to send.
            max_tokens: Soft cap on how many tokens to generate.

        Returns:
            Tuple of (response_text, tokens_used).
        """
        ...
