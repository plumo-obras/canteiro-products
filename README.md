# canteiro-products

Microsserviço do Plumo com os **produtos e preços da construção**: as bases oficiais de custos, importadas do órgão que
publica, com busca por termos, o item com o preço em cada UF e o histórico mês a mês, e a **composição analítica** (os
insumos e serviços de cada composição, com coeficiente e custo, fechando no centavo com a base).

Hoje: **SINAPI** (Caixa + IBGE), nacional, 27 UF, com e sem desoneração. Próximas fontes entram como um leitor novo em
`infraestrutura/bases/` (SICRO/DNIT, ORSE/CEHOP-SE, GOINFRA/AGETOP...), sempre do arquivo oficial do órgão.

Quem usa: o [canteiro-cad](https://github.com/plumo-obras/canteiro-cad) (o insumo de cada material do projeto), a
[canteiro-api](https://github.com/plumo-obras/canteiro-api) e o agente (o que existe no mercado e quanto custa).

## Subir

```bash
docker compose up -d --build              # http://localhost:8300/docs
```

Ao subir sem nenhuma base, e depois uma vez por dia, o serviço busca o mês mais novo de cada base. A Caixa limita
downloads repetidos (HTTP 429): se a importação automática falhar, o serviço segue de pé e diz no log; importe o
arquivo baixado no navegador:

```bash
docker compose exec produtos importar-base sinapi --arquivo /caminho/SINAPI-2026-09-formato-xlsx.zip
```

| Variável | Padrão | |
|---|---|---|
| `PRODUTOS_API_KEYS` | vazio (sem autenticação) | chaves aceitas em `X-API-Key`, separadas por vírgula |
| `PRODUTOS_DADOS` | `/dados` na imagem | onde fica o banco (SQLite, ~110 MB por mês do SINAPI) |
| `PRODUTOS_ATUALIZAR` | 1 | busca o mês novo de cada base ao subir e uma vez por dia |
| `PRODUTOS_CORS` | `*` | origens liberadas |

## API

| | |
|---|---|
| `GET /v1/bases` | as bases (órgão, abrangência, fonte) e os meses importados |
| `GET /v1/itens?q=concreto usinado c30&uf=SP` | busca em insumos e composições: termos soltos, sem acento, em qualquer ordem; `-termo` exclui a palavra; `tipo=insumo\|composicao`, `base=`, `mes=AAAA-MM` (padrão: o mais novo), `desonerado=true`, `limite=` |
| `GET /v1/itens/{base}/{tipo}/{codigo}?uf=SP` | o item: preço na UF, preço em cada UF, histórico; na composição, os itens com coeficiente, preço e parcial |

Dinheiro em centavos. O parcial da composição é coeficiente × preço **truncado** no centavo, como a planilha do SINAPI:
a soma fecha com o custo publicado.

## Arquitetura

```
src/canteiro_products/
  dominio/          base, referência mensal, insumo, composição, preço; a busca por termos (Python puro)
  aplicacao/        casos de uso (bases, buscar, detalhar, importar) e as portas (repositório, fonte de cada base)
  infraestrutura/   sqlite.py (FTS5 para a busca) · bases/sinapi.py (download e leitura do arquivo da Caixa)
  interfaces/       http/ (FastAPI) · cli/importar.py (importar-base)
```

Cada camada só importa as de dentro; `tests/test_arquitetura.py` confere.

## Desenvolver

```bash
uv sync --extra dev -p 3.11
uv run pytest -q
uv run ruff check src tests && uv run ruff format --check src tests
PRODUTOS_DADOS=./dados uv run importar-base sinapi --arquivo SINAPI.zip
PRODUTOS_DADOS=./dados uv run uvicorn canteiro_products.interfaces.http.app:criar_app --factory --reload
```

Os dados das bases são públicos (órgãos federais e estaduais) e vêm sempre do arquivo oficial. Nada é copiado de
agregadores de terceiros.
