from __future__ import annotations

import httpx
import pytest
import respx

from app.core.config import Settings
from app.providers.http import OllamaProvider, OpenAICompatibleProvider


@pytest.mark.asyncio
async def test_ollama_health_requires_the_configured_model(tmp_path) -> None:
    settings = Settings(
        data_dir=tmp_path,
        model_provider="ollama",
        model_base_url="http://ollama.test",
        model_name="required:latest",
    )
    provider = OllamaProvider(settings)

    with respx.mock:
        respx.get("http://ollama.test/api/tags").mock(
            return_value=httpx.Response(
                200,
                json={"models": [{"name": "other:latest", "model": "other:latest"}]},
            )
        )
        assert await provider.health() == (False, "model_missing")

        respx.get("http://ollama.test/api/tags").mock(
            return_value=httpx.Response(
                200,
                json={"models": [{"name": "required:latest", "model": "required:latest"}]},
            )
        )
        assert await provider.health() == (True, "available")


@pytest.mark.asyncio
async def test_openai_compatible_health_requires_the_configured_model(tmp_path) -> None:
    settings = Settings(
        data_dir=tmp_path,
        model_provider="openai_compatible",
        model_base_url="https://models.test/v1",
        model_name="required-model",
    )
    provider = OpenAICompatibleProvider(settings)

    with respx.mock:
        respx.get("https://models.test/v1/models").mock(
            return_value=httpx.Response(200, json={"data": [{"id": "other-model"}]})
        )
        assert await provider.health() == (False, "model_missing")

        respx.get("https://models.test/v1/models").mock(
            return_value=httpx.Response(200, json={"data": [{"id": "required-model"}]})
        )
        assert await provider.health() == (True, "available")
