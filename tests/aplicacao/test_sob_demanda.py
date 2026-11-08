"""SICRO UF a UF: a UF entra quando alguém pede preço nela, uma vez só, e daí em diante se atualiza sozinha."""

import threading
import time

import pytest

from canteiro_products.aplicacao.casos_de_uso import Catalogo
from canteiro_products.infraestrutura.sqlite import RepositorioSqlite
from tests.falsos import FonteSicroFalsa


@pytest.fixture
def montar(tmp_path):
    def _montar(**kw):
        fonte = FonteSicroFalsa(**kw)
        return Catalogo(RepositorioSqlite(tmp_path / "p.sqlite"), {"sicro": fonte}), fonte

    return _montar


def _esperar(cond, segundos=5.0):
    fim = time.monotonic() + segundos
    while time.monotonic() < fim and not cond():
        time.sleep(0.02)
    return cond()


def test_detalhe_numa_uf_nova_busca_a_uf_e_responde(montar):
    c, fonte = montar()
    d = c.detalhar("sicro", "insumo", "P9801", uf="SP")
    assert d["mes"] == "2026-07" and d["preco_centavos"] == 2657 and fonte.baixadas == ["SP"]
    c.detalhar("sicro", "insumo", "P9801", uf="SP")  # já está aqui: não baixa de novo
    assert fonte.baixadas == ["SP"]


def test_busca_responde_na_hora_e_carrega_a_uf_em_segundo_plano(montar):
    c, fonte = montar()
    r = c.buscar("ajudante", uf="MG")
    assert r["carregando"] == ["sicro/MG"]
    assert _esperar(lambda: c.buscar("ajudante", uf="MG")["carregando"] == [])
    assert c.buscar("ajudante", uf="MG")["itens"][0]["preco_centavos"] == 2416
    assert fonte.baixadas == ["MG"]


def test_duas_consultas_ao_mesmo_tempo_baixam_a_uf_uma_vez(montar):
    c, fonte = montar(espera=0.2)
    t = [threading.Thread(target=c.detalhar, args=("sicro", "insumo", "P9801"), kwargs={"uf": "RJ"}) for _ in range(4)]
    for x in t:
        x.start()
    for x in t:
        x.join()
    assert fonte.baixadas == ["RJ"]


def test_trimestre_novo_atualiza_so_as_ufs_usadas(montar, tmp_path):
    c, fonte = montar(mes="2026-04")
    c.detalhar("sicro", "insumo", "P9801", uf="SP")
    c.detalhar("sicro", "insumo", "P9801", uf="MG")
    assert c.atualizar("sicro") is None  # em dia
    fonte.mes, c._ultimo_mes = "2026-07", {}
    r = c.atualizar("sicro")
    assert r["mes"] == "2026-07" and r["ufs"] == ["MG", "SP"]
    assert fonte.baixadas == ["SP", "MG", "MG", "SP"]
    assert c.detalhar("sicro", "insumo", "P9801", uf="SP")["mes"] == "2026-07"


def test_atualizar_sem_uf_usada_nao_baixa_nada(montar):
    c, fonte = montar()
    assert c.atualizar("sicro") is None and fonte.baixadas == []
