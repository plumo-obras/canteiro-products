"""Repositório em SQLite: um arquivo no volume, sem servidor de banco para subir. A busca usa o índice de texto FTS5
sobre a descrição normalizada (sem acento, maiúscula) e o código; preço por UF e regime numa tabela à parte."""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

from canteiro_products.dominio.busca import Consulta, normalizar
from canteiro_products.dominio.modelos import Item, ItemDaComposicao, LoteDeReferencia, Preco, Referencia, Tipo

ESQUEMA = """
CREATE TABLE IF NOT EXISTS referencias (base TEXT, mes TEXT, importada_em REAL, PRIMARY KEY (base, mes));
CREATE TABLE IF NOT EXISTS itens (
    base TEXT, mes TEXT, tipo TEXT, codigo TEXT, descricao TEXT, unidade TEXT, grupo TEXT,
    PRIMARY KEY (base, mes, tipo, codigo));
CREATE VIRTUAL TABLE IF NOT EXISTS busca USING fts5(texto, base UNINDEXED, mes UNINDEXED, tipo UNINDEXED,
    codigo UNINDEXED, tokenize = 'unicode61');
CREATE TABLE IF NOT EXISTS precos (
    base TEXT, mes TEXT, tipo TEXT, codigo TEXT, uf TEXT, desonerado INTEGER, centavos INTEGER,
    PRIMARY KEY (base, mes, tipo, codigo, uf, desonerado));
CREATE INDEX IF NOT EXISTS precos_item ON precos (base, tipo, codigo, uf, desonerado);
CREATE TABLE IF NOT EXISTS analitico (
    base TEXT, mes TEXT, composicao TEXT, ordem INTEGER, tipo TEXT, codigo TEXT, descricao TEXT, unidade TEXT,
    coeficiente REAL, situacao TEXT, PRIMARY KEY (base, mes, composicao, ordem));
"""


class RepositorioSqlite:
    def __init__(self, arquivo: Path | str):
        self.arquivo = str(arquivo)
        if self.arquivo != ":memory:":
            Path(self.arquivo).parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._trava = threading.Lock()  # uma importação por vez; leitura não espera (WAL)
        self._con().executescript(ESQUEMA)

    def _con(self) -> sqlite3.Connection:
        # uma conexão por thread: o FastAPI atende rotas síncronas num pool de threads
        c = getattr(self._local, "con", None)
        if c is None:
            c = sqlite3.connect(self.arquivo, check_same_thread=False)
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA synchronous=NORMAL")
            self._local.con = c
        return c

    # ------------------------------------------------------------------ gravação

    def gravar_lote(self, lote: LoteDeReferencia) -> None:
        b, m = lote.referencia.base, lote.referencia.mes
        with self._trava:
            c = self._con()
            with c:  # uma transação: quem lê vê o mês antigo inteiro ou o novo inteiro
                if lote.ufs is None:
                    for tabela in ("itens", "precos", "analitico", "busca"):
                        c.execute(f"DELETE FROM {tabela} WHERE base = ? AND mes = ?", (b, m))  # noqa: S608
                else:
                    # base por UF: só os preços destas UFs saem; os itens se atualizam sem apagar os das outras
                    marcas = ",".join("?" * len(lote.ufs))
                    c.execute(f"DELETE FROM precos WHERE base = ? AND mes = ? AND uf IN ({marcas})", (b, m, *lote.ufs))  # noqa: S608
                    chaves = [(b, m, i.tipo.value, i.codigo) for i in lote.itens]
                    c.executemany("DELETE FROM itens WHERE base = ? AND mes = ? AND tipo = ? AND codigo = ?", chaves)
                    c.executemany("DELETE FROM busca WHERE base = ? AND mes = ? AND tipo = ? AND codigo = ?", chaves)
                    c.executemany("DELETE FROM analitico WHERE base = ? AND mes = ? AND composicao = ?",
                                  [(b, m, comp) for comp in lote.analiticos])  # fmt: skip
                c.executemany(
                    "INSERT INTO itens VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [(b, m, i.tipo.value, i.codigo, i.descricao, i.unidade, i.grupo) for i in lote.itens],
                )
                c.executemany(
                    "INSERT INTO busca (texto, base, mes, tipo, codigo) VALUES (?, ?, ?, ?, ?)",
                    [(f"{normalizar(i.descricao)} {i.codigo}", b, m, i.tipo.value, i.codigo) for i in lote.itens],
                )
                c.executemany(
                    "INSERT INTO precos VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [
                        (b, m, t.value, cod, p.uf, int(p.desonerado), p.centavos)
                        for (t, cod), ps in lote.precos.items()
                        for p in ps
                    ],  # fmt: skip
                )
                c.executemany(
                    "INSERT INTO analitico VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        (b, m, comp, k, it.tipo.value, it.codigo, it.descricao, it.unidade, it.coeficiente, it.situacao)
                        for comp, its in lote.analiticos.items()
                        for k, it in enumerate(its)
                    ],  # fmt: skip
                )
                c.execute("INSERT OR REPLACE INTO referencias VALUES (?, ?, ?)", (b, m, time.time()))

    # ------------------------------------------------------------------ leitura

    def referencias(self, base: str | None = None) -> list[Referencia]:
        sql, args = "SELECT base, mes FROM referencias", ()
        if base:
            sql, args = sql + " WHERE base = ?", (base,)
        return [Referencia(b, m) for b, m in self._con().execute(sql + " ORDER BY base, mes", args)]

    def buscar(self, consulta: Consulta, *, tipo, base, mes, uf, desonerado, limite):
        termos = " AND ".join(f'"{t}"*' for t in consulta.contem)
        if consulta.nao_contem:
            # excluir é pela palavra inteira: "-bomba" não pode tirar o "bombeavel"
            termos += " NOT (" + " OR ".join(f'"{t}"' for t in consulta.nao_contem) + ")"
        filtros, args = ["busca MATCH ?"], [termos]
        if tipo:
            filtros.append("busca.tipo = ?")
            args.append(tipo.value)
        if base:
            filtros.append("busca.base = ?")
            args.append(base)
        if mes:
            filtros.append("busca.mes = ?")
            args.append(mes)
        else:  # o mês mais novo de cada base
            filtros.append("busca.mes = (SELECT MAX(r.mes) FROM referencias r WHERE r.base = busca.base)")
        sql = f"""
            SELECT i.base, i.tipo, i.codigo, i.descricao, i.unidade, i.grupo, i.mes, p.centavos
            FROM busca
            JOIN itens i ON i.base = busca.base AND i.mes = busca.mes AND i.tipo = busca.tipo
                AND i.codigo = busca.codigo
            LEFT JOIN precos p ON p.base = i.base AND p.mes = i.mes AND p.tipo = i.tipo AND p.codigo = i.codigo
                AND p.uf = ? AND p.desonerado = ?
            WHERE {" AND ".join(filtros)}
            ORDER BY bm25(busca), length(i.descricao)
            LIMIT ?"""  # noqa: S608 — filtros são fixos; os valores vão como parâmetros
        linhas = self._con().execute(sql, [uf, int(desonerado), *args, limite]).fetchall()
        return [(Item(b, Tipo(t), cod, d, un, g), m, c) for b, t, cod, d, un, g, m, c in linhas]

    def obter(self, base, tipo, codigo, mes):
        r = (
            self._con()
            .execute(
                "SELECT descricao, unidade, grupo FROM itens WHERE base=? AND mes=? AND tipo=? AND codigo=?",
                (base, mes, tipo.value, codigo),
            )
            .fetchone()
        )
        return Item(base, tipo, codigo, *r) if r else None

    def precos(self, base, tipo, codigo, mes):
        return [
            Preco(uf, bool(d), c)
            for uf, d, c in self._con().execute(
                "SELECT uf, desonerado, centavos FROM precos WHERE base=? AND mes=? AND tipo=? AND codigo=?"
                " ORDER BY uf",
                (base, mes, tipo.value, codigo),
            )
        ]

    def historico(self, base, tipo, codigo, uf, desonerado):
        return list(
            self._con().execute(
                "SELECT mes, centavos FROM precos WHERE base=? AND tipo=? AND codigo=? AND uf=? AND desonerado=?"
                " ORDER BY mes",
                (base, tipo.value, codigo, uf, int(desonerado)),
            )
        )

    def analitico(self, base, codigo, mes):
        return [
            ItemDaComposicao(Tipo(t), cod, d, un, coef, sit)
            for t, cod, d, un, coef, sit in self._con().execute(
                "SELECT tipo, codigo, descricao, unidade, coeficiente, situacao FROM analitico"
                " WHERE base=? AND mes=? AND composicao=? ORDER BY ordem",
                (base, mes, codigo),
            )
        ]

    def ufs_carregadas(self, base, mes):
        return {
            uf for (uf,) in self._con().execute("SELECT DISTINCT uf FROM precos WHERE base=? AND mes=?", (base, mes))
        }
