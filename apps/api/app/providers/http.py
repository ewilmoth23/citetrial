from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit

import httpx

from app.core.config import Settings
from app.providers.base import ModelProvider, ProviderError, ProviderResult


def provider_leaves_device(base_url: str) -> bool:
    hostname = (urlsplit(base_url).hostname or "").rstrip(".").lower()
    if hostname in {"localhost", "localhost.localdomain", "host.docker.internal"}:
        return False
    try:
        address = ipaddress.ip_address(hostname.split("%", 1)[0])
    except ValueError:
        return True
    return not (address.is_loopback or address.is_private or address.is_link_local)


class OllamaProvider(ModelProvider):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def leaves_device(self) -> bool:
        return provider_leaves_device(self.settings.model_base_url)

    async def health(self) -> tuple[bool, str]:
        try:
            async with httpx.AsyncClient(timeout=3, trust_env=False) as client:
                response = await client.get(f"{self.settings.model_base_url.rstrip('/')}/api/tags")
                response.raise_for_status()
                body = response.json()
            models = body.get("models") if isinstance(body, dict) else None
            if not isinstance(models, list):
                return False, "unavailable"
            available_models = {
                value
                for item in models
                if isinstance(item, dict)
                for key in ("name", "model")
                if isinstance((value := item.get(key)), str)
            }
            if self.settings.model_name not in available_models:
                return False, "model_missing"
            return True, "available"
        except (httpx.HTTPError, ValueError, TypeError):
            return False, "unavailable"

    async def complete(
        self, system: str, user: str, *, temperature: float | None = None
    ) -> ProviderResult:
        payload = {
            "model": self.settings.model_name,
            "stream": False,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "options": {
                "temperature": self.settings.model_temperature
                if temperature is None
                else temperature,
                "num_predict": self.settings.model_max_tokens,
            },
        }
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.model_timeout_seconds, trust_env=False
            ) as client:
                response = await client.post(
                    f"{self.settings.model_base_url.rstrip('/')}/api/chat", json=payload
                )
                response.raise_for_status()
                body = response.json()
            return ProviderResult(
                content=str(body["message"]["content"]), usage=body.get("eval_count", {})
            )
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise ProviderError("Local model provider did not return a valid response") from exc


class OpenAICompatibleProvider(ModelProvider):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def leaves_device(self) -> bool:
        return provider_leaves_device(self.settings.model_base_url)

    @property
    def _headers(self) -> dict[str, str]:
        return (
            {"Authorization": f"Bearer {self.settings.model_api_key}"}
            if self.settings.model_api_key
            else {}
        )

    async def health(self) -> tuple[bool, str]:
        try:
            async with httpx.AsyncClient(
                timeout=3, headers=self._headers, trust_env=False
            ) as client:
                response = await client.get(f"{self.settings.model_base_url.rstrip('/')}/models")
                response.raise_for_status()
                body = response.json()
            models = body.get("data") if isinstance(body, dict) else None
            if not isinstance(models, list):
                return False, "unavailable"
            available_models = {
                identifier
                for item in models
                if isinstance(item, dict)
                if isinstance((identifier := item.get("id")), str)
            }
            if self.settings.model_name not in available_models:
                return False, "model_missing"
            return True, "available"
        except (httpx.HTTPError, ValueError, TypeError):
            return False, "unavailable"

    async def complete(
        self, system: str, user: str, *, temperature: float | None = None
    ) -> ProviderResult:
        payload = {
            "model": self.settings.model_name,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": self.settings.model_temperature if temperature is None else temperature,
            "max_tokens": self.settings.model_max_tokens,
        }
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.model_timeout_seconds, headers=self._headers, trust_env=False
            ) as client:
                response = await client.post(
                    f"{self.settings.model_base_url.rstrip('/')}/chat/completions", json=payload
                )
                response.raise_for_status()
                body = response.json()
            return ProviderResult(
                content=str(body["choices"][0]["message"]["content"]), usage=body.get("usage", {})
            )
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise ProviderError(
                "Configured model provider did not return a valid response"
            ) from exc
