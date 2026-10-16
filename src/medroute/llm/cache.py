"""Cache em disco das respostas de provedores reais (Spec 05, S2).

Mesma entrada -> mesma resposta sem nova chamada à API: economiza a cota do Groq
e deixa as execuções do relatório e do vídeo reproduzíveis.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .client import LLMClient
    from .prompts import Prompt

logger = logging.getLogger(__name__)


class CachedClient:
    """Envolve um `LLMClient` e grava cada resposta em `<cache_dir>/<hash>.json`."""

    def __init__(self, inner: LLMClient, cache_dir: str | Path) -> None:
        self.inner = inner
        self.cache_dir = Path(cache_dir)
        self.provider = inner.provider
        self.model = inner.model
        self.hits = 0
        self.misses = 0

    def complete(self, system: str, user: str, *, prompt: Prompt | None = None) -> str:
        path = self.cache_dir / f"{self.key(system, user)}.json"
        cached = self._read(path)
        if cached is not None:
            self.hits += 1
            return cached

        self.misses += 1
        response = self.inner.complete(system, user, prompt=prompt)
        self._write(path, system, user, response, prompt)
        return response

    def key(self, system: str, user: str) -> str:
        campos = [self.provider, self.model, *self._params(), system, user]
        bruto = json.dumps(campos, ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(bruto).hexdigest()

    def _params(self) -> tuple[float | None, int | None]:
        return getattr(self.inner, "temperature", None), getattr(self.inner, "max_tokens", None)

    def _read(self, path: Path) -> str | None:
        try:
            response = json.loads(path.read_text(encoding="utf-8"))["response"]
        except FileNotFoundError:
            return None
        except (OSError, ValueError, KeyError, TypeError):
            logger.warning("cache de LLM ilegível, será refeito: %s", path.name)
            return None
        return response if isinstance(response, str) and response else None

    def _write(
        self, path: Path, system: str, user: str, response: str, prompt: Prompt | None
    ) -> None:
        temperature, max_tokens = self._params()
        entrada = {
            "provider": self.provider,
            "model": self.model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "prompt": prompt.nome if prompt else None,
            "versao": prompt.versao if prompt else None,
            "criado_em": datetime.now(UTC).isoformat(timespec="seconds"),
            "system": system,
            "user": user,
            "response": response,
        }
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        # Grava em arquivo temporário e renomeia: uma interrupção não deixa JSON pela metade.
        tmp = path.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(entrada, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)
