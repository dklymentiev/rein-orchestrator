"""
Base provider interface for LLM API calls.

All providers implement the same call() interface so the orchestrator
is completely agnostic to which LLM backend is used.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Callable, Tuple


@dataclass
class UsageStats:
    """Token usage and cost statistics for a single LLM call."""
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
    model: str = ""
    provider: str = ""
    duration_ms: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def to_dict(self) -> dict:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "cost": round(self.cost, 6),
            "model": self.model,
            "provider": self.provider,
            "duration_ms": self.duration_ms,
        }


# USD per 1M tokens
MODEL_PRICING = {
    # Anthropic
    "claude-sonnet-4": {"input": 3.0, "output": 15.0},
    "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0},
    "claude-haiku-4": {"input": 0.80, "output": 4.0},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.0},
    "claude-opus-4": {"input": 15.0, "output": 75.0},
    "claude-opus-4-20250514": {"input": 15.0, "output": 75.0},
    # OpenAI
    "gpt-4o": {"input": 2.50, "output": 10.0},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "o1": {"input": 15.0, "output": 60.0},
    "o3-mini": {"input": 1.10, "output": 4.40},
    # OpenRouter prefixed models (map to base pricing)
    "anthropic/claude-sonnet-4": {"input": 3.0, "output": 15.0},
    "anthropic/claude-haiku-4": {"input": 0.80, "output": 4.0},
    "anthropic/claude-opus-4": {"input": 15.0, "output": 75.0},
    "openai/gpt-4o": {"input": 2.50, "output": 10.0},
    "openai/gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "google/gemini-2.5-pro": {"input": 1.25, "output": 10.0},
    "google/gemini-2.5-flash": {"input": 0.15, "output": 0.60},
    "deepseek/deepseek-chat-v3": {"input": 0.27, "output": 1.10},
}


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate cost in USD for given token counts and model."""
    pricing = MODEL_PRICING.get(model)
    if not pricing:
        return 0.0
    input_cost = (input_tokens / 1_000_000) * pricing["input"]
    output_cost = (output_tokens / 1_000_000) * pricing["output"]
    return input_cost + output_cost


class Provider(ABC):
    """Abstract base class for LLM providers."""

    def __init__(
        self,
        model: str,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        logger: Optional[Callable[[str], None]] = None,
        **kwargs
    ):
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.logger = logger or (lambda x: None)

    @abstractmethod
    def call(self, prompt: str, stage: str = "") -> Tuple[str, UsageStats]:
        """
        Send prompt to LLM and return response text with usage stats.

        Args:
            prompt: The full prompt to send
            stage: Stage/block name for logging

        Returns:
            Tuple of (response_text, usage_stats)

        Raises:
            Exception on API errors (caught by orchestrator)
        """
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable provider name for logging."""
        ...
