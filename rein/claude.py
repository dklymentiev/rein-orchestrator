"""
Rein Claude Client - LEGACY module, kept for backward compatibility.

New code should use rein.providers instead:
    from rein.providers import create_provider
    provider = create_provider(provider="anthropic", model="claude-sonnet-4-20250514")
    result = provider.call(prompt, stage)

This module wraps the new provider system to maintain the old ClaudeClient API.
"""
import os
import warnings
from typing import Optional, Callable

from .providers import create_provider


class ClaudeClient:
    """Legacy client for Claude API - wraps new provider system.

    Deprecated: Use rein.providers.create_provider() instead.
    """

    def __init__(
        self,
        logger: Optional[Callable[[str], None]] = None,
        default_model: str = "claude-sonnet-4-20250514",
        max_tokens: int = 4096,
        temperature: float = 0.7
    ):
        self.logger = logger or (lambda x: None)
        self.default_model = default_model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._provider = None

    def _get_provider(self):
        """Lazy-init provider from environment."""
        if self._provider is None:
            self._provider = create_provider(
                model=self.default_model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                logger=self.logger,
            )
        return self._provider

    def call(self, prompt: str, stage: str = "") -> str:
        """Call LLM via auto-detected provider."""
        try:
            return self._get_provider().call(prompt, stage)
        except Exception as e:
            self.logger(f"API ERROR | stage={stage} | {str(e)}")
            return f"ERROR: {str(e)}"
