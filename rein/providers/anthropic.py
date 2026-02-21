"""
Anthropic provider - direct Claude API via official SDK.

Config:
    provider: anthropic
    model: claude-sonnet-4-20250514  # or claude-opus-4-20250514, etc.

Env:
    ANTHROPIC_API_KEY: API key (required)
"""
import os
from typing import Optional, Callable

from .base import Provider


class AnthropicProvider(Provider):
    """Direct Anthropic Claude API provider."""

    DEFAULT_MODEL = "claude-sonnet-4-20250514"

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
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")

    def call(self, prompt: str, stage: str = "") -> str:
        import anthropic

        self.logger(f"ANTHROPIC CALL | stage={stage} | model={self.model}")

        client = anthropic.Anthropic(api_key=self.api_key) if self.api_key else anthropic.Anthropic()
        message = client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        result = message.content[0].text
        self.logger(f"ANTHROPIC RESPONSE | stage={stage} | length={len(result)}")
        return result

    @property
    def provider_name(self) -> str:
        return "anthropic"
