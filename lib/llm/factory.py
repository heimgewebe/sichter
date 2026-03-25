"""Factory — creates the right LLM backend from policy/LLM config dict."""
from __future__ import annotations

import os

from lib.llm.ollama import OllamaProvider
from lib.llm.openai import OpenAIProvider


def get_provider(llm_config: dict | None):
    """Return an LLMProvider based on the ``llm`` section of policy.yml."""
    cfg = llm_config or {}
    provider_name = str(cfg.get("provider", "ollama")).lower()
    model = str(cfg.get("model", "qwen2.5-coder:7b"))

    if provider_name == "ollama":
        base_url = str(cfg.get("base_url", "http://localhost:11434"))
        return OllamaProvider(base_url=base_url, model=model)

    if provider_name in {"openai", "vllm", "local"}:
        api_key = os.environ.get("OPENAI_API_KEY", "")
        base_url = str(cfg.get("base_url", "https://api.openai.com/v1"))
        return OpenAIProvider(api_key=api_key, model=model, base_url=base_url)

    raise ValueError(f"Unbekannter LLM-Provider: {provider_name!r}")
