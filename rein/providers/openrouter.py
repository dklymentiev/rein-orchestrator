"""
OpenRouter provider - proxy for Claude, GPT, Llama, and 100+ models.

Config:
    provider: openrouter
    model: anthropic/claude-3.5-sonnet  # or openai/gpt-4o, meta-llama/llama-3.1, etc.

Env:
    OPENROUTER_API_KEY: API key (required)
"""
import os
from typing import Optional, Callable

import requests

from .base import Provider


class OpenRouterProvider(Provider):
    """OpenRouter API provider (multi-model proxy)."""

    DEFAULT_MODEL = "anthropic/claude-sonnet-4"
    API_URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(
        self,
        model: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.7,
        logger: Optional[Callable[[str], None]] = None,
        api_key: str = "",
        **kwargs
    ):
        super().__init__(
            model=model or self.DEFAULT_MODEL,
            max_tokens=max_tokens,
            temperature=temperature,
            logger=logger,
        )
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")

    def call(self, prompt: str, stage: str = "") -> str:
        self.logger(f"OPENROUTER CALL | stage={stage} | model={self.model}")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        response = requests.post(
            self.API_URL,
            headers=headers,
            json={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": self.max_tokens,
                "temperature": self.temperature,
            },
            timeout=120,
        )
        response.raise_for_status()

        result = response.json()["choices"][0]["message"]["content"]
        self.logger(f"OPENROUTER RESPONSE | stage={stage} | length={len(result)}")
        return result

    @property
    def provider_name(self) -> str:
        return "openrouter"
