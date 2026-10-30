"""Testes de pipeline/ingestao.py: CSVs escritos aqui, banco em tmp_path."""

import csv

import duckdb
import pytest

from pipeline import db, ingestao

# Uma linha em cada CSV, para os testes que só olham um dos três arquivos.
FILMES_PADRAO = [
    ("id", "title"),
    ("1", "Filme"),  # um filme qualquer: o arquivo só precisa existir
]
LINKS_PADRAO = [
    ("movieId", "imdbId", "tmdbId"),
    ("10", "0114709", "1"),  # um link qualquer: o arquivo só precisa existir
]
AVALIACOES_PADRAO = [
    ("userId", "movieId", "rating", "timestamp"),
    ("7", "10", "4.0", "0"),  # uma nota qualquer: o arquivo só precisa existir
]


def escrever_csv(caminho, linhas):
    with open(caminho, "w", encoding="utf-8", newline="") as arquivo:
        csv.writer(arquivo, lineterminator="\n").writerows(linhas)


def preparar(tmp_path, monkeypatch, filmes=FILMES_PADRAO):
    pasta = tmp_path / "raw"
    pasta.mkdir()
    banco = tmp_path / "teste.duckdb"
    monkeypatch.setattr(ingestao, "PASTA_RAW", pasta)
    monkeypatch.setattr(db, "ARQUIVO_BANCO", banco)
    escrever_csv(pasta / "movies_metadata.csv", filmes)
    escrever_csv(pasta / "links.csv", LINKS_PADRAO)
    escrever_csv(pasta / "ratings_small.csv", AVALIACOES_PADRAO)
    return pasta, banco


def consultar(banco, sql):
    with duckdb.connect(banco) as con:
        return con.execute(sql).fetchall()


def test_formatar_usa_ponto_no_milhar():
    assert ingestao.formatar(1234567) == "1.234.567"


def test_formatar_nao_poe_ponto_abaixo_de_mil():
    assert ingestao.formatar(999) == "999"


def test_csv_vira_tabela_com_as_mesmas_linhas(tmp_path, monkeypatch):
    _, banco = preparar(
        tmp_path,
        monkeypatch,
        filmes=[
            ("id", "title"),
            ("1", "Primeiro"),  # linha comum
            ("2", "São Paulo"),  # acento: o utf-8 tem de chegar intacto
        ],
    )

    ingestao.main()

    assert consultar(banco, "SELECT id, title FROM raw.filmes ORDER BY id") == [
        ("1", "Primeiro"),
        ("2", "São Paulo"),
    ]


def test_toda_coluna_entra_como_varchar(tmp_path, monkeypatch):
    _, banco = preparar(tmp_path, monkeypatch)

    ingestao.main()

    tipos = consultar(
        banco,
        "SELECT DISTINCT data_type FROM information_schema.columns "
        "WHERE table_schema = 'raw'",
    )
    assert tipos == [("VARCHAR",)]


def test_texto_na_continua_na(tmp_path, monkeypatch):
    _, banco = preparar(
        tmp_path,
        monkeypatch,
        filmes=[
            ("id", "title"),
            ("1", "NA"),  # o pandas transformaria em nulo por padrão
            ("2", "null"),  # idem
            ("3", "None"),  # idem
        ],
    )

    ingestao.main()

    assert consultar(banco, "SELECT title FROM raw.filmes ORDER BY id") == [
        ("NA",),
        ("null",),
        ("None",),
    ]


def test_campo_vazio_vira_nulo(tmp_path, monkeypatch):
    _, banco = preparar(
        tmp_path,
        monkeypatch,
        filmes=[
            ("id", "title"),
            ("1", ""),  # campo vazio: o único caso que vira nulo
        ],
    )

    ingestao.main()

    assert consultar(banco, "SELECT title FROM raw.filmes") == [(None,)]


def test_linha_repetida_nao_e_descartada(tmp_path, monkeypatch):
    _, banco = preparar(
        tmp_path,
        monkeypatch,
        filmes=[
            ("id", "title"),
            ("1", "Igual"),  # original
            ("1", "Igual"),  # cópia: deduplicar é decisão de refined
        ],
    )

    ingestao.main()

    assert consultar(banco, "SELECT count(*) FROM raw.filmes") == [(2,)]


def test_quebra_de_linha_entre_aspas_nao_parte_a_linha(tmp_path, monkeypatch):
    _, banco = preparar(
        tmp_path,
        monkeypatch,
        filmes=[
            ("id", "title"),
            ("1", "linha um\nlinha dois"),  # como as sinopses do CSV original
        ],
    )

    ingestao.main()

    assert consultar(banco, "SELECT title FROM raw.filmes") == [
        ("linha um\nlinha dois",)
    ]


def test_rodar_de_novo_nao_acumula_linhas(tmp_path, monkeypatch):
    _, banco = preparar(tmp_path, monkeypatch)

    ingestao.main()
    ingestao.main()

    assert consultar(banco, "SELECT count(*) FROM raw.filmes") == [(1,)]


def test_saida_mostra_uma_linha_por_tabela_e_o_total(tmp_path, monkeypatch, capsys):
    preparar(tmp_path, monkeypatch)

    ingestao.main()

    assert capsys.readouterr().out.splitlines() == [
        "✓ raw.filmes" + " " * 18 + "1 linhas",
        "✓ raw.links" + " " * 19 + "1 linhas",
        "✓ raw.avaliacoes" + " " * 14 + "1 linhas",
        "Total: 3 linhas",
    ]


def test_arquivo_faltando_encerra_sem_gravar_nada(tmp_path, monkeypatch, capsys):
    pasta, banco = preparar(tmp_path, monkeypatch)
    (pasta / "links.csv").unlink()

    with pytest.raises(SystemExit) as saida:
        ingestao.main()

    assert saida.value.code == 1
    assert not banco.exists()
    tela = capsys.readouterr().out
    assert "links.csv" in tela
    assert str(pasta) in tela
