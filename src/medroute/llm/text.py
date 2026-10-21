"""Utilitários de texto da camada de LLM: formatação pt-BR e limpeza das respostas."""

from __future__ import annotations

# Espaços inseparáveis (U+00A0, U+2007, U+202F) -> espaço; hífens U+2010/U+2011 -> "-".
_TIPOGRAFICOS = {0x00A0: " ", 0x2007: " ", 0x202F: " ", 0x2010: "-", 0x2011: "-"}
_SEPARADORES_BR = str.maketrans({",": ".", ".": ","})


def clean_text(texto: str) -> str:
    """Troca espaços e hífens tipográficos por comuns.

    Modelos como o gpt-oss escrevem "Domicílio<U+202F>02" (espaço estreito inseparável),
    que parece igual na tela, mas quebra a comparação de nomes e some em fontes de PDF.
    """
    return texto.translate(_TIPOGRAFICOS)


def numero_br(valor: float, casas: int = 1) -> str:
    """Formata no padrão brasileiro: 1120.5 -> '1.120,5'."""
    return f"{valor:,.{casas}f}".translate(_SEPARADORES_BR)


def moeda(valor: float) -> str:
    """1586.65 -> 'R$ 1.586,65'."""
    return f"R$ {numero_br(valor, 2)}"


def hora(minuto_do_dia: float) -> str:
    """Minuto do dia, arredondado ao minuto: 462.4 -> '07:42'."""
    minutos = round(minuto_do_dia) % (24 * 60)
    return f"{minutos // 60:02d}:{minutos % 60:02d}"
