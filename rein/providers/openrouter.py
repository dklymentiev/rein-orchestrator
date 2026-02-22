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

    def call(self, prompt: str, stage: str = ""):
        import time as _time
        from .base import UsageStats, calculate_cost

        self.logger(f"OPENROUTER CALL | stage={stage} | model={self.model}")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        t0 = _time.monotonic()
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
        duration_ms = int((_time.monotonic() - t0) * 1000)

        data = response.json()
        result = data["choices"][0]["message"]["content"]

        resp_usage = data.get("usage", {})
        input_tokens = resp_usage.get("prompt_tokens", 0)
        output_tokens = resp_usage.get("completion_tokens", 0)
        cost = calculate_cost(self.model, input_tokens, output_tokens)

        usage = UsageStats(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
            model=self.model,
            provider="openrouter",
            duration_ms=duration_ms,
        )

        self.logger(f"OPENROUTER RESPONSE | stage={stage} | length={len(result)} | tokens={usage.total_tokens} | cost=${cost:.4f}")
        return result, usage

    @property
    def provider_name(self) -> str:
        return "openrouter"
