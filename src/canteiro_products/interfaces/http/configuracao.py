"""Configuração por variável de ambiente (todas opcionais).

PRODUTOS_DADOS          pasta do banco (padrão ./dados_produtos; /dados na imagem)
PRODUTOS_API_KEYS       chaves aceitas em X-API-Key, separadas por vírgula (vazio = sem autenticação)
PRODUTOS_CORS           origens liberadas (padrão *)
PRODUTOS_ATUALIZAR      1 (padrão): ao subir sem nenhuma base, e uma vez por dia, busca o mês novo de cada base
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _lista(v: str) -> list[str]:
    return [x.strip() for x in v.split(",") if x.strip()]


@dataclass(frozen=True)
class Configuracao:
    dados: Path
    chaves: frozenset[str]
    cors: list[str]
    atualizar: bool = True

    @classmethod
    def do_ambiente(cls, env: dict[str, str] | None = None) -> Configuracao:
        e = os.environ if env is None else env
        return cls(
            dados=Path(e.get("PRODUTOS_DADOS", "dados_produtos")),
            chaves=frozenset(_lista(e.get("PRODUTOS_API_KEYS", ""))),
            cors=_lista(e.get("PRODUTOS_CORS", "*")),
            atualizar=e.get("PRODUTOS_ATUALIZAR", "1") != "0",
        )
