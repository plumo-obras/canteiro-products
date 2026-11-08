import time

import pytest
from fastapi.testclient import TestClient

from canteiro_products.aplicacao.casos_de_uso import Catalogo
from canteiro_products.infraestrutura.sqlite import RepositorioSqlite
from canteiro_products.interfaces.http.app import criar_app
from canteiro_products.interfaces.http.configuracao import Configuracao
from tests.falsos import FonteFalsa


@pytest.fixture
def cli(tmp_path):
    cat = Catalogo(RepositorioSqlite(tmp_path / "p.sqlite"), {"sinapi": FonteFalsa()})
    cat.importar("sinapi")
    cfg = Configuracao.do_ambiente(
        {"PRODUTOS_DADOS": str(tmp_path), "PRODUTOS_API_KEYS": "k", "PRODUTOS_ATUALIZAR": "0"}
    )
    with TestClient(criar_app(cfg, cat)) as c:
        c.headers["X-API-Key"] = "k"
        yield c


def test_saude_e_chave(cli):
    assert cli.get("/v1/saude", headers={"X-API-Key": ""}).status_code == 200
    assert cli.get("/v1/bases", headers={"X-API-Key": "errada"}).status_code == 401


def test_bases_busca_e_detalhe(cli):
    assert cli.get("/v1/bases").json()[0]["meses"] == ["2026-09"]
    r = cli.get("/v1/itens", params={"q": "concreto c30", "uf": "SP"}).json()
    assert r["itens"][0]["codigo"] == "34494" and r["itens"][0]["preco_centavos"] == 51263
    d = cli.get("/v1/itens/sinapi/composicao/89290", params={"uf": "SP"}).json()
    assert len(d["itens"]) == 2


def test_erros_viram_codigos(cli):
    assert cli.get("/v1/itens", params={"q": " "}).status_code == 422
    assert cli.get("/v1/itens/sinapi/insumo/999").status_code == 404
    assert cli.get("/v1/itens/sinapi/servico/34").status_code == 422


def test_atualizacao_ao_subir_baixa_so_o_que_falta(tmp_path):
    fonte = FonteFalsa()
    cat = Catalogo(RepositorioSqlite(tmp_path / "p.sqlite"), {"sinapi": fonte})
    cfg = Configuracao.do_ambiente({"PRODUTOS_DADOS": str(tmp_path)})
    with TestClient(criar_app(cfg, cat)) as c:
        for _ in range(100):  # a atualização roda em segundo plano
            if cat.bases()[0]["meses"]:
                break
            time.sleep(0.05)
        assert c.get("/v1/bases").json()[0]["meses"] == ["2026-09"]
    assert fonte.baixados == 1
