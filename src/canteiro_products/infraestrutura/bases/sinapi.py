"""SINAPI (Caixa + IBGE): a base nacional de custos da construção civil, publicada todo mês.

A Caixa publica um ZIP nacional por mês (`SINAPI-AAAA-MM-formato-xlsx.zip`). A planilha de referência (a maior do ZIP)
tem os insumos (ISD sem desoneração, ICD com), as composições (CSD, CCD) com o custo nas 27 UF e o Analítico (os itens
de cada composição com o coeficiente). Texto do SINAPI é dado público, nunca instrução.
"""

from __future__ import annotations

import io
import re
import zipfile
from datetime import date

import httpx

from canteiro_products.dominio.erros import BaseIndisponivel
from canteiro_products.dominio.modelos import (
    UFS,
    Base,
    Item,
    ItemDaComposicao,
    LoteDeReferencia,
    Preco,
    Referencia,
    Tipo,
)

BASE = Base(
    sigla="sinapi",
    nome="SINAPI — Sistema Nacional de Pesquisa de Custos e Índices da Construção Civil",
    orgao="Caixa Econômica Federal e IBGE",
    abrangencia="nacional (27 UF)",
    fonte_url="https://www.caixa.gov.br/poder-publico/modernizacao-gestao/sinapi",
)
URL_MENSAL = "https://www.caixa.gov.br/Downloads/sinapi-relatorios-mensais/SINAPI-{ano}-{mes:02d}-formato-xlsx.zip"
# o portal responde em loop de redirecionamento para quem não parece navegador
CABECALHOS = {"User-Agent": "Mozilla/5.0 (canteiro-products; base SINAPI)"}
INSUMOS = {"ISD": False, "ICD": True}  # aba -> desonerado
COMPOSICOES = {"CSD": False, "CCD": True}
_CODIGO_NA_FORMULA = re.compile(r",\s*(\d+)\s*\)\s*$")  # =HYPERLINK(..., 104658)


class FonteSinapi:
    base = BASE

    def __init__(self, timeout: float = 120, hoje: date | None = None):
        self.timeout, self.hoje = timeout, hoje

    # ------------------------------------------------------------------ download

    def baixar(self, mes: str | None) -> tuple[str, bytes]:
        candidatos = [tuple(int(x) for x in mes.split("-"))] if mes else _meses_anteriores(self.hoje or date.today())
        erros = []
        with httpx.Client(timeout=self.timeout, follow_redirects=True, headers=CABECALHOS) as c:
            for a, m in candidatos:
                r = c.get(URL_MENSAL.format(ano=a, mes=m))
                if r.status_code == 200 and r.content[:2] == b"PK":
                    return f"{a}-{m:02d}", r.content
                erros.append(f"{a}-{m:02d}: {r.status_code}")
        dica = (
            " A Caixa limita downloads repetidos (429): tente mais tarde ou baixe o ZIP no navegador e importe"
            " o arquivo."
            if any(e.endswith(": 429") for e in erros)
            else ""
        )
        raise BaseIndisponivel("SINAPI não encontrado na Caixa (" + ", ".join(erros) + ")." + dica)

    # ------------------------------------------------------------------ leitura

    def ler(self, arquivo: bytes) -> LoteDeReferencia:
        import openpyxl

        dados = _planilha_de_referencia(arquivo) if _eh_zip_de_planilhas(arquivo) else arquivo
        # sem data_only: o código da composição vem dentro de um HYPERLINK, e o valor em cache dele é 0
        wb = openpyxl.load_workbook(io.BytesIO(dados), read_only=True)
        faltam = [a for a in (*INSUMOS, *COMPOSICOES, "Analítico") if a not in wb.sheetnames]
        if faltam:
            raise ValueError(f"esta planilha não é a de referência do SINAPI (faltam as abas {', '.join(faltam)})")
        mes = _mes(wb["ISD"])
        lote = LoteDeReferencia(Referencia("sinapi", mes))
        vistos: set[tuple[Tipo, str]] = set()
        for aba, deson in INSUMOS.items():
            self._insumos(wb[aba], deson, lote, vistos)
        for aba, deson in COMPOSICOES.items():
            self._composicoes(wb[aba], deson, lote, vistos)
        self._analitico(wb["Analítico"], lote)
        return lote

    def _insumos(self, ws, desonerado: bool, lote: LoteDeReferencia, vistos: set) -> None:
        colunas = None
        for linha in ws.iter_rows(values_only=True):
            if linha and linha[0] == "Classificação":
                colunas = {uf: i for i, uf in enumerate(linha) if uf in UFS}
            elif colunas and linha and isinstance(linha[1], int):
                cod = str(linha[1])
                if (Tipo.INSUMO, cod) not in vistos:
                    vistos.add((Tipo.INSUMO, cod))
                    lote.itens.append(Item("sinapi", Tipo.INSUMO, cod, _txt(linha[2]), _txt(linha[3]), _txt(linha[0])))
                lote.precos.setdefault((Tipo.INSUMO, cod), []).extend(
                    Preco(uf, desonerado, round(linha[i] * 100))
                    for uf, i in colunas.items()
                    if isinstance(linha[i], int | float)
                )

    def _composicoes(self, ws, desonerado: bool, lote: LoteDeReferencia, vistos: set) -> None:
        ufs, cabecalho = None, False
        for linha in ws.iter_rows(values_only=True):
            if not linha:
                continue
            if not cabecalho and linha[4] in UFS and linha[6] in UFS:
                ufs = {uf: i for i, uf in enumerate(linha) if uf in UFS}  # a linha das UFs, acima do cabeçalho
            elif linha[0] == "Grupo":
                cabecalho = True
            elif cabecalho and ufs and linha[2]:
                cod = _codigo(linha[1])
                if not cod:
                    continue
                if (Tipo.COMPOSICAO, cod) not in vistos:
                    vistos.add((Tipo.COMPOSICAO, cod))
                    lote.itens.append(
                        Item("sinapi", Tipo.COMPOSICAO, cod, _txt(linha[2]), _txt(linha[3]), _txt(linha[0]))
                    )
                lote.precos.setdefault((Tipo.COMPOSICAO, cod), []).extend(
                    Preco(uf, desonerado, round(linha[i] * 100))
                    for uf, i in ufs.items()
                    if isinstance(linha[i], int | float) and linha[i] > 0  # custo zerado = falta preço de um item
                )

    def _analitico(self, ws, lote: LoteDeReferencia) -> None:
        cabecalho = False
        for linha in ws.iter_rows(values_only=True):
            if not linha:
                continue
            if linha[0] == "Grupo":
                cabecalho = True
            elif cabecalho and linha[2] in ("INSUMO", "COMPOSICAO") and isinstance(linha[3], int):
                lote.analiticos.setdefault(str(linha[1]), []).append(ItemDaComposicao(
                    tipo=Tipo.INSUMO if linha[2] == "INSUMO" else Tipo.COMPOSICAO, codigo=str(linha[3]),
                    descricao=_txt(linha[4]), unidade=_txt(linha[5]), coeficiente=float(linha[6] or 0),
                    situacao=_txt(linha[7]),
                ))  # fmt: skip


def _meses_anteriores(hoje: date, quantos: int = 6) -> list[tuple[int, int]]:
    # a Caixa publica o mês M por volta do dia 10 de M+1
    a, m, out = hoje.year, hoje.month, []
    for _ in range(quantos):
        m -= 1
        if m == 0:
            a, m = a - 1, 12
        out.append((a, m))
    return out


def _mes(ws) -> str:
    for linha in ws.iter_rows(max_row=10, values_only=True):
        if linha and linha[0] == "Mês de Referência:":
            m, a = str(linha[1]).split("/")
            return f"{a}-{int(m):02d}"
    raise ValueError("não achei o mês de referência na aba ISD")


def _codigo(valor) -> str | None:
    if isinstance(valor, int) and valor > 0:
        return str(valor)
    m = _CODIGO_NA_FORMULA.search(str(valor or ""))
    return m.group(1) if m else None


def _txt(v) -> str:
    return str(v).strip() if v is not None else ""


def _eh_zip_de_planilhas(dados: bytes) -> bool:
    if dados[:2] != b"PK":
        return False
    with zipfile.ZipFile(io.BytesIO(dados)) as z:
        nomes = z.namelist()
        return "[Content_Types].xml" not in nomes and any(n.lower().endswith(".xlsx") for n in nomes)


def _planilha_de_referencia(zip_: bytes) -> bytes:
    # o nome vem com acento em codificação variável ("Refer+�ncia"): a de referência é a maior planilha do ZIP
    with zipfile.ZipFile(io.BytesIO(zip_)) as z:
        info = max((i for i in z.infolist() if i.filename.lower().endswith(".xlsx")), key=lambda i: i.file_size)
        return z.read(info)
