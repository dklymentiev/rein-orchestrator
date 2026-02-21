"""
OpenAI provider - GPT-4o, GPT-4, o1, etc via official SDK.

Config:
    provider: openai
    model: gpt-4o  # or gpt-4, o1, o3-mini, etc.

Env:
    OPENAI_API_KEY: API key (required)
    OPENAI_BASE_URL: Custom base URL (optional, for Azure/proxies)
"""
import os
from typing import Optional, Callable

from .base import Provider


class OpenAIProvider(Provider):
    """OpenAI API provider (also works with Azure OpenAI and compatible APIs)."""

    DEFAULT_MODEL = "gpt-4o"

    def __init__(
        self,
        model: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.7,
        logger: Optional[Callable[[str], None]] = None,
        api_key: str = "",
        base_url: str = "",
        **kwargs
    ):
        super().__init__(
            model=model or self.DEFAULT_MODEL,
            max_tokens=max_tokens,
            temperature=temperature,
            logger=logger,
        )
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.base_url = base_url or os.environ.get("OPENAI_BASE_URL", "")

    def call(self, prompt: str, stage: str = "") -> str:
        from openai import OpenAI

        self.logger(f"OPENAI CALL | stage={stage} | model={self.model}")

        client_kwargs = {}
        if self.api_key:
            client_kwargs["api_key"] = self.api_key
        if self.base_url:
            client_kwargs["base_url"] = self.base_url

        client = OpenAI(**client_kwargs)
        response = client.chat.completions.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        result = response.choices[0].message.content
        self.logger(f"OPENAI RESPONSE | stage={stage} | length={len(result)}")
        return result

    @property
    def provider_name(self) -> str:
        return "openai"
