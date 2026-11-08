# canteiro-products

Microsserviço do Plumo com os **produtos e preços da construção**: as bases oficiais de custos, importadas do órgão que
publica, com busca por termos, o item com o preço em cada UF e o histórico mês a mês, e a **composição analítica** (os
insumos e serviços de cada composição, com coeficiente e custo, fechando no centavo com a base).

| Base | Órgão | O que entra | Publicação |
|---|---|---|---|
| **SINAPI** | Caixa + IBGE | insumos, composições e o analítico; 27 UF; com e sem desoneração | mensal, um ZIP nacional |
| **SICRO** | DNIT | materiais, mão de obra e equipamentos (custo produtivo/h), composições (custo unitário); com e sem desoneração na mão de obra e no equipamento | trimestral, um .7z por UF |

A composição analítica do SICRO (produção da equipe, FIC, momento de transporte) ainda não entra: o custo dela não é
coeficiente × preço, e a regra da casa é fechar com o publicado. Próximas fontes entram como um leitor novo em
`infraestrutura/bases/`, sempre do arquivo oficial do órgão. O **ORSE** (CEHOP-SE) está pendente: o servidor de arquivos
dele não respondeu e o formato `.ORSE` é o do programa da CEHOP, sem documentação pública.

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
docker compose exec produtos importar-base sicro --uf SP --uf MG      # o trimestre mais novo destas UFs
docker compose exec produtos importar-base sicro --arquivo /caminho/mg-07-2026.7z
```

**SICRO sob demanda.** O DNIT publica um pacote de ~30 MB por UF a cada trimestre; em vez de baixar as 27, cada UF
entra quando alguém pede preço nela. O detalhe de um item numa UF nova espera o pacote chegar (~5 a 20 s, uma vez); a
busca responde na hora com o que tem e avisa em `carregando` (`["sicro/BA"]`) a UF que está chegando em segundo plano.
Duas consultas ao mesmo tempo não baixam a mesma UF duas vezes. A cada trimestre novo, só as UFs já usadas se atualizam.
O download retoma de onde parou quando o portal derruba a conexão no meio.

| Variável | Padrão | |
|---|---|---|
| `PRODUTOS_API_KEYS` | vazio (sem autenticação) | chaves aceitas em `X-API-Key`, separadas por vírgula |
| `PRODUTOS_DADOS` | `/dados` na imagem | onde fica o banco (SQLite, ~110 MB por mês do SINAPI) |
| `PRODUTOS_ATUALIZAR` | 1 | busca o mês novo de cada base ao subir e uma vez por dia |
| `PRODUTOS_SICRO_UFS` | nenhuma | UFs do SICRO para já carregar ao subir (`SP,MG`); as outras entram quando alguém pede |
| `PRODUTOS_CORS` | `*` | origens liberadas |

## API

| | |
|---|---|
| `GET /v1/bases` | as bases (órgão, abrangência, fonte) e os meses importados |
| `GET /v1/itens?q=concreto usinado c30&uf=SP` | busca (com `carregando`: as bases por UF que ainda estão chegando) em insumos e composições: termos soltos, sem acento, em qualquer ordem; `-termo` exclui a palavra; `tipo=insumo\|composicao`, `base=`, `mes=AAAA-MM` (padrão: o mais novo), `desonerado=true`, `limite=` |
| `GET /v1/itens/{base}/{tipo}/{codigo}?uf=SP` | o item: preço na UF, preço em cada UF, histórico; na composição, os itens com coeficiente, preço e parcial |

Dinheiro em centavos. O parcial da composição é coeficiente × preço **truncado** no centavo, como a planilha do SINAPI:
a soma fecha com o custo publicado.

## Arquitetura

```
src/canteiro_products/
  dominio/          base, referência mensal, insumo, composição, preço; a busca por termos (Python puro)
  aplicacao/        casos de uso (bases, buscar, detalhar, importar) e as portas (repositório, fonte de cada base)
  infraestrutura/   sqlite.py (FTS5 para a busca) · bases/sinapi.py (Caixa) · bases/sicro.py (DNIT) · bases/_http.py
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
