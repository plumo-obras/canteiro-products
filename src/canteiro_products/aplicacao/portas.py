"""Portas: o que os casos de uso pedem de fora. A infraestrutura implementa (SQLite, o leitor de cada base); os testes
trocam por versões em memória."""

from __future__ import annotations

from typing import Protocol

from canteiro_products.dominio.busca import Consulta
from canteiro_products.dominio.modelos import Base, Item, ItemDaComposicao, LoteDeReferencia, Preco, Referencia, Tipo


class Repositorio(Protocol):
    def gravar_lote(self, lote: LoteDeReferencia) -> None:
        """Grava a referência inteira; gravar o mesmo mês de novo substitui (importar é idempotente)."""
        ...

    def referencias(self, base: str | None = None) -> list[Referencia]: ...

    def buscar(
        self,
        consulta: Consulta,
        *,
        tipo: Tipo | None,
        base: str | None,
        mes: str | None,
        uf: str,
        desonerado: bool,
        limite: int,
    ) -> list[tuple[Item, str, int | None]]:
        """(item, mês, preço na UF em centavos ou None), do mês pedido ou do mais novo de cada base."""
        ...  # fmt: skip

    def obter(self, base: str, tipo: Tipo, codigo: str, mes: str) -> Item | None: ...

    def precos(self, base: str, tipo: Tipo, codigo: str, mes: str) -> list[Preco]: ...

    def historico(self, base: str, tipo: Tipo, codigo: str, uf: str, desonerado: bool) -> list[tuple[str, int]]: ...

    def analitico(self, base: str, codigo: str, mes: str) -> list[ItemDaComposicao]: ...


class FonteDeBase(Protocol):
    """Uma base oficial: de onde se baixa o arquivo do mês e como se lê."""

    base: Base

    def baixar(self, mes: str | None) -> tuple[str, bytes]:
        """O arquivo do mês (ou do mais novo publicado) e o mês que ele traz. Levanta BaseIndisponivel."""
        ...

    def ler(self, arquivo: bytes) -> LoteDeReferencia: ...
