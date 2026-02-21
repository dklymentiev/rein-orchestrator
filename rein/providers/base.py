"""
Base provider interface for LLM API calls.

All providers implement the same call() interface so the orchestrator
is completely agnostic to which LLM backend is used.
"""
from abc import ABC, abstractmethod
from typing import Optional, Callable


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
    def call(self, prompt: str, stage: str = "") -> str:
        """
        Send prompt to LLM and return response text.

        Args:
            prompt: The full prompt to send
            stage: Stage/block name for logging

        Returns:
            Response text from the LLM

        Raises:
            Exception on API errors (caught by orchestrator)
        """
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable provider name for logging."""
        ...
