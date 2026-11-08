import pytest

from canteiro_products.dominio.busca import interpretar, normalizar
from canteiro_products.dominio.modelos import Referencia


def test_normalizar_tira_acento_e_pontuacao():
    assert normalizar("Aço CA-50, Ø 10,0 mm") == "ACO CA 50 10 0 MM"
    assert normalizar("Concreto usinado bombeável") == "CONCRETO USINADO BOMBEAVEL"


def test_interpretar_termos_e_exclusao():
    c = interpretar("concreto  Concreto c30 -bomba -")
    assert c.contem == ("CONCRETO", "C30")  # repetido sai, e o "-" sozinho não é termo
    assert c.nao_contem == ("BOMBA",)
    assert interpretar("   ").vazia


@pytest.mark.parametrize("mes", ["2026-13", "26-09", "2026-9", ""])
def test_referencia_exige_mes_aaaa_mm(mes):
    with pytest.raises(ValueError):
        Referencia("sinapi", mes)
