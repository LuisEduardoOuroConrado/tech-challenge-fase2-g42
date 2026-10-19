"""Camada de LLM: instruções, relatórios e Q&A (Spec 05)."""

from .cache import CachedClient
from .client import LLMClient, LLMError, MockClient, OpenAICompatibleClient, client_from_env
from .context import RouteContext, StopContext, build_route_contexts
from .instructions import generate_instructions
from .prompts import Prompt, load_prompt
from .qa import answer
from .reports import generate_report

__all__ = [
    "CachedClient",
    "LLMClient",
    "LLMError",
    "MockClient",
    "OpenAICompatibleClient",
    "Prompt",
    "RouteContext",
    "StopContext",
    "answer",
    "build_route_contexts",
    "client_from_env",
    "generate_instructions",
    "generate_report",
    "load_prompt",
]
