"""API HTTP do catálogo de produtos e preços da construção.

    GET /v1/bases                                    as bases e os meses importados
    GET /v1/itens?q=concreto fck 30&uf=SP             busca (insumos e composições; tipo=, base=, mes=, desonerado=)
    GET /v1/itens/{base}/{tipo}/{codigo}?uf=SP        o item: preço na UF, preço por UF, histórico e, na composição, os
                                                     itens com coeficiente e o custo de cada um

Aqui só se traduz HTTP <-> casos de uso. Importar é pela linha de comando (`importar-base`) ou sozinho, uma vez por dia.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from canteiro_products import VERSAO_SERVICO
from canteiro_products.aplicacao.casos_de_uso import Catalogo
from canteiro_products.dominio.erros import BaseIndisponivel, ErroDeProdutos, NaoEncontrado, PedidoInvalido
from canteiro_products.infraestrutura.bases.sicro import FonteSicro
from canteiro_products.infraestrutura.bases.sinapi import FonteSinapi
from canteiro_products.infraestrutura.sqlite import RepositorioSqlite

from .configuracao import Configuracao

CODIGO = {NaoEncontrado: 404, PedidoInvalido: 422, BaseIndisponivel: 503}
UM_DIA = 24 * 3600


def montar_catalogo(cfg: Configuracao) -> Catalogo:
    fontes = {"sinapi": FonteSinapi(), "sicro": FonteSicro()}
    return Catalogo(RepositorioSqlite(cfg.dados / "produtos.sqlite"), fontes)


def _atualizar_sem_derrubar(catalogo: Catalogo, pre_carregar: tuple[str, ...] = ()) -> None:
    """Importa o mês mais novo de cada base que ainda não está aqui. Falhar (sem internet, órgão limitando) é só log."""
    for sigla in sorted(catalogo.fontes):
        try:
            r = catalogo.atualizar(sigla)
            if r:
                n = f"{r['insumos']} insumos, {r['composicoes']} composições"
                print(f"{sigla}: {r['mes']} importado ({n})", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"{sigla}: não atualizado agora: {e}", flush=True)
    for uf in pre_carregar:
        try:
            if catalogo.garantir_uf("sicro", uf):
                print(f"sicro: {uf} carregado", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"sicro {uf}: não carregado agora: {e}", flush=True)


def criar_app(cfg: Configuracao | None = None, catalogo: Catalogo | None = None) -> FastAPI:
    cfg = cfg or Configuracao.do_ambiente()
    catalogo = catalogo or montar_catalogo(cfg)

    @contextlib.asynccontextmanager
    async def ciclo(_app: FastAPI) -> AsyncIterator[None]:
        async def todo_dia() -> None:
            while True:
                await asyncio.to_thread(_atualizar_sem_derrubar, catalogo, cfg.sicro_ufs)
                await asyncio.sleep(UM_DIA)

        tarefa = asyncio.create_task(todo_dia()) if cfg.atualizar else None
        try:
            yield
        finally:
            if tarefa:
                tarefa.cancel()

    app = FastAPI(
        title="Produtos e preços da construção",
        version=VERSAO_SERVICO,
        description="As bases oficiais de custos da construção (SINAPI...) para o Plumo: busca, item e composição.",
        lifespan=ciclo,
    )
    app.add_middleware(CORSMiddleware, allow_origins=cfg.cors, allow_methods=["GET"], allow_headers=["*"])

    @app.exception_handler(ErroDeProdutos)
    async def _erro(_req: Request, e: ErroDeProdutos) -> JSONResponse:
        return JSONResponse({"detail": str(e)}, status_code=CODIGO.get(type(e), 400))

    def autenticar(request: Request) -> None:
        if cfg.chaves and request.headers.get("x-api-key") not in cfg.chaves:
            raise HTTPException(401, "Envie uma chave válida no cabeçalho X-API-Key.")

    protegido = [Depends(autenticar)]

    @app.get("/v1/saude", tags=["serviço"])
    def saude() -> dict:
        return {"status": "ok", "versao_servico": VERSAO_SERVICO}

    @app.get("/v1/bases", tags=["catálogo"], dependencies=protegido)
    def bases() -> list[dict]:
        return catalogo.bases()

    @app.get("/v1/itens", tags=["catálogo"], dependencies=protegido)
    def buscar(
        q: str = Query(..., description="termos soltos, sem acento; '-termo' exclui"),
        tipo: str | None = Query(None, description="insumo | composicao"),
        base: str | None = Query(None),
        uf: str = Query("SP"),
        mes: str | None = Query(None, description="AAAA-MM; padrão: o mais novo de cada base"),
        desonerado: bool = Query(False, description="encargos sociais com desoneração"),
        limite: int = Query(50, ge=1, le=200),
    ) -> dict:
        return catalogo.buscar(q, tipo=tipo, base=base, uf=uf, mes=mes, desonerado=desonerado, limite=limite)

    @app.get("/v1/itens/{base}/{tipo}/{codigo}", tags=["catálogo"], dependencies=protegido)
    def detalhar(base: str, tipo: str, codigo: str, uf: str = "SP", mes: str | None = None,
                 desonerado: bool = False) -> dict:  # fmt: skip
        return catalogo.detalhar(base, tipo, codigo, uf=uf, mes=mes, desonerado=desonerado)

    return app
