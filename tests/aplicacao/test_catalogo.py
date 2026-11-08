import pytest

from canteiro_products.aplicacao.casos_de_uso import Catalogo
from canteiro_products.dominio.erros import NaoEncontrado, PedidoInvalido
from canteiro_products.infraestrutura.sqlite import RepositorioSqlite
from tests.falsos import FonteFalsa, planilha_sinapi, zip_da_caixa


@pytest.fixture
def catalogo(tmp_path):
    c = Catalogo(RepositorioSqlite(tmp_path / "p.sqlite"), {"sinapi": FonteFalsa()})
    c.importar("sinapi")
    return c


def test_bases_e_meses(catalogo):
    (b,) = catalogo.bases()
    assert b["base"] == "sinapi" and b["meses"] == ["2026-09"] and "Caixa" in b["orgao"]


def test_buscar_sem_acento_em_qualquer_ordem_com_preco_na_uf(catalogo):
    r = catalogo.buscar("vergalhao 10 aco", uf="mg")
    assert [(i["codigo"], i["preco_centavos"]) for i in r["itens"]] == [("34", 710)]
    r = catalogo.buscar("alvenaria ceramicos", tipo="composicao")
    assert r["itens"][0]["codigo"] == "89290" and r["itens"][0]["preco_centavos"] == 10063


def test_exclusao_e_pela_palavra_inteira(catalogo):
    # "-bomba" não tira o concreto "BOMBEAVEL"; "-bombeamento" tira
    assert [i["codigo"] for i in catalogo.buscar("concreto -bomba")["itens"]] == ["34494"]
    assert catalogo.buscar("concreto -bombeamento")["itens"] == []


def test_detalhar_composicao_fecha_como_o_sinapi(catalogo):
    d = catalogo.detalhar("sinapi", "composicao", "89290", uf="SP")
    assert d["preco_centavos"] == 10063 and d["precos_por_uf"] == {"SP": 10063}
    assert [(i["codigo"], i["parcial_centavos"]) for i in d["itens"]] == [("88309", 3494), ("34586", 3335)]
    assert d["historico"] == [{"mes": "2026-09", "centavos": 10063}]


def test_desonerado_e_historico_de_varios_meses(tmp_path):
    fonte = FonteFalsa()
    c = Catalogo(RepositorioSqlite(tmp_path / "p.sqlite"), {"sinapi": fonte})
    c.importar("sinapi", arquivo=zip_da_caixa(planilha_sinapi("08/2026")))
    c.importar("sinapi", arquivo=zip_da_caixa(planilha_sinapi("09/2026")))
    assert c.bases()[0]["meses"] == ["2026-09", "2026-08"]
    d = c.detalhar("sinapi", "insumo", "34", uf="SP", desonerado=True)
    assert d["mes"] == "2026-09" and d["preco_centavos"] == 602
    assert [h["mes"] for h in d["historico"]] == ["2026-08", "2026-09"]
    # reimportar o mesmo mês substitui, não duplica
    c.importar("sinapi", arquivo=zip_da_caixa(planilha_sinapi("09/2026")))
    assert len(c.buscar("vergalhao")["itens"]) == 1


def test_pedidos_invalidos_e_nao_encontrado(catalogo, tmp_path):
    for kw in ({"q": ""}, {"q": "aco", "uf": "XX"}, {"q": "aco", "tipo": "servico"}, {"q": "aco", "base": "orse"}):
        with pytest.raises(PedidoInvalido):
            catalogo.buscar(**kw)
    with pytest.raises(NaoEncontrado):
        catalogo.detalhar("sinapi", "insumo", "999999")
    with pytest.raises(NaoEncontrado):
        Catalogo(RepositorioSqlite(tmp_path / "vazio.sqlite"), {"sinapi": FonteFalsa()}).detalhar(
            "sinapi", "insumo", "34"
        )
