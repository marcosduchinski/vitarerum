"""Captcha verifier adapters.

``CloudflareTurnstileVerifier`` calls Cloudflare's ``siteverify`` with the
server-held secret. ``AlwaysPassVerifier`` is the local/test stand-in used when
``app_env`` is local (Cloudflare ships always-passing dev keys, but skipping the
network call keeps the test suite offline and deterministic).
"""

from __future__ import annotations

import httpx


class CloudflareTurnstileVerifier:
    def __init__(self, secret_key: str, verify_url: str, timeout: float = 5.0) -> None:
        self._secret = secret_key
        self._url = verify_url
        self._timeout = timeout

    async def verify(self, token: str, remote_ip: str) -> bool:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                self._url,
                data={
                    "secret": self._secret,
                    "response": token,
                    "remoteip": remote_ip,
                },
            )
        resp.raise_for_status()
        return bool(resp.json().get("success"))


class AlwaysPassVerifier:
    """Accepts any token. For local/test only."""

    async def verify(self, token: str, remote_ip: str) -> bool:
        return True
