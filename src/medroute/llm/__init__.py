"""Camada de LLM: instruções, relatórios e Q&A (Spec 05)."""

from .client import LLMClient, LLMError, MockClient, OpenAICompatibleClient, client_from_env

__all__ = [
    "LLMClient",
    "LLMError",
    "MockClient",
    "OpenAICompatibleClient",
    "client_from_env",
]
