from datetime import date

from canteiro_products.dominio.modelos import Tipo
from canteiro_products.infraestrutura.bases.sinapi import FonteSinapi, _meses_anteriores
from tests.falsos import zip_da_caixa


def test_le_o_zip_da_caixa_com_os_dois_regimes_e_o_analitico():
    lote = FonteSinapi().ler(zip_da_caixa())
    assert lote.referencia.mes == "2026-09"
    assert {(i.tipo, i.codigo) for i in lote.itens} == {
        (Tipo.INSUMO, "34"), (Tipo.INSUMO, "34494"), (Tipo.INSUMO, "34586"),
        (Tipo.COMPOSICAO, "89290"), (Tipo.COMPOSICAO, "88309"),
    }  # fmt: skip
    aco = {(p.uf, p.desonerado): p.centavos for p in lote.precos[(Tipo.INSUMO, "34")]}
    assert aco == {("SP", False): 669, ("MG", False): 710, ("SP", True): 602, ("MG", True): 639}
    # UF sem coleta fica sem preço; composição com custo zerado (item sem preço) também
    assert ("MG", False) not in {(p.uf, p.desonerado) for p in lote.precos[(Tipo.INSUMO, "34494")]}
    assert ("MG", False) not in {(p.uf, p.desonerado) for p in lote.precos[(Tipo.COMPOSICAO, "89290")]}
    itens = lote.analiticos["89290"]
    assert [(i.tipo, i.codigo, i.coeficiente) for i in itens] == [
        (Tipo.COMPOSICAO, "88309", 0.9379), (Tipo.INSUMO, "34586", 15.37)]  # fmt: skip


def test_meses_candidatos_comecam_no_anterior():
    assert _meses_anteriores(date(2026, 1, 20), 3) == [(2025, 12), (2025, 11), (2025, 10)]
