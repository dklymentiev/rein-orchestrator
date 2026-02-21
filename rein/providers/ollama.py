"""
Ollama provider - local models via Ollama REST API.

Config:
    provider: ollama
    model: llama3.1  # or mistral, codellama, deepseek-r1, etc.

Env:
    OLLAMA_URL: Base URL (default: http://localhost:11434)
"""
import os
from typing import Optional, Callable

import requests

from .base import Provider


class OllamaProvider(Provider):
    """Ollama local model provider."""

    DEFAULT_MODEL = "llama3.1"
    DEFAULT_URL = "http://localhost:11434"

    def __init__(
        self,
        model: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.7,
        logger: Optional[Callable[[str], None]] = None,
        base_url: str = "",
        **kwargs
    ):
        super().__init__(
            model=model or self.DEFAULT_MODEL,
            max_tokens=max_tokens,
            temperature=temperature,
            logger=logger,
        )
        self.base_url = base_url or os.environ.get("OLLAMA_URL", self.DEFAULT_URL)

    def call(self, prompt: str, stage: str = ""):
        import time as _time
        from .base import UsageStats

        self.logger(f"OLLAMA CALL | stage={stage} | model={self.model} | url={self.base_url}")

        t0 = _time.monotonic()
        response = requests.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {
                    "num_predict": self.max_tokens,
                    "temperature": self.temperature,
                },
            },
            timeout=300,  # Local models can be slow
        )
        response.raise_for_status()
        duration_ms = int((_time.monotonic() - t0) * 1000)

        data = response.json()
        result = data["message"]["content"]

        input_tokens = data.get("prompt_eval_count", 0)
        output_tokens = data.get("eval_count", 0)

        usage = UsageStats(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=0.0,  # Local model, free
            model=self.model,
            provider="ollama",
            duration_ms=duration_ms,
        )

        self.logger(f"OLLAMA RESPONSE | stage={stage} | length={len(result)} | tokens={usage.total_tokens}")
        return result, usage

    @property
    def provider_name(self) -> str:
        return "ollama"
