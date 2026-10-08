"""Clientes de LLM: mock (sem rede) e compatível com a API da OpenAI (OpenAI e Groq).

Spec 05. O módulo não carrega o `.env`; quem chama (CLI/Streamlit) prepara o ambiente.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Mapping
from typing import Protocol

import openai
from openai import OpenAI

DEFAULT_GROQ_BASE_URL = "https://api.groq.com/openai/v1"

# Erros que valem nova tentativa: limite de taxa, timeout, conexão e falha 5xx do servidor.
TRANSIENT_ERRORS = (
    openai.RateLimitError,
    openai.APIConnectionError,  # inclui APITimeoutError
    openai.InternalServerError,
)


class LLMError(RuntimeError):
    pass


class LLMClient(Protocol):
    provider: str
    model: str

    def complete(self, system: str, user: str) -> str: ...


class MockClient:
    """Determinístico e sem rede. Devolve '[mock]\\n' + user e registra as chamadas."""

    provider = "mock"
    model = "mock"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        return f"[mock]\n{user}"


class OpenAICompatibleClient:
    def __init__(
        self,
        provider: str,
        api_key: str,
        model: str,
        base_url: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1500,
        timeout_s: float = 60.0,
        max_retries: int = 3,
        sdk_client: OpenAI | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not api_key:
            raise LLMError(f"{provider}: chave de API vazia")
        if not model:
            raise LLMError(f"{provider}: nome do modelo vazio")
        if max_retries < 0:
            raise ValueError("max_retries deve ser >= 0")
        self.provider = provider
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.max_retries = max_retries
        self._sleep = sleep
        # As retentativas são nossas (Spec 05), então desligamos as do SDK.
        self._sdk = sdk_client or OpenAI(
            api_key=api_key, base_url=base_url, timeout=timeout_s, max_retries=0
        )

    def complete(self, system: str, user: str) -> str:
        for tentativa in range(self.max_retries + 1):
            try:
                response = self._sdk.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                )
                break
            except TRANSIENT_ERRORS as e:
                if tentativa == self.max_retries:
                    raise self._error(e, f"após {tentativa + 1} tentativas") from e
                self._sleep(2 ** (tentativa + 1))  # 2 s, 4 s, 8 s...
            except openai.OpenAIError as e:
                raise self._error(e) from e

        choice = response.choices[0] if response.choices else None
        content = (choice.message.content or "").strip() if choice else ""
        if not content:
            motivo = getattr(choice, "finish_reason", None)
            dica = " (limite de tokens: aumente LLM_MAX_TOKENS)" if motivo == "length" else ""
            raise LLMError(f"{self.provider}: resposta vazia do modelo {self.model}{dica}")
        return content

    def _error(self, e: Exception, detalhe: str = "") -> LLMError:
        # Só o tipo e o status HTTP: a mensagem do SDK pode conter trechos da chave.
        status = getattr(e, "status_code", None)
        partes = [type(e).__name__, f"HTTP {status}" if status else "", detalhe]
        return LLMError(
            f"{self.provider}: falha ao chamar o modelo {self.model} "
            f"({', '.join(p for p in partes if p)})"
        )


def client_from_env(env: Mapping[str, str] | None = None) -> LLMClient:
    env = os.environ if env is None else env
    provider = env.get("LLM_PROVIDER", "").strip().lower() or "mock"
    if provider == "mock":
        return MockClient()
    if provider not in ("groq", "openai"):
        raise LLMError(f"LLM_PROVIDER inválido: {provider!r} (use mock, groq ou openai)")

    prefixo = provider.upper()
    api_key = _required(env, f"{prefixo}_API_KEY")
    model = _required(env, f"{prefixo}_MODEL")
    base_url = env.get(f"{prefixo}_BASE_URL", "").strip() or (
        DEFAULT_GROQ_BASE_URL if provider == "groq" else None
    )
    return OpenAICompatibleClient(
        provider=provider,
        api_key=api_key,
        model=model,
        base_url=base_url,
        temperature=_number(env, "LLM_TEMPERATURE", 0.2, float),
        max_tokens=_number(env, "LLM_MAX_TOKENS", 1500, int),
    )


def _required(env: Mapping[str, str], nome: str) -> str:
    valor = env.get(nome, "").strip()
    if not valor:
        raise LLMError(f"{nome} não configurada: preencha no .env (veja .env.example)")
    return valor


def _number(env: Mapping[str, str], nome: str, padrao, tipo):
    bruto = env.get(nome, "").strip()
    if not bruto:
        return padrao
    try:
        return tipo(bruto)
    except ValueError as e:
        raise LLMError(f"{nome} inválida: {bruto!r}") from e
