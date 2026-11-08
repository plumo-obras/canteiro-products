"""Produtos e preços da construção para o Plumo: as bases oficiais de custos (SINAPI hoje; SICRO, ORSE e outras como
novas fontes), importadas do órgão que publica e consultadas por busca, por código e pela composição analítica.

Camadas (de dentro para fora; cada uma só conhece as de dentro):
    dominio/          o que é uma base, uma referência mensal, um insumo, uma composição; a busca por termos
    aplicacao/        casos de uso (buscar, detalhar, importar) e as portas (repositório, fonte de cada base)
    infraestrutura/   SQLite com índice de texto; o leitor e o download de cada base (bases/)
    interfaces/       a API HTTP (FastAPI) e a linha de comando
"""

VERSAO_SERVICO = "0.1.0"
