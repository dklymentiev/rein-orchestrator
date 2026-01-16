"""
Rein Claude Client - API calls via Brain API, OpenRouter, or Anthropic direct
"""
import os
from typing import Optional, Callable

import requests


class ClaudeClient:
    """Client for Claude API (supports Brain API, OpenRouter, Anthropic)"""

    # Brain API endpoint (Claude CLI with full host access)
    BRAIN_API_URL = "https://brain.generic-app.com/api/prompt"

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

    def call(self, prompt: str, stage: str = "") -> str:
        """
        Call Claude API (auto-selects Brain API, OpenRouter, or Anthropic)

        Priority:
        1. BRAIN_API_URL env var or default brain.generic-app.com
        2. OPENROUTER_API_KEY -> OpenRouter
        3. ANTHROPIC_API_KEY -> Anthropic direct

        Args:
            prompt: The prompt to send
            stage: Stage name for logging

        Returns:
            Response text or error message
        """
        try:
            brain_url = os.environ.get('BRAIN_API_URL', self.BRAIN_API_URL)
            openrouter_key = os.environ.get('OPENROUTER_API_KEY')
            anthropic_key = os.environ.get('ANTHROPIC_API_KEY')

            # Priority 1: Brain API (default)
            if brain_url and not os.environ.get('DISABLE_BRAIN_API'):
                self.logger(f"BRAIN API CALL | stage={stage}")
                return self._call_brain(prompt, stage, brain_url)

            # Priority 2: OpenRouter
            if openrouter_key:
                openrouter_model = os.environ.get('OPENROUTER_MODEL', 'anthropic/claude-3.5-sonnet')
                self.logger(f"OPENROUTER CALL | stage={stage} | model={openrouter_model}")
                return self._call_openrouter(prompt, stage, openrouter_key, openrouter_model)

            # Priority 3: Anthropic direct
            if anthropic_key:
                self.logger(f"ANTHROPIC CALL | stage={stage}")
                return self._call_anthropic(prompt, stage)

            # Fallback to Brain API anyway
            self.logger(f"BRAIN API CALL (fallback) | stage={stage}")
            return self._call_brain(prompt, stage, self.BRAIN_API_URL)

        except Exception as e:
            self.logger(f"API ERROR | stage={stage} | {str(e)}")
            return f"ERROR: {str(e)}"

    def _call_brain(self, prompt: str, stage: str, url: str) -> str:
        """Call Brain API (Claude CLI wrapper with full host access)"""
        response = requests.post(
            url,
            json={"prompt": prompt},
            timeout=120,
            verify=True
        )
        response.raise_for_status()
        result = response.json().get('response', '')
        self.logger(f"BRAIN RESPONSE | stage={stage} | length={len(result)}")
        return result

    def _call_anthropic(self, prompt: str, stage: str) -> str:
        """Call Anthropic Claude API directly"""
        import anthropic
        client = anthropic.Anthropic()
        message = client.messages.create(
            model=self.default_model,
            max_tokens=self.max_tokens,
            messages=[{"role": "user", "content": prompt}]
        )
        result = message.content[0].text
        self.logger(f"ANTHROPIC RESPONSE | stage={stage} | length={len(result)}")
        return result

    def _call_openrouter(self, prompt: str, stage: str, api_key: str, model: str) -> str:
        """Call OpenRouter API (proxy for Claude and other models)"""
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        # Allow env overrides for max_tokens and temperature
        max_tokens = int(os.environ.get('MAX_TOKENS', self.max_tokens))
        temperature = float(os.environ.get('TEMPERATURE', self.temperature))

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature
        }

        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=60
        )
        response.raise_for_status()

        result = response.json()['choices'][0]['message']['content']
        self.logger(f"OPENROUTER RESPONSE | stage={stage} | length={len(result)}")
        return result
