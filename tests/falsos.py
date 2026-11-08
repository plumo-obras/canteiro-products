"""Uma planilha de referência no formato da Caixa (abas ISD, ICD, CSD, CCD e Analítico), montada no teste com linhas do
SINAPI (dado público): o leitor tem de achar o mês, os preços nos dois regimes e o código dentro do HYPERLINK."""

from __future__ import annotations

import io
import zipfile

import openpyxl

UFS_TESTE = ["SP", "MG"]
INSUMOS = [  # classificação, código, descrição, unidade, SP, MG
    ("MATERIAL", 34, "ACO CA-50, 10,0 MM, VERGALHAO", "KG", 6.69, 7.10),
    ("MATERIAL", 34494, "CONCRETO USINADO BOMBEAVEL, CLASSE DE RESISTENCIA C30, COM BRITA 0 E 1, SLUMP = 100 +/- 20 MM,"
     " EXCLUI SERVICO DE BOMBEAMENTO (NBR 8953)", "M3", 512.63, None),
    ("MATERIAL", 34586, "BLOCO ESTRUTURAL CERAMICO DE 14 X 19 X 29 CM", "UN", 2.17, 2.30),
]  # fmt: skip
COMPOSICOES = [  # grupo, código, descrição, unidade, SP, MG
    ("Alvenaria", 89290, "ALVENARIA ESTRUTURAL DE BLOCOS CERÂMICOS 14X19X29 CM, FBK = 6 MPA", "M2", 100.63, 0),
    ("Pessoal", 88309, "PEDREIRO COM ENCARGOS COMPLEMENTARES", "H", 37.26, 33.10),
]
ANALITICO = [  # composição, tipo, código, descrição, unidade, coeficiente
    (89290, "COMPOSICAO", 88309, "PEDREIRO COM ENCARGOS COMPLEMENTARES", "H", 0.9379),
    (89290, "INSUMO", 34586, "BLOCO ESTRUTURAL CERAMICO DE 14 X 19 X 29 CM", "UN", 15.37),
]


def planilha_sinapi(mes: str = "09/2026", fator_desonerado: float = 0.9) -> bytes:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for aba, f in (("ISD", 1.0), ("ICD", fator_desonerado)):
        ws = wb.create_sheet(aba)
        ws.append(["SINAPI"])
        ws.append(["Mês de Referência:", mes])
        ws.append(["Classificação", "Código do\nInsumo", "Descrição do Insumo", "Unidade", "Origem", *UFS_TESTE])
        for cls, cod, desc, un, sp, mg in INSUMOS:
            ws.append([cls, cod, desc, un, "C", round(sp * f, 2), None if mg is None else round(mg * f, 2)])
    for aba, f in (("CSD", 1.0), ("CCD", fator_desonerado)):
        ws = wb.create_sheet(aba)
        ws.append(["SINAPI"])
        ws.append(["Mês de Referência:", mes])
        ws.append([None, None, None, None, "SP", None, "MG", None])
        ws.append(["Grupo", "Código da\nComposição", "Descrição", "Unidade", "Custo (R$)", "%AS", "Custo (R$)", "%AS"])
        for grupo, cod, desc, un, sp, mg in COMPOSICOES:
            link = f'=HYPERLINK("#"&CELL("address",OFFSET(Analítico!$B$1,MATCH({cod},Analítico!$B:$B,0)-1,3)),{cod})'
            ws.append([grupo, link, desc, un, round(sp * f, 2), 0, round(mg * f, 2), 0])
    ws = wb.create_sheet("Analítico")
    ws.append(["SINAPI"])
    ws.append(["Grupo", "Código da\nComposição", "Tipo Item", "Código do\nItem", "Descrição", "Unidade", "Coeficiente",
               "Situação"])  # fmt: skip
    ws.append(["Alvenaria", 89290, None, None, COMPOSICOES[0][2], "M2", None, "COM CUSTO"])
    for comp, tipo, cod, desc, un, coef in ANALITICO:
        ws.append(["Alvenaria", comp, tipo, cod, desc, un, coef, "COM PREÇO" if tipo == "INSUMO" else "COM CUSTO"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def zip_da_caixa(planilha: bytes | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("SINAPI_mao_de_obra_2026_09.xlsx", b"x" * 10)
        z.writestr("SINAPI_Referência_2026_09.xlsx", planilha or planilha_sinapi())  # a maior é a de referência
    return buf.getvalue()


class FonteFalsa:
    """A fonte do SINAPI com a planilha do teste, sem rede."""

    def __init__(self, arquivo: bytes | None = None):
        from canteiro_products.infraestrutura.bases.sinapi import BASE, FonteSinapi

        self.base, self._leitor, self.arquivo, self.baixados = BASE, FonteSinapi(), arquivo or zip_da_caixa(), 0

    def ultimo_mes(self):
        return "2026-09"

    def baixar(self, mes):
        self.baixados += 1
        yield self.arquivo

    def ler(self, arquivo):
        return self._leitor.ler(arquivo)


def pacote_sicro(uf: str = "MG", mes: str = "01-2026", fator: float = 1.0) -> bytes:
    """Um pacote .7z do SICRO como o DNIT publica (um por UF), só com os relatórios sintéticos em Excel."""
    import py7zr

    def planilha(cabecalho, linhas) -> bytes:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(cabecalho)
        for linha in linhas:
            ws.append(linha)
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    equip = [
        "Código",
        "Descrição",
        "Aquisição",
        "Depr.",
        "Oport.",
        "Seg.",
        "Manut.",
        "Oper.",
        "MO oper.",
        "Custo Produtivo\n (R$/h)",
        "Improdutivo",
    ]  # noqa: E501
    eq = [("E9007", "Bomba de pistão triplex - 8,20 kW", 167178.57, 16.72, 3.22, 0, 14.63, 8.41, 0, 43.0 * fator, 20.0)]
    eq.append(eq[0])  # o DNIT publica alguns equipamentos em duas linhas iguais
    rel = {
        "Relatório Sintético de Materiais": planilha(["Código", "Descrição", "Unidade", "Preço"], [
            ("M0004", "Aço CA 50", "kg", 6.0065 * fator), ("M0453", "Concreto usinado - fck = 30 MPa", "m³", None)]),
        "Relatório Sintético de Mão de Obra": planilha(["Código", "Descrição", "Unidade", "Custo"], [
            ("P9801", "Ajudante", "h", 24.1561 * fator), (None, None, None, None)]),
        "Relatório Sintético de Mão de Obra - com desoneração": planilha(["Código", "Descrição", "Unidade", "Custo"], [
            ("P9801", "Ajudante", "h", 22.813 * fator)]),
        "Relatório Sintético de Equipamentos": planilha(equip, eq),
        "Relatório Sintético de Equipamentos - com desoneração": planilha(equip, eq),
        "Relatório Sintético de Composições de Custos": planilha(["Código", "Descrição", "Unidade", "Custo"], [
            ("0307731", "Aparelho de apoio de neoprene fretado", "dm³", 153.28 * fator)]),
    }  # fmt: skip
    buf = io.BytesIO()
    with py7zr.SevenZipFile(buf, "w") as z:
        for nome, dados in rel.items():
            z.writestr(dados, f"{uf} {mes} {nome}.xlsx")
        z.writestr(b"%PDF-1.4", f"{uf} {mes} Relatório Sintético de Materiais.pdf")
    return buf.getvalue()


class FonteSicroFalsa:
    """O SICRO sem rede: cada UF devolve o pacote do teste (devagar, para duas consultas baterem ao mesmo tempo)."""

    def __init__(self, mes: str = "2026-07", espera: float = 0.0):
        import threading

        from canteiro_products.infraestrutura.bases.sicro import BASE, FonteSicro

        self.base, self.por_uf, self._leitor, self.mes, self.espera = BASE, True, FonteSicro(), mes, espera
        self.baixadas: list[str] = []
        self._trava = threading.Lock()

    def ultimo_mes(self):
        return self.mes

    def baixar_uf(self, mes, uf):
        import time

        with self._trava:
            self.baixadas.append(uf)
        time.sleep(self.espera)
        a, m = mes.split("-")
        return pacote_sicro(uf, f"{m}-{a}", fator=1.1 if uf == "SP" else 1.0)

    def baixar(self, mes):
        yield self.baixar_uf(mes, "MG")

    def ler(self, arquivo):
        return self._leitor.ler(arquivo)
