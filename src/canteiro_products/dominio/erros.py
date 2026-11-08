"""Erros do domínio, com a mensagem para quem usa o serviço. A interface decide o código."""

from __future__ import annotations


class ErroDeProdutos(Exception):
    """Base: a mensagem já está em linguagem de gente."""


class NaoEncontrado(ErroDeProdutos):
    pass


class PedidoInvalido(ErroDeProdutos):
    pass


class BaseIndisponivel(ErroDeProdutos):
    """A base não publicou o mês, ou o órgão recusou o download (limite de acessos)."""
