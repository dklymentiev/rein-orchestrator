"""Tests for rein/providers/ - AI-agnostic provider layer"""
import os
import pytest
from unittest.mock import patch, MagicMock

from rein.providers import create_provider, list_providers, Provider
from rein.providers.anthropic import AnthropicProvider
from rein.providers.openai import OpenAIProvider
from rein.providers.ollama import OllamaProvider
from rein.providers.openrouter import OpenRouterProvider


class TestProviderBase:
    """Test Provider abstract base class"""

    def test_provider_is_abstract(self):
        """Cannot instantiate Provider directly"""
        with pytest.raises(TypeError):
            Provider(model="test")

    def test_list_providers(self):
        """Core providers are registered"""
        providers = list_providers()
        assert "anthropic" in providers
        assert "openai" in providers
        assert "ollama" in providers
        assert "openrouter" in providers


class TestCreateProvider:
    """Test create_provider factory function"""

    def test_create_anthropic_explicit(self):
        """Create Anthropic provider by name"""
        p = create_provider(provider="anthropic", model="claude-sonnet-4-20250514", api_key="test-key")
        assert isinstance(p, AnthropicProvider)
        assert p.model == "claude-sonnet-4-20250514"
        assert p.provider_name == "anthropic"

    def test_create_openai_explicit(self):
        """Create OpenAI provider by name"""
        p = create_provider(provider="openai", model="gpt-4o", api_key="test-key")
        assert isinstance(p, OpenAIProvider)
        assert p.model == "gpt-4o"

    def test_create_ollama_explicit(self):
        """Create Ollama provider by name"""
        p = create_provider(provider="ollama", model="llama3.1")
        assert isinstance(p, OllamaProvider)
        assert p.model == "llama3.1"

    def test_create_openrouter_explicit(self):
        """Create OpenRouter provider by name"""
        p = create_provider(provider="openrouter", api_key="test-key")
        assert isinstance(p, OpenRouterProvider)

    def test_unknown_provider_raises(self):
        """Unknown provider name raises ValueError"""
        with pytest.raises(ValueError, match="Unknown provider"):
            create_provider(provider="nonexistent")

    def test_auto_detect_anthropic(self):
        """Auto-detect Anthropic from env"""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}, clear=False):
            env = {k: v for k, v in os.environ.items()
                   if k not in ("OPENAI_API_KEY", "OPENROUTER_API_KEY", "OLLAMA_URL")}
            with patch.dict(os.environ, env, clear=True):
                os.environ["ANTHROPIC_API_KEY"] = "sk-test"
                p = create_provider()
                assert isinstance(p, AnthropicProvider)

    def test_auto_detect_openai(self):
        """Auto-detect OpenAI from env"""
        env = {"OPENAI_API_KEY": "sk-test"}
        with patch.dict(os.environ, env, clear=True):
            p = create_provider()
            assert isinstance(p, OpenAIProvider)

    def test_no_provider_no_env_raises(self):
        """No provider and no env raises ValueError"""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="No provider specified"):
                create_provider()

    def test_provider_name_case_insensitive(self):
        """Provider name is case-insensitive"""
        p = create_provider(provider="Anthropic", api_key="test")
        assert isinstance(p, AnthropicProvider)

    def test_default_params(self):
        """Default max_tokens and temperature are applied"""
        p = create_provider(provider="ollama")
        assert p.max_tokens == 4096
        assert p.temperature == 0.7

    def test_custom_params(self):
        """Custom max_tokens and temperature are applied"""
        p = create_provider(provider="ollama", max_tokens=8192, temperature=0.3)
        assert p.max_tokens == 8192
        assert p.temperature == 0.3


class TestAnthropicProvider:
    """Test AnthropicProvider"""

    def test_default_model(self):
        p = AnthropicProvider()
        assert p.model == "claude-sonnet-4-20250514"

    def test_custom_model(self):
        p = AnthropicProvider(model="claude-opus-4-20250514")
        assert p.model == "claude-opus-4-20250514"

    def test_provider_name(self):
        p = AnthropicProvider()
        assert p.provider_name == "anthropic"


class TestOpenAIProvider:
    """Test OpenAIProvider"""

    def test_default_model(self):
        p = OpenAIProvider()
        assert p.model == "gpt-4o"

    def test_base_url(self):
        p = OpenAIProvider(base_url="https://custom.api.com/v1")
        assert p.base_url == "https://custom.api.com/v1"


class TestOllamaProvider:
    """Test OllamaProvider"""

    def test_default_url(self):
        p = OllamaProvider()
        assert p.base_url == "http://localhost:11434"

    def test_custom_url(self):
        p = OllamaProvider(base_url="http://gpu-server:11434")
        assert p.base_url == "http://gpu-server:11434"


class TestConfigIntegration:
    """Test provider config extraction from workflow YAML"""

    def test_simple_provider_config(self):
        from rein.config import ConfigLoader
        loader = ConfigLoader(agents_dir="/tmp")
        config = {"provider": "anthropic", "model": "claude-sonnet-4-20250514"}
        result = loader.get_provider_config(config)
        assert result["provider"] == "anthropic"
        assert result["model"] == "claude-sonnet-4-20250514"

    def test_nested_provider_config(self):
        from rein.config import ConfigLoader
        loader = ConfigLoader(agents_dir="/tmp")
        config = {
            "provider": {
                "name": "openai",
                "model": "gpt-4o",
                "base_url": "https://custom.api.com",
                "max_tokens": 8192,
            }
        }
        result = loader.get_provider_config(config)
        assert result["provider"] == "openai"
        assert result["model"] == "gpt-4o"
        assert result["base_url"] == "https://custom.api.com"
        assert result["max_tokens"] == 8192

    def test_empty_provider_config(self):
        from rein.config import ConfigLoader
        loader = ConfigLoader(agents_dir="/tmp")
        config = {"blocks": []}
        result = loader.get_provider_config(config)
        assert result["provider"] == ""
        assert result["model"] == ""
