"""
Gateway provider - AI Gateway (internal use, not shipped in open-source).

Session-based provider: creates a session per call, sends prompt, closes session.

Config:
    provider: gateway
    model: haiku|sonnet|opus (default: haiku)

Env:
    AI_GATEWAY_URL: Gateway base URL (e.g. http://localhost:19850)
    BRAIN_API_URL: Legacy alias for AI_GATEWAY_URL
"""

import os
from typing import Callable, Optional

import requests

from .base import Provider


class GatewayProvider(Provider):
    """AI Gateway provider (session-based, internal use)."""

    def __init__(
        self,
        model: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.7,
        logger: Optional[Callable[[str], None]] = None,
        base_url: str = "",
        cwd: str = "",
        **kwargs,
    ):
        super().__init__(
            model=model or "haiku",
            max_tokens=max_tokens,
            temperature=temperature,
            logger=logger,
        )
        self.cwd = cwd or ""
        self.base_url = base_url or os.environ.get("AI_GATEWAY_URL", "") or os.environ.get("BRAIN_API_URL", "")
        # Strip trailing slash and /api/prompt suffix (legacy)
        self.base_url = self.base_url.rstrip("/")
        if self.base_url.endswith("/api/prompt"):
            self.base_url = self.base_url[: -len("/api/prompt")]

    def call(self, prompt: str, stage: str = ""):
        import time as _time

        from .base import UsageStats

        if not self.base_url:
            raise ValueError(
                "AI_GATEWAY_URL is required for gateway provider. Set AI_GATEWAY_URL=http://your-gateway:port"
            )

        self.logger(f"GATEWAY CALL | stage={stage} | model={self.model} | url={self.base_url}")

        t0 = _time.monotonic()

        # 1. Create session
        session_resp = requests.post(
            f"{self.base_url}/api/v1/sessions",
            json={"service": "rein", "model": self.model, **({"cwd": self.cwd} if self.cwd else {})},
            timeout=30,
        )
        session_resp.raise_for_status()
        session_id = session_resp.json()["session_id"]

        try:
            # 2. Send prompt
            chat_resp = requests.post(
                f"{self.base_url}/api/v1/sessions/{session_id}/chat",
                json={"content": prompt},
                timeout=300,
            )
            chat_resp.raise_for_status()
            chat_data = chat_resp.json()
            result = chat_data.get("content", "")
        finally:
            # 3. Always close session
            try:
                requests.delete(
                    f"{self.base_url}/api/v1/sessions/{session_id}",
                    timeout=10,
                )
            except Exception:
                pass

        duration_ms = int((_time.monotonic() - t0) * 1000)

        # Gateway may or may not return usage data
        resp_usage = chat_data.get("usage", {})
        usage = UsageStats(
            input_tokens=resp_usage.get("input_tokens", 0),
            output_tokens=resp_usage.get("output_tokens", 0),
            cost=0.0,  # Gateway pricing unknown
            model=self.model,
            provider="gateway",
            duration_ms=duration_ms,
        )

        self.logger(f"GATEWAY RESPONSE | stage={stage} | length={len(result)} | tokens={usage.total_tokens}")
        return result, usage

    @property
    def provider_name(self) -> str:
        return "gateway"
