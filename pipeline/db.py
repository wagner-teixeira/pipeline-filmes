"""Acesso ao banco DuckDB do projeto.

Spec (specs/ingestao.md), e por que cada regra existe:

PASTA_RAW      Path da pasta raw/ na raiz do projeto.
ARQUIVO_BANCO  Path do filmes.duckdb na raiz.
    Os dois caminhos ficam aqui para existirem num só lugar. São absolutos,
    derivados deste arquivo, para não dependerem de onde o comando é chamado.

conectar()
    Abre o filmes.duckdb, criando se faltar. Quem não pode criar um banco
    vazio (o ui.py, regra U3) não deve usar esta função.

criar_schema(con, nome)
    CREATE SCHEMA IF NOT EXISTS: reexecutar não pode dar erro.

gravar(con, df, schema, tabela)
    CREATE OR REPLACE a partir do DataFrame, nunca acrescenta: rodar dez
    vezes = rodar uma. Devolve a contagem lida do banco, e não do DataFrame,
    para que o número mostrado seja o que de fato foi gravado.
"""

from pathlib import Path

import duckdb

RAIZ = Path(__file__).resolve().parent.parent
PASTA_RAW = RAIZ / "raw"
ARQUIVO_BANCO = RAIZ / "filmes.duckdb"


def conectar():
    return duckdb.connect(ARQUIVO_BANCO)


def criar_schema(con, nome):
    con.execute(f'CREATE SCHEMA IF NOT EXISTS "{nome}"')


def gravar(con, df, schema, tabela):
    # "df" no FROM é o parâmetro acima: o DuckDB resolve o nome pelas
    # variáveis Python em escopo (replacement scan).
    con.execute(f'CREATE OR REPLACE TABLE "{schema}"."{tabela}" AS SELECT * FROM df')
    return con.execute(f'SELECT count(*) FROM "{schema}"."{tabela}"').fetchone()[0]
