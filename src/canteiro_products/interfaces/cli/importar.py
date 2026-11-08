#!/usr/bin/env python3
"""Importa uma base oficial no catálogo.

Uso:
    importar-base sinapi                          # o mês mais novo publicado (baixa do órgão)
    importar-base sinapi --mes 2026-09            # um mês específico
    importar-base sinapi --arquivo SINAPI.zip     # o arquivo já baixado (o órgão limitou o download, sem internet...)
    importar-base sicro --uf SP --uf MG           # SICRO: as UFs pedidas, do trimestre mais novo (sem --uf: as 27)
O banco é o do serviço ($PRODUTOS_DADOS/produtos.sqlite).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from canteiro_products.dominio.erros import ErroDeProdutos
from canteiro_products.interfaces.http.app import montar_catalogo
from canteiro_products.interfaces.http.configuracao import Configuracao


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("base")
    ap.add_argument("--mes", help="AAAA-MM")
    ap.add_argument("--arquivo", type=Path)
    ap.add_argument("--uf", action="append", default=[], help="SICRO: uma UF (repita para várias)")
    a = ap.parse_args()
    catalogo = montar_catalogo(Configuracao.do_ambiente())
    if a.uf and not a.arquivo:
        try:
            for uf in a.uf:
                novo = catalogo.garantir_uf(a.base, uf.upper(), a.mes)
                print(f"{a.base} {uf.upper()}: {'importado' if novo else 'já estava'}", file=sys.stderr)
        except ErroDeProdutos as e:
            sys.exit(f"{a.base}: {e}")
        return
    try:
        r = catalogo.importar(a.base, arquivo=a.arquivo.read_bytes() if a.arquivo else None, mes=a.mes)
    except ErroDeProdutos as e:
        sys.exit(f"{a.base}: {e}")
    print(f"{r['base']} {r['mes']}: {r['insumos']} insumos, {r['composicoes']} composições, {r['precos']} preços",
          file=sys.stderr)  # fmt: skip


if __name__ == "__main__":
    main()
