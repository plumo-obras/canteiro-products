"""O pouco de HTTP que as fontes oficiais pedem: perguntar se um arquivo existe sem baixá-lo (os portais do governo
recusam HEAD, mas aceitam GET com Range) e baixar o arquivo inteiro."""

from __future__ import annotations

import time

import httpx

# portais do governo (Caixa, gov.br) recusam ou entram em loop de redirecionamento com cliente que não parece navegador
CABECALHOS = {"User-Agent": "Mozilla/5.0 (canteiro-products; bases oficiais de custos)"}


def existe(url: str, assinatura: bytes, timeout: float = 30) -> int | None:
    """O status HTTP se o arquivo existe e começa pela assinatura (ZIP, 7z...); None se não existe. 429 vira 429."""
    with httpx.Client(timeout=timeout, follow_redirects=True, headers={**CABECALHOS, "Range": "bytes=0-15"}) as c:
        r = c.get(url)
    if r.status_code == 429:
        return 429
    return r.status_code if r.status_code in (200, 206) and r.content.startswith(assinatura) else None


def baixar(url: str, assinatura: bytes, timeout: float = 300, tentativas: int = 5, pausa: float = 5) -> bytes | None:
    """O arquivo inteiro, ou None se não existe. Os portais do governo derrubam a conexão no meio de arquivos grandes
    (o pacote do SICRO tem ~30 MB): retoma de onde parou com Range, com pausa entre as tentativas."""
    dados = bytearray()
    total = None
    for tentativa in range(tentativas):
        cab = {**CABECALHOS, **({"Range": f"bytes={len(dados)}-"} if dados else {})}
        try:
            with httpx.Client(timeout=timeout, follow_redirects=True, headers=cab) as c, c.stream("GET", url) as r:
                if r.status_code == 404 or (r.status_code == 200 and dados):
                    if r.status_code == 404:
                        return None
                    dados.clear()  # o servidor ignorou o Range: recomeça do zero
                if r.status_code not in (200, 206):
                    return None
                if total is None:
                    total = int(r.headers.get("content-length", 0)) or None
                for pedaco in r.iter_bytes():
                    dados.extend(pedaco)
            if not dados.startswith(assinatura):
                return None
            if total is None or len(dados) >= total:
                return bytes(dados)
        except httpx.HTTPError:
            pass
        time.sleep(pausa * (tentativa + 1))
    raise httpx.TransportError(f"download interrompido {tentativas} vezes ({len(dados)} de {total or '?'} bytes)")
