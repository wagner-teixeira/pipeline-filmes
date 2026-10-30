"""Testes de pipeline/db.py, sempre com um DuckDB novo em tmp_path."""

import duckdb
import pandas as pd

from pipeline import db


def test_caminhos_do_projeto_sao_absolutos():
    assert db.ARQUIVO_BANCO.is_absolute()
    assert db.PASTA_RAW.is_absolute()


def test_conectar_cria_o_banco_que_nao_existia(tmp_path, monkeypatch):
    banco = tmp_path / "teste.duckdb"
    monkeypatch.setattr(db, "ARQUIVO_BANCO", banco)

    db.conectar().close()

    assert banco.exists()


def test_criar_schema_duas_vezes_nao_da_erro(tmp_path):
    with duckdb.connect(tmp_path / "teste.duckdb") as con:
        db.criar_schema(con, "novo")
        db.criar_schema(con, "novo")
        schemas = con.execute(
            "SELECT count(*) FROM information_schema.schemata WHERE schema_name = 'novo'"
        ).fetchone()[0]

    assert schemas == 1


def test_gravar_devolve_a_contagem_do_banco(tmp_path):
    df = pd.DataFrame(
        {
            "valor": [
                "a",  # primeira linha: a contagem tem de passar de 1
                "b",  # segunda linha: a contagem esperada é 2
            ]
        }
    )

    with duckdb.connect(tmp_path / "teste.duckdb") as con:
        db.criar_schema(con, "novo")
        linhas = db.gravar(con, df, "novo", "tabela")

    assert linhas == 2


def test_gravar_substitui_em_vez_de_acrescentar(tmp_path):
    primeira = pd.DataFrame(
        {
            "valor": [
                "antigo",  # tem de sumir quando a segunda carga entrar
            ]
        }
    )
    segunda = pd.DataFrame(
        {
            "valor": [
                "novo",  # único valor que pode sobrar
            ]
        }
    )

    with duckdb.connect(tmp_path / "teste.duckdb") as con:
        db.criar_schema(con, "novo")
        db.gravar(con, primeira, "novo", "tabela")
        db.gravar(con, segunda, "novo", "tabela")
        valores = con.execute("SELECT valor FROM novo.tabela").fetchall()

    assert valores == [("novo",)]
