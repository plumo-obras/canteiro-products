"""O que existe no mercado da construção, segundo as bases oficiais de custos.

Uma **base** (SINAPI, SICRO, ORSE...) é publicada por um órgão público, em **referências** mensais. Cada referência traz
**insumos** (material, mão de obra, equipamento: o que se compra) e **composições** (serviços: o que se executa, com
os itens e os coeficientes), com o preço ou custo por UF. Dinheiro em centavos, como no resto do Plumo; coeficiente e
preço unitário ficam como a base publica, para a conta da composição fechar com a dela.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

UFS = (
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR",
    "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO",
)  # fmt: skip
_MES = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


class Tipo(StrEnum):
    INSUMO = "insumo"
    COMPOSICAO = "composicao"


@dataclass(frozen=True)
class Base:
    sigla: str  # "sinapi"
    nome: str
    orgao: str
    abrangencia: str  # "nacional (27 UF)", "SE"...
    fonte_url: str


@dataclass(frozen=True)
class Referencia:
    """Um mês de uma base. A desoneração (encargos sociais com ou sem) muda o custo da mão de obra, então os preços
    de cada referência vêm nos dois regimes."""

    base: str
    mes: str  # "AAAA-MM"

    def __post_init__(self) -> None:
        if not _MES.match(self.mes):
            raise ValueError(f"mês de referência inválido: {self.mes!r} (use AAAA-MM)")


@dataclass(frozen=True)
class Item:
    """Um insumo ou uma composição de uma base. O código é o da base (texto: há bases com letras)."""

    base: str
    tipo: Tipo
    codigo: str
    descricao: str
    unidade: str
    grupo: str = ""  # classificação do insumo (MATERIAL, MAO DE OBRA...) ou grupo da composição


@dataclass(frozen=True)
class Preco:
    uf: str
    desonerado: bool
    centavos: int


@dataclass(frozen=True)
class ItemDaComposicao:
    tipo: Tipo
    codigo: str
    descricao: str
    unidade: str
    coeficiente: float
    situacao: str = ""  # "COM PREÇO", "COM CUSTO", "SEM PREÇO"... como a base publica


@dataclass
class LoteDeReferencia:
    """Tudo que uma referência traz, já lido da planilha da base: é o que se grava de uma vez."""

    referencia: Referencia
    itens: list[Item] = field(default_factory=list)
    precos: dict[tuple[Tipo, str], list[Preco]] = field(default_factory=dict)
    analiticos: dict[str, list[ItemDaComposicao]] = field(default_factory=dict)  # código da composição -> itens
    # bases publicadas por UF (o SICRO é um arquivo por estado): o lote só substitui os preços destas UFs, e os itens
    # entram ou se atualizam sem apagar os das outras. None = a referência inteira (SINAPI, nacional).
    ufs: tuple[str, ...] | None = None
