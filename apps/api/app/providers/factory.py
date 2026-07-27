from app.core.config import Settings
from app.providers.base import ModelProvider
from app.providers.http import OllamaProvider, OpenAICompatibleProvider


def create_provider(settings: Settings) -> ModelProvider:
    if settings.model_provider == "ollama":
        return OllamaProvider(settings)
    if settings.model_provider == "openai_compatible":
        return OpenAICompatibleProvider(settings)
    raise ValueError("Unsupported model provider")
