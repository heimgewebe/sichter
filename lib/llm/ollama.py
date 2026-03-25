"""Ollama HTTP provider — calls the local Ollama API."""
from __future__ import annotations

import json
import urllib.request
from urllib.error import URLError


class OllamaProvider:
    """Calls a locally running Ollama instance via its REST API."""

    provider_name = "ollama"

    def __init__(self, base_url: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model

    def complete(self, prompt: str, max_tokens: int = 2000) -> tuple[str, int]:
        payload = json.dumps(
            {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {"num_predict": max_tokens},
            }
        ).encode()

        req = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read())
        except URLError as exc:
            raise RuntimeError(f"Ollama nicht erreichbar ({self.base_url}): {exc}") from exc

        text = str(data.get("response", "")).strip()
        prompt_tokens = int(data.get("prompt_eval_count", 0))
        gen_tokens = int(data.get("eval_count", 0))
        return text, prompt_tokens + gen_tokens
