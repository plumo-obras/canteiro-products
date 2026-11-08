# syntax=docker/dockerfile:1
# Produtos e preços da construção (Plumo). Contexto de build = raiz deste repositório.
# Imagens travadas pelo digest do índice multi-arquitetura; o Dependabot sobe tag e digest juntos.
FROM ghcr.io/astral-sh/uv:0.13@sha256:96f40d3904aad8d0bd010539001d36c8e2188b981e1334471a90c4a1d93bb490 AS uv
FROM python:3.11-slim@sha256:07d4824036af339fa1b6ef769cc99d9c10a141769538b52b3b597c84f7a7b535
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_NO_CACHE=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy \
    PATH=/srv/.venv/bin:$PATH \
    PRODUTOS_DADOS=/dados
WORKDIR /srv
# Versões do uv.lock com --locked: lock desatualizado em relação ao pyproject quebra o build, em vez de instalar
# calado a versão velha. A imagem instala exatamente o que o CI testou. Dependências antes do código, para mudança
# no src não reinstalar as dependências.
COPY pyproject.toml uv.lock ./
RUN --mount=from=uv,source=/uv,target=/bin/uv \
    uv sync --locked --no-dev --no-install-project
COPY src src
RUN --mount=from=uv,source=/uv,target=/bin/uv \
    uv sync --locked --no-dev --no-editable \
 && useradd --create-home --uid 10001 produtos && mkdir -p /dados && chown produtos /dados
USER produtos
VOLUME ["/dados"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/v1/saude', timeout=4)"
CMD ["uvicorn", "canteiro_products.interfaces.http.app:criar_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
