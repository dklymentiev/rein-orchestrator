"""
Rein Providers - AI-agnostic LLM provider layer.

Usage:
    from rein.providers import create_provider

    # From workflow config
    provider = create_provider(provider="anthropic", model="claude-sonnet-4-20250514")
    result = provider.call("Summarize this text...", stage="analysis")

    # Auto-detect from environment variables
    provider = create_provider()  # checks ANTHROPIC_API_KEY, OPENAI_API_KEY, etc.

Supported providers:
    - anthropic: Direct Claude API (ANTHROPIC_API_KEY)
    - openai: OpenAI API (OPENAI_API_KEY), also works with Azure
    - ollama: Local models via Ollama (OLLAMA_URL)
    - openrouter: Multi-model proxy (OPENROUTER_API_KEY)
    - gateway: AI Gateway proxy (AI_GATEWAY_URL)
"""
import os
from typing import Optional, Callable

from .base import Provider, UsageStats
from .anthropic import AnthropicProvider
from .openai import OpenAIProvider
from .ollama import OllamaProvider
from .openrouter import OpenRouterProvider
from .gateway import GatewayProvider

PROVIDERS = {
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
    "ollama": OllamaProvider,
    "openrouter": OpenRouterProvider,
    "gateway": GatewayProvider,
}



def create_provider(
    provider: str = "",
    model: str = "",
    max_tokens: int = 4096,
    temperature: float = 0.7,
    logger: Optional[Callable[[str], None]] = None,
    **kwargs
) -> Provider:
    """
    Create an LLM provider instance.

    If provider is not specified, auto-detects from environment:
    1. ANTHROPIC_API_KEY -> anthropic
    2. OPENAI_API_KEY -> openai
    3. OPENROUTER_API_KEY -> openrouter
    4. OLLAMA_URL -> ollama

    Args:
        provider: Provider name (anthropic, openai, ollama, openrouter)
        model: Model name (provider-specific)
        max_tokens: Maximum response tokens
        temperature: Sampling temperature
        logger: Logging callback
        **kwargs: Provider-specific options (api_key, base_url, etc.)

    Returns:
        Provider instance

    Raises:
        ValueError: If provider is unknown or no provider can be auto-detected
    """
    # Explicit provider
    if provider:
        provider_name = provider.lower().strip()
        if provider_name not in PROVIDERS:
            available = ", ".join(sorted(PROVIDERS.keys()))
            raise ValueError(f"Unknown provider '{provider_name}'. Available: {available}")
        return PROVIDERS[provider_name](
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            logger=logger,
            **kwargs,
        )

    # Auto-detect from environment
    if os.environ.get("ANTHROPIC_API_KEY"):
        return AnthropicProvider(model=model, max_tokens=max_tokens, temperature=temperature, logger=logger, **kwargs)

    if os.environ.get("OPENAI_API_KEY"):
        return OpenAIProvider(model=model, max_tokens=max_tokens, temperature=temperature, logger=logger, **kwargs)

    if os.environ.get("OPENROUTER_API_KEY"):
        return OpenRouterProvider(model=model, max_tokens=max_tokens, temperature=temperature, logger=logger, **kwargs)

    if os.environ.get("OLLAMA_URL"):
        return OllamaProvider(model=model, max_tokens=max_tokens, temperature=temperature, logger=logger, **kwargs)

    if os.environ.get("AI_GATEWAY_URL") or os.environ.get("BRAIN_API_URL"):
        return GatewayProvider(model=model, max_tokens=max_tokens, temperature=temperature, logger=logger, **kwargs)

    raise ValueError(
        "No provider specified and no API keys found in environment. "
        "Set one of: ANTHROPIC_API_KEY, OPENAI_API_KEY, OPENROUTER_API_KEY, OLLAMA_URL, or AI_GATEWAY_URL"
    )


def list_providers() -> list:
    """Return list of available provider names."""
    return sorted(PROVIDERS.keys())


__all__ = [
    "Provider",
    "UsageStats",
    "AnthropicProvider",
    "OpenAIProvider",
    "OllamaProvider",
    "OpenRouterProvider",
    "GatewayProvider",
    "create_provider",
    "list_providers",
]
