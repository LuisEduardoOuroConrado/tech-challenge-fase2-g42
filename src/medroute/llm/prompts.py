"""Prompts versionados em `llm/prompts/<nome>.md` (Spec 05).

Formato do arquivo: cabeçalho YAML entre `---` com `versao`, seguido das seções
`## system` e `## user`. Os textos usam `string.Template` (`$variavel`), que não
conflita com as chaves do JSON enviado à LLM.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from string import Template

import yaml

PROMPTS_DIR = Path(__file__).parent / "prompts"

_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n(.*)\Z", re.DOTALL)
_SECAO = re.compile(r"^## (system|user)[ \t]*$", re.MULTILINE)


@dataclass(frozen=True)
class Prompt:
    nome: str
    versao: int
    system: str
    user: str

    def render(self, **variaveis: str) -> tuple[str, str]:
        """Devolve (system, user) com as variáveis substituídas."""
        try:
            return (
                Template(self.system).substitute(variaveis),
                Template(self.user).substitute(variaveis),
            )
        except KeyError as e:
            raise ValueError(f"prompt {self.nome}: variável {e} não informada") from e


def load_prompt(nome: str, pasta: Path = PROMPTS_DIR) -> Prompt:
    path = pasta / f"{nome}.md"
    texto = path.read_text(encoding="utf-8").replace("\r\n", "\n")

    match = _FRONTMATTER.match(texto)
    if not match:
        raise ValueError(f"{path.name}: cabeçalho '---' com a versão não encontrado")
    cabecalho = yaml.safe_load(match.group(1)) or {}
    versao = cabecalho.get("versao")
    if not isinstance(versao, int) or versao < 1:
        raise ValueError(f"{path.name}: 'versao' deve ser um inteiro >= 1")

    partes = _SECAO.split(match.group(2))
    # split com grupo: [antes, "system", texto, "user", texto]
    secoes = dict(zip(partes[1::2], (p.strip() for p in partes[2::2]), strict=True))
    if set(secoes) != {"system", "user"} or len(partes) != 5:
        raise ValueError(f"{path.name}: são esperadas as seções '## system' e '## user'")
    return Prompt(nome=nome, versao=versao, system=secoes["system"], user=secoes["user"])
