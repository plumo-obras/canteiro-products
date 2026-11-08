# canteiro-products

Microsserviço do Plumo com os produtos e preços da construção: as bases oficiais de custos (SINAPI e SICRO hoje), importadas do
órgão que publica, com busca, item e composição analítica. Leia o `README.md` antes de codar.

## Regras da casa

**O repositório é PÚBLICO.** Nada de segredo, dado de cliente ou arquivo da base no repositório (o banco fica no
volume; o arquivo do órgão é baixado ou importado). Teste usa a planilha montada em `tests/falsos.py`.

**Só fonte oficial.** Cada base vem do arquivo publicado pelo órgão (Caixa, DNIT, CEHOP...). Não se copia de
agregador de terceiros (os termos deles proíbem, e o dado tem de ser rastreável até a fonte).

**Camadas: de fora só se importa para dentro.** `dominio` ← `aplicacao` ← `infraestrutura` ← `interfaces`. Base nova =
um leitor em `infraestrutura/bases/` que implementa `FonteDeBase`; o resto não muda. `tests/test_arquitetura.py` barra
import na direção errada.

**O número é o da base.** Dinheiro em centavos; coeficiente como a base publica; o parcial da composição é truncado no
centavo, como a planilha do SINAPI, para a soma fechar com o custo publicado. Leitor novo tem de provar isso no teste.

**Não martele o órgão.** O download é um por base por dia, no máximo; 429 é para esperar, não para repetir.

**Comentário explica por quê, não o quê.** Português do Brasil no código e nas mensagens.

## Comandos

```bash
uv sync --extra dev -p 3.11
uv run pytest -q
uv run ruff check src tests && uv run ruff format --check src tests
docker compose up -d --build                                   # http://localhost:8300/docs
docker compose exec produtos importar-base sinapi --arquivo /caminho/SINAPI.zip
```
