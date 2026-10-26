"""Monta o relatório técnico em PDF a partir dos capítulos em Markdown.

Junta os capítulos de `CAPITULOS` (na ordem do enunciado), converte para HTML com markdown-it,
desenha os diagramas Mermaid e imprime em PDF com o Chrome headless (estilo em
`reports/relatorio/estilo.css`). Imagens apontam para os arquivos locais; links para arquivos do
repositório viram links do GitHub.

    python scripts/build_relatorio.py                       # vídeo ainda "a publicar"
    python scripts/build_relatorio.py --video https://...   # com o link do vídeo na capa
"""

from __future__ import annotations

import argparse
import html
import os
import re
import shutil
import subprocess
import tempfile
from datetime import date
from pathlib import Path

from markdown_it import MarkdownIt

RAIZ = Path(__file__).resolve().parents[1]
REPO_URL = "https://github.com/LuisEduardoOuroConrado/tech-challenge-fase2-g42"
SAIDA_PDF = RAIZ / "reports/relatorio/relatorio-tecnico-g42.pdf"
SAIDA_HTML = RAIZ / "reports/relatorio/build/relatorio.html"
ESTILO = RAIZ / "reports/relatorio/estilo.css"
MERMAID_JS = "https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js"
MERMAID_INIT = 'mermaid.initialize({ startOnLoad: true, theme: "neutral" });'

INTEGRANTES = [
    "Luis Eduardo Ouro Conrado",
    "Beatriz Honey",
    "Pedro Henrique Klein de Almeida",
    "Rodrigo Edson Fernandes",
    "Alexandre Akio Ogata",
]

# (arquivo, título do capítulo no PDF, linha de autoria acrescentada logo abaixo do título ou None)
CAPITULOS = [
    ("reports/relatorio/00-introducao.md", "Introdução e arquitetura", None),
    ("reports/secoes/conrado-ga.md", "Algoritmo genético: do TSP ao VRP", None),
    ("reports/secoes/rodrigo-llm.md", "Integração com LLM", None),
    (
        "reports/secoes/pedro-experimentos-s3.md",
        "Comparativo com outras abordagens: experimentos E1–E6",
        "**Autor:** Pedro (Parte C) · **Base:** `configs/experimentos/s3.yaml`, "
        "`reports/experimentos-s3/`.",
    ),
    ("reports/relatorio/40-visualizacao.md", "Visualização das rotas e aplicação", None),
    ("reports/relatorio/90-conclusao.md", "Conclusão", None),
]

LINK_MD = re.compile(r"(!?)\[([^\]]*)\]\(([^)\s]+)\)")


def _resolver_links(texto: str, pasta: Path) -> str:
    """Imagem -> caminho relativo ao HTML gerado; link relativo para o repositório -> GitHub.

    (markdown-it recusa URLs `file:`, por isso a imagem fica relativa a `SAIDA_HTML`.)"""

    def trocar(m: re.Match) -> str:
        imagem, rotulo, alvo = m.groups()
        if re.match(r"^[a-z]+:|^#", alvo):
            return m.group(0)
        caminho = (pasta / alvo).resolve()
        if imagem:
            return f"![{rotulo}]({Path(os.path.relpath(caminho, SAIDA_HTML.parent)).as_posix()})"
        try:
            rel = caminho.relative_to(RAIZ).as_posix()
        except ValueError:
            return m.group(0)
        tipo = "tree" if caminho.is_dir() else "blob"
        return f"[{rotulo}]({REPO_URL}/{tipo}/main/{rel})"

    return LINK_MD.sub(trocar, texto)


def _capitulo(arquivo: str, titulo: str, autoria: str | None) -> str:
    caminho = RAIZ / arquivo
    texto = caminho.read_text(encoding="utf-8")
    linhas = texto.splitlines()
    if not linhas or not linhas[0].startswith("# "):
        raise ValueError(f"{arquivo}: a primeira linha deve ser o título (# ...)")
    corpo = "\n".join(linhas[1:])
    if autoria:
        corpo = f"\n{autoria}\n{corpo}"
    return f"# {titulo}\n{_resolver_links(corpo, caminho.parent)}"


def _markdown() -> MarkdownIt:
    md = MarkdownIt("commonmark", {"html": True}).enable(["table", "strikethrough"])
    padrao = md.renderer.rules["fence"]

    def fence(tokens, idx, options, env):
        token = tokens[idx]
        if token.info.strip() == "mermaid":
            return f'<pre class="mermaid">{html.escape(token.content)}</pre>\n'
        return padrao(tokens, idx, options, env)

    md.renderer.rules["fence"] = fence
    return md


def _pos_processar(corpo: str) -> tuple[str, str]:
    """Numera capítulos, cria âncoras e sumário e transforma imagens isoladas em figuras."""
    # (âncora, título, [(âncora, título) das seções])
    capitulos: list[tuple[str, str, list[tuple[str, str]]]] = []

    def cabecalho(m: re.Match) -> str:
        nivel, conteudo = m.group(1), m.group(2)
        if nivel == "1":
            n = len(capitulos) + 1
            capitulos.append((f"cap{n}", f"{n}. {conteudo}", []))
            return f'<h1 id="cap{n}"><span class="num">{n}</span>{conteudo}</h1>'
        ancora, _, secoes = capitulos[-1]
        sub = f"{ancora}-{len(secoes) + 1}"
        secoes.append((sub, conteudo))
        return f'<h2 id="{sub}">{conteudo}</h2>'

    corpo = re.sub(r"<h([12])>(.*?)</h\1>", cabecalho, corpo)
    itens = "".join(
        f'<li><a href="#{a}">{t}</a><ol>'
        + "".join(f'<li><a href="#{sa}">{st}</a></li>' for sa, st in secoes)
        + "</ol></li>"
        for a, t, secoes in capitulos
    )
    corpo = re.sub(
        r'<p><img src="([^"]+)" alt="([^"]*)" ?/?></p>',
        r'<figure><img src="\1" alt="\2"><figcaption>\2</figcaption></figure>',
        corpo,
    )
    return corpo, f'<ol class="toc">{itens}</ol>'


def _capa(video: str | None) -> str:
    nomes = "".join(f"<li>{html.escape(nome)}</li>" for nome in INTEGRANTES)
    video_html = "<em>a publicar</em>"
    if video:
        video_html = f'<a href="{html.escape(video)}">{html.escape(video)}</a>'
    hoje = date.today().strftime("%d/%m/%Y")
    return f"""
<section class="capa">
  <p class="curso">FIAP · Pós Tech · IA para Devs · Tech Challenge Fase 2</p>
  <h1 class="titulo">medroute</h1>
  <p class="subtitulo">Otimização de rotas para distribuição de medicamentos e insumos
     com algoritmo genético e LLM</p>
  <p class="projeto">Projeto 2 · Relatório técnico · Grupo 42</p>
  <ul class="integrantes">{nomes}</ul>
  <table class="links">
    <tr><th>Repositório</th><td><a href="{REPO_URL}">{REPO_URL}</a></td></tr>
    <tr><th>Vídeo</th><td>{video_html}</td></tr>
  </table>
  <p class="data">São Paulo, {hoje}</p>
</section>"""


def montar_html(video: str | None) -> str:
    md = _markdown()
    corpo = md.render("\n\n".join(_capitulo(*c) for c in CAPITULOS))
    corpo, sumario = _pos_processar(corpo)
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<title>medroute · Relatório técnico · Grupo 42</title>
<style>{ESTILO.read_text(encoding="utf-8")}</style>
<script src="{MERMAID_JS}"></script>
<script>{MERMAID_INIT}</script>
</head><body>
{_capa(video)}
<section class="sumario"><h1 style="border:0">Sumário</h1>{sumario}</section>
{corpo}
</body></html>"""


def _chrome(caminho: str | None) -> str:
    candidatos = [
        caminho,
        shutil.which("chrome"),
        shutil.which("google-chrome"),
        shutil.which("chromium"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    for c in candidatos:
        if c and Path(c).exists():
            return c
    raise SystemExit("Chrome ou Edge não encontrado; use --chrome <caminho>.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--video", help="link do vídeo (YouTube ou Vimeo) para a capa")
    parser.add_argument("--chrome", help="caminho do Chrome/Edge")
    parser.add_argument("--out", type=Path, default=SAIDA_PDF)
    args = parser.parse_args()

    SAIDA_HTML.parent.mkdir(parents=True, exist_ok=True)
    SAIDA_HTML.write_text(montar_html(args.video), encoding="utf-8")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    try:
        args.out.unlink(missing_ok=True)
    except PermissionError:
        msg = f"{args.out} está aberto em outro programa; feche e rode de novo."
        raise SystemExit(msg) from None
    # Perfil temporário: sem ele, um Chrome já aberto recebe a chamada e o PDF não é gerado.
    with tempfile.TemporaryDirectory() as perfil:
        subprocess.run(
            [
                _chrome(args.chrome),
                "--headless=new",
                "--disable-gpu",
                f"--user-data-dir={perfil}",
                "--no-pdf-header-footer",
                "--virtual-time-budget=30000",
                f"--print-to-pdf={args.out}",
                SAIDA_HTML.as_uri(),
            ],
            check=True,
            capture_output=True,
        )
    if not args.out.exists():
        raise SystemExit("O Chrome não gerou o PDF.")
    print(f"PDF: {args.out.relative_to(RAIZ) if args.out.is_relative_to(RAIZ) else args.out}")


if __name__ == "__main__":
    main()
