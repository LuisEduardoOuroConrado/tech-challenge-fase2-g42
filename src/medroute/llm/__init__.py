"""Camada de LLM: instruções, relatórios e Q&A (Spec 05)."""

from .client import LLMClient, LLMError, MockClient, OpenAICompatibleClient, client_from_env
from .context import RouteContext, StopContext, build_route_contexts
from .instructions import generate_instructions
from .prompts import Prompt, load_prompt

__all__ = [
    "LLMClient",
    "LLMError",
    "MockClient",
    "OpenAICompatibleClient",
    "Prompt",
    "RouteContext",
    "StopContext",
    "build_route_contexts",
    "client_from_env",
    "generate_instructions",
    "load_prompt",
]
