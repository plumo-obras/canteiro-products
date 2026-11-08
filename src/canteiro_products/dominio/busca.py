"""Busca por termos, do jeito que quem orça procura na base: palavras soltas, em qualquer ordem, sem se preocupar com
acento ou maiúscula ("concreto fck 30 bombeavel"). Um termo com "-" na frente exclui ("concreto -bomba").

Aqui só se decide o que a pessoa pediu; quem acha é o repositório (índice de texto)."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

MAX_TERMOS = 12


def normalizar(texto: str) -> str:
    """Sem acento, maiúsculo, só letras e números separados por espaço: "Aço CA-50, Ø 10,0" -> "ACO CA 50 0 10 0"."""
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().upper()
    return " ".join(re.findall(r"[A-Z0-9]+", t))


@dataclass(frozen=True)
class Consulta:
    contem: tuple[str, ...]
    nao_contem: tuple[str, ...] = ()

    @property
    def vazia(self) -> bool:
        return not self.contem


def interpretar(q: str) -> Consulta:
    contem, nao = [], []
    for bruto in (q or "").split()[:MAX_TERMOS]:
        alvo = nao if bruto.startswith("-") and len(bruto) > 1 else contem
        for t in normalizar(bruto.lstrip("-")).split():
            if t not in alvo:
                alvo.append(t)
    return Consulta(tuple(contem), tuple(nao))
