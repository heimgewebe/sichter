"""OpenAI-compatible HTTP provider (also works with vLLM / local endpoints)."""
from __future__ import annotations

import json
import os
import urllib.request
from urllib.error import HTTPError, URLError


class OpenAIProvider:
    """Sends requests to an OpenAI-compatible chat completions endpoint."""

    provider_name = "openai"

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._api_key = api_key

    def complete(self, prompt: str, max_tokens: int = 2000) -> tuple[str, int]:
        payload = json.dumps(
            {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
            }
        ).encode()

        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read())
        except HTTPError as exc:
            body = exc.read().decode(errors="replace")[:200]
            raise RuntimeError(
                f"OpenAI API Fehler {exc.code}: {body}"
            ) from exc
        except URLError as exc:
            raise RuntimeError(f"OpenAI-Endpunkt nicht erreichbar: {exc}") from exc

        text = str(data["choices"][0]["message"]["content"]).strip()
        tokens_used = int(data.get("usage", {}).get("total_tokens", 0))
        return text, tokens_used
