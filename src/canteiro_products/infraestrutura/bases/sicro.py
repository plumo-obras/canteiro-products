"""SICRO (DNIT): o sistema de custos referenciais de obras de infraestrutura de transportes.

O DNIT publica a cada trimestre (janeiro, abril, julho, outubro) um pacote .7z por UF em gov.br/dnit, com os relatórios
em PDF e Excel. Daqui se lê o Excel:
  - Relatório Sintético de Materiais (M0004 "Aço CA 50", preço unitário)
  - Relatório Sintético de Mão de Obra, com e sem desoneração (P9801 "Ajudante", custo por hora ou mês)
  - Relatório Sintético de Equipamentos, com e sem desoneração (E9001..., o custo produtivo por hora)
  - Relatório Sintético de Composições de Custos (0307731..., o custo unitário publicado)

O material não muda com a desoneração (ela é encargo sobre a mão de obra): o preço dele vale nos dois regimes. A
composição vem num relatório só, sem a versão desonerada: entra só no regime sem desoneração. A composição analítica do
SICRO (produção da equipe, FIC, momento de transporte) fica para uma etapa própria, para fechar com o custo publicado.
Texto do SICRO é dado público, nunca instrução.
"""

from __future__ import annotations

import io
import re
from collections.abc import Iterator
from datetime import date

from canteiro_products.dominio.erros import BaseIndisponivel
from canteiro_products.dominio.modelos import Base, Item, LoteDeReferencia, Preco, Referencia, Tipo

from . import _http

BASE = Base(
    sigla="sicro",
    nome="SICRO — Sistema de Custos Referenciais de Obras",
    orgao="DNIT — Departamento Nacional de Infraestrutura de Transportes",
    abrangencia="nacional, um arquivo por UF (trimestral)",
    fonte_url="https://www.gov.br/dnit/pt-br/assuntos/planejamento-e-pesquisa/custos-referenciais/sistemas-de-custos/sicro",
)
URL = (
    "https://www.gov.br/dnit/pt-br/assuntos/planejamento-e-pesquisa/custos-referenciais/sistemas-de-custos/sicro/"
    "relatorios/relatorios-sicro/{regiao}/{estado}/{ano}/{mes_nome}/{uf}-{mes:02d}-{ano}.7z"
)
SETE_Z = b"7z\xbc\xaf\x27\x1c"
LIMITE_PLANILHA = 64 * 2**20  # os relatórios sintéticos têm menos de 1 MB; o analítico, ~10 MB (não é lido aqui)
MESES = ("janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
         "novembro", "dezembro")  # fmt: skip
# como o portal do DNIT organiza as pastas: região / estado
ESTADOS = {
    "AC": ("norte", "acre"), "AP": ("norte", "amapa"), "AM": ("norte", "amazonas"), "PA": ("norte", "para"),
    "RO": ("norte", "rondonia"), "RR": ("norte", "roraima"), "TO": ("norte", "tocantins"),
    "AL": ("nordeste", "alagoas"), "BA": ("nordeste", "bahia"), "CE": ("nordeste", "ceara"),
    "MA": ("nordeste", "maranhao"), "PB": ("nordeste", "paraiba"), "PE": ("nordeste", "pernambuco"),
    "PI": ("nordeste", "piaui"), "RN": ("nordeste", "rio-grande-do-norte"), "SE": ("nordeste", "sergipe"),
    "DF": ("centro-oeste", "distrito-federal"), "GO": ("centro-oeste", "goias"), "MT": ("centro-oeste", "mato-grosso"),
    "MS": ("centro-oeste", "mato-grosso-do-sul"), "ES": ("sudeste", "espirito-santo"),
    "MG": ("sudeste", "minas-gerais"), "RJ": ("sudeste", "rio-de-janeiro"), "SP": ("sudeste", "sao-paulo"),
    "PR": ("sul", "parana"), "RS": ("sul", "rio-grande-do-sul"), "SC": ("sul", "santa-catarina"),
}  # fmt: skip
# "MG 01-2026 Relatório Sintético de Materiais.xlsx"
_NOME = re.compile(r"(?:^|/)([A-Z]{2}) (\d{2})-(\d{4}) (Relat[oó]rio .+)\.xlsx$")


def url(uf: str, mes: str) -> str:
    a, m = (int(x) for x in mes.split("-"))
    regiao, estado = ESTADOS[uf]
    return URL.format(regiao=regiao, estado=estado, ano=a, mes_nome=MESES[m - 1], uf=uf.lower(), mes=m)


class FonteSicro:
    base = BASE
    por_uf = True  # um arquivo por UF: a API carrega a UF quando alguém pede preço nela

    def __init__(self, ufs: tuple[str, ...] | None = None, timeout: float = 300, hoje: date | None = None):
        self.ufs = tuple(ufs or ESTADOS)
        self.timeout, self.hoje = timeout, hoje

    # ------------------------------------------------------------------ download

    def ultimo_mes(self) -> str:
        """O DNIT publica por trimestre; pergunta-se só pelo arquivo de uma UF (o de MG, se estiver na lista)."""
        uf = "MG" if "MG" in self.ufs else self.ufs[0]
        hoje = self.hoje or date.today()
        a, m = hoje.year, hoje.month
        for _ in range(15):
            mes = f"{a}-{m:02d}"
            if m in (1, 4, 7, 10):
                st = _http.existe(url(uf, mes), SETE_Z)
                if st == 429:
                    raise BaseIndisponivel("O DNIT limitou os downloads (429): tente mais tarde.")
                if st:
                    return mes
            m -= 1
            if m == 0:
                a, m = a - 1, 12
        raise BaseIndisponivel("Nenhum SICRO publicado no portal do DNIT nos últimos 15 meses.")

    def baixar_uf(self, mes: str, uf: str) -> bytes:
        if uf not in ESTADOS:
            raise BaseIndisponivel(f"UF desconhecida: {uf}")
        try:
            arquivo = _http.baixar(url(uf, mes), SETE_Z, self.timeout)
        except _http.httpx.HTTPError as e:
            raise BaseIndisponivel(f"SICRO {uf} {mes}: o portal do DNIT não entregou o arquivo ({e}).") from None
        if arquivo is None:
            raise BaseIndisponivel(f"SICRO {uf} {mes}: arquivo não publicado no portal do DNIT.")
        return arquivo

    def baixar(self, mes: str) -> Iterator[bytes]:
        """As UFs configuradas (para importar de uma vez pela linha de comando); a API baixa UF a UF, quando pedem."""
        for uf in self.ufs:
            yield self.baixar_uf(mes, uf)

    # ------------------------------------------------------------------ leitura

    def ler(self, arquivo: bytes) -> LoteDeReferencia:
        import openpyxl
        import py7zr
        from py7zr.io import BytesIOFactory

        with py7zr.SevenZipFile(io.BytesIO(arquivo)) as z:
            tamanhos = {i.filename: i.uncompressed for i in z.list()}
            alvos = [n for n in tamanhos if _NOME.search(n) and "Sintético" in n]
            fabrica = BytesIOFactory(LIMITE_PLANILHA)
            z.extract(targets=alvos, factory=fabrica)
        planilhas = {}
        for n in alvos:
            b = fabrica.get(n)
            # a fábrica em memória corta calada o que passa do limite: planilha cortada é erro, não dado
            if b.size() != tamanhos[n]:
                raise ValueError(f"{n}: maior que {LIMITE_PLANILHA // 2**20} MB, não lido")
            b.seek(0)
            planilhas[n] = b.read()
        if not planilhas:
            raise ValueError("este arquivo não é um pacote do SICRO (sem os relatórios sintéticos em Excel)")
        uf, mes = None, None
        relatorios: dict[str, bytes] = {}
        for nome, dados in planilhas.items():
            u, m, a, rel = _NOME.search(nome).groups()
            uf, mes = u, f"{a}-{m}"
            relatorios[rel] = dados
        if uf not in ESTADOS:
            raise ValueError(f"UF desconhecida no pacote do SICRO: {uf}")
        lote = LoteDeReferencia(Referencia("sicro", mes), ufs=(uf,))

        def linhas(relatorio: str):
            dados = relatorios.get(relatorio)
            if dados is None:
                return []
            ws = openpyxl.load_workbook(io.BytesIO(dados), read_only=True, data_only=True).worksheets[0]
            return [r for r in ws.iter_rows(min_row=2, values_only=True) if r and r[0] and r[1]]

        def item(tipo: Tipo, cod, desc, un, grupo: str) -> str:
            codigo = str(cod).strip()
            if (tipo, codigo) not in lote.precos:
                lote.itens.append(Item("sicro", tipo, codigo, str(desc).strip(), str(un or "").strip(), grupo))
                lote.precos[(tipo, codigo)] = []
            return codigo

        def preco(tipo: Tipo, codigo: str, valor, desonerado: bool) -> None:
            ja = lote.precos[(tipo, codigo)]
            # o relatório de equipamentos traz alguns códigos em duas linhas iguais: vale a primeira
            if isinstance(valor, int | float) and valor > 0 and not any(p.desonerado == desonerado for p in ja):
                ja.append(Preco(uf, desonerado, round(valor * 100)))

        for cod, desc, un, valor, *_ in linhas("Relatório Sintético de Materiais"):
            c = item(Tipo.INSUMO, cod, desc, un, "MATERIAL")
            preco(Tipo.INSUMO, c, valor, False)
            preco(Tipo.INSUMO, c, valor, True)  # material não tem encargo social: o preço vale nos dois regimes
        for rel, deson in (("Relatório Sintético de Mão de Obra", False),
                           ("Relatório Sintético de Mão de Obra - com desoneração", True)):  # fmt: skip
            for cod, desc, un, valor, *_ in linhas(rel):
                preco(Tipo.INSUMO, item(Tipo.INSUMO, cod, desc, un, "MAO DE OBRA"), valor, deson)
        for rel, deson in (("Relatório Sintético de Equipamentos", False),
                           ("Relatório Sintético de Equipamentos - com desoneração", True)):  # fmt: skip
            for r in linhas(rel):
                # o custo produtivo por hora é o que entra na composição quando o equipamento trabalha
                preco(Tipo.INSUMO, item(Tipo.INSUMO, r[0], r[1], "h", "EQUIPAMENTO"), r[9], deson)
        for cod, desc, un, valor, *_ in linhas("Relatório Sintético de Composições de Custos"):
            preco(Tipo.COMPOSICAO, item(Tipo.COMPOSICAO, cod, desc, un, ""), valor, False)
        return lote
