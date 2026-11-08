from datetime import date

import pytest

from canteiro_products.aplicacao.casos_de_uso import Catalogo
from canteiro_products.dominio.erros import BaseIndisponivel
from canteiro_products.dominio.modelos import Tipo
from canteiro_products.infraestrutura.bases import sicro
from canteiro_products.infraestrutura.bases.sicro import FonteSicro, url
from canteiro_products.infraestrutura.sqlite import RepositorioSqlite
from tests.falsos import pacote_sicro


def test_le_o_pacote_da_uf():
    lote = FonteSicro().ler(pacote_sicro("MG", "01-2026"))
    assert (lote.referencia.mes, lote.ufs) == ("2026-01", ("MG",))
    precos = {(t, c): {(p.uf, p.desonerado): p.centavos for p in ps} for (t, c), ps in lote.precos.items()}
    # material vale nos dois regimes; mão de obra e equipamento têm um preço por regime
    assert precos[(Tipo.INSUMO, "M0004")] == {("MG", False): 601, ("MG", True): 601}
    assert precos[(Tipo.INSUMO, "P9801")] == {("MG", False): 2416, ("MG", True): 2281}
    assert precos[(Tipo.INSUMO, "E9007")] == {("MG", False): 4300, ("MG", True): 4300}  # o custo produtivo por hora
    assert precos[(Tipo.INSUMO, "M0453")] == {}  # sem preço publicado
    assert precos[(Tipo.COMPOSICAO, "0307731")] == {("MG", False): 15328}  # código com o zero da frente
    assert sum(1 for i in lote.itens if i.codigo == "E9007") == 1  # a linha repetida do DNIT entra uma vez


def test_url_do_portal_por_regiao_estado_e_mes():
    assert url("MG", "2026-01").endswith("/relatorios-sicro/sudeste/minas-gerais/2026/janeiro/mg-01-2026.7z")
    assert url("DF", "2026-07").endswith("/centro-oeste/distrito-federal/2026/julho/df-07-2026.7z")


def test_uf_por_uf_nao_apaga_a_outra(tmp_path):
    fonte = FonteSicro()
    c = Catalogo(RepositorioSqlite(tmp_path / "p.sqlite"), {"sicro": fonte})
    c.importar("sicro", arquivo=pacote_sicro("MG"))
    c.importar("sicro", arquivo=pacote_sicro("SP", fator=1.1))
    d = c.detalhar("sicro", "insumo", "P9801", uf="SP")
    assert d["precos_por_uf"] == {"MG": 2416, "SP": 2657}
    c.importar("sicro", arquivo=pacote_sicro("MG", fator=2))  # reimportar MG troca só MG
    assert c.detalhar("sicro", "insumo", "P9801", uf="SP")["precos_por_uf"] == {"MG": 4831, "SP": 2657}
    assert len(c.buscar("ajudante", base="sicro")["itens"]) == 1


def test_ultimo_mes_e_trimestral_e_respeita_o_429(monkeypatch):
    perguntados = []

    def existe(u, _assinatura):
        perguntados.append(u)
        return 206 if "/2026/julho/" in u else None

    monkeypatch.setattr(sicro._http, "existe", existe)
    assert FonteSicro(hoje=date(2026, 11, 8)).ultimo_mes() == "2026-07"
    assert all(m in u for u, m in zip(perguntados, ("outubro", "julho"), strict=True))  # só meses de trimestre
    monkeypatch.setattr(sicro._http, "existe", lambda u, a: 429)
    with pytest.raises(BaseIndisponivel, match="429"):
        FonteSicro(hoje=date(2026, 11, 8)).ultimo_mes()


def test_download_retoma_de_onde_o_portal_derrubou(monkeypatch):
    import httpx

    from canteiro_products.infraestrutura.bases import _http

    arquivo = b"7z\xbc\xaf\x27\x1c" + bytes(range(256)) * 40
    pedidos = []

    def responder(req: httpx.Request) -> httpx.Response:
        rng = req.headers.get("range")
        pedidos.append(rng)
        inicio = int(rng.split("=")[1].rstrip("-")) if rng else 0
        if not rng:  # a 1ª resposta promete tudo e cai no meio
            return httpx.Response(200, headers={"content-length": str(len(arquivo))}, content=_cai(arquivo[:3000]))
        return httpx.Response(206, content=arquivo[inicio:])

    def _cai(parte):
        def gerar():
            yield parte
            raise httpx.RemoteProtocolError("peer closed connection")

        return gerar()

    real = httpx.Client
    monkeypatch.setattr(_http.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(responder), **kw))
    monkeypatch.setattr(_http.time, "sleep", lambda s: None)
    assert _http.baixar("https://dnit/x.7z", b"7z", pausa=0) == arquivo
    assert pedidos == [None, "bytes=3000-"]
