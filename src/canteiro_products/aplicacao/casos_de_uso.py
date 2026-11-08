"""Casos de uso do catálogo de produtos e preços da construção."""

from __future__ import annotations

from decimal import Decimal

from canteiro_products.dominio.busca import interpretar
from canteiro_products.dominio.erros import NaoEncontrado, PedidoInvalido
from canteiro_products.dominio.modelos import UFS, Tipo

from .portas import FonteDeBase, Repositorio

LIMITE_MAXIMO = 200


def _parcial(preco_centavos: int | None, coeficiente: float) -> int | None:
    """Coeficiente × preço truncado no centavo, como a planilha do SINAPI faz (TRUNC(E*F;2)): arredondar dava alguns
    centavos de diferença no total da composição."""
    if preco_centavos is None:
        return None
    return int(Decimal(str(coeficiente)) * preco_centavos)


class Catalogo:
    def __init__(self, repositorio: Repositorio, fontes: dict[str, FonteDeBase]):
        self.repo, self.fontes = repositorio, fontes

    # ------------------------------------------------------------------ consulta

    def bases(self) -> list[dict]:
        out = []
        for sigla, f in sorted(self.fontes.items()):
            meses = sorted({r.mes for r in self.repo.referencias(sigla)}, reverse=True)
            b = f.base
            out.append({"base": sigla, "nome": b.nome, "orgao": b.orgao, "abrangencia": b.abrangencia,
                        "fonte_url": b.fonte_url, "meses": meses})  # fmt: skip
        return out

    def buscar(self, q: str, *, tipo: str | None = None, base: str | None = None, uf: str = "SP",
               mes: str | None = None, desonerado: bool = False, limite: int = 50) -> dict:  # fmt: skip
        consulta = interpretar(q)
        if consulta.vazia:
            raise PedidoInvalido("Diga o que procura (ex.: concreto fck 30 bombeavel).")
        uf = self._uf(uf)
        t = self._tipo(tipo)
        if base and base not in self.fontes:
            raise PedidoInvalido(f"Base '{base}' não existe aqui. Bases: {', '.join(sorted(self.fontes))}.")
        achados = self.repo.buscar(consulta, tipo=t, base=base, mes=mes, uf=uf, desonerado=desonerado,
                                   limite=max(1, min(limite, LIMITE_MAXIMO)))  # fmt: skip
        return {
            "consulta": {"contem": list(consulta.contem), "nao_contem": list(consulta.nao_contem)},
            "uf": uf,
            "desonerado": desonerado,
            "itens": [{**self._item(i), "mes": m, "preco_centavos": p} for i, m, p in achados],
        }

    def detalhar(self, base: str, tipo: str, codigo: str, *, uf: str = "SP", mes: str | None = None,
                 desonerado: bool = False) -> dict:  # fmt: skip
        uf, t = self._uf(uf), self._tipo(tipo)
        if t is None:
            raise PedidoInvalido("Tipo é insumo ou composicao.")
        mes = mes or self._mes_mais_novo(base)
        item = self.repo.obter(base, t, codigo, mes)
        if item is None:
            raise NaoEncontrado(f"{t.value.capitalize()} {codigo} não existe na base {base} em {mes}.")
        precos = self.repo.precos(base, t, codigo, mes)
        aqui = next((p.centavos for p in precos if p.uf == uf and p.desonerado == desonerado), None)
        out = {
            **self._item(item),
            "mes": mes,
            "uf": uf,
            "desonerado": desonerado,
            "preco_centavos": aqui,
            "precos_por_uf": {p.uf: p.centavos for p in precos if p.desonerado == desonerado},
            "historico": [{"mes": m, "centavos": c} for m, c in self.repo.historico(base, t, codigo, uf, desonerado)],
        }
        if t is Tipo.COMPOSICAO:
            out["itens"] = self._analitico(base, codigo, mes, uf, desonerado)
        return out

    def _analitico(self, base: str, codigo: str, mes: str, uf: str, desonerado: bool) -> list[dict]:
        itens = []
        for it in self.repo.analitico(base, codigo, mes):
            p = next((x.centavos for x in self.repo.precos(base, it.tipo, it.codigo, mes)
                      if x.uf == uf and x.desonerado == desonerado), None)  # fmt: skip
            itens.append({"tipo": it.tipo.value, "codigo": it.codigo, "descricao": it.descricao, "unidade": it.unidade,
                          "coeficiente": it.coeficiente, "situacao": it.situacao, "preco_centavos": p,
                          "parcial_centavos": _parcial(p, it.coeficiente)})  # fmt: skip
        return itens

    # ------------------------------------------------------------------ importação

    def importar(self, base: str, *, arquivo: bytes | None = None, mes: str | None = None) -> dict:
        """Lê o arquivo do órgão (o dado, ou os baixados agora: um ou um por UF) e grava. Reimportar substitui."""
        fonte = self.fontes.get(base)
        if fonte is None:
            raise PedidoInvalido(f"Base '{base}' não existe aqui. Bases: {', '.join(sorted(self.fontes))}.")
        arquivos = [arquivo] if arquivo is not None else fonte.baixar(mes or fonte.ultimo_mes())
        resumo = {"base": base, "mes": None, "ufs": [], "insumos": 0, "composicoes": 0, "precos": 0}
        for arq in arquivos:
            lote = fonte.ler(arq)
            self.repo.gravar_lote(lote)
            resumo["mes"] = lote.referencia.mes
            resumo["ufs"] += list(lote.ufs or [])
            resumo["insumos"] = max(resumo["insumos"], sum(i.tipo is Tipo.INSUMO for i in lote.itens))
            resumo["composicoes"] = max(resumo["composicoes"], sum(i.tipo is Tipo.COMPOSICAO for i in lote.itens))
            resumo["precos"] += sum(len(v) for v in lote.precos.values())
        return resumo

    def atualizar(self, base: str) -> dict | None:
        """Importa o mês mais novo publicado se ele ainda não está aqui; None se já está em dia."""
        mes = self.fontes[base].ultimo_mes()
        if mes in {r.mes for r in self.repo.referencias(base)}:
            return None
        return self.importar(base, mes=mes)

    # ------------------------------------------------------------------ ajudas

    def _mes_mais_novo(self, base: str) -> str:
        meses = sorted({r.mes for r in self.repo.referencias(base)})
        if not meses:
            raise NaoEncontrado(f"A base {base} ainda não foi importada.")
        return meses[-1]

    @staticmethod
    def _uf(uf: str) -> str:
        u = (uf or "").upper()
        if u not in UFS:
            raise PedidoInvalido("UF com duas letras (SP, MG...).")
        return u

    @staticmethod
    def _tipo(tipo: str | None) -> Tipo | None:
        if not tipo:
            return None
        try:
            return Tipo(tipo)
        except ValueError:
            raise PedidoInvalido("Tipo é insumo ou composicao.") from None

    @staticmethod
    def _item(i) -> dict:
        return {"base": i.base, "tipo": i.tipo.value, "codigo": i.codigo, "descricao": i.descricao,
                "unidade": i.unidade, "grupo": i.grupo}  # fmt: skip
