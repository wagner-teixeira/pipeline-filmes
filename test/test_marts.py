"""Testes de pipeline/marts.py: .sql escritos aqui, banco em tmp_path."""

import duckdb
import pytest

from pipeline import db, marts

TABELAS_REFINED = ("filmes", "links", "avaliacoes")


def preparar(tmp_path, monkeypatch, tabelas=TABELAS_REFINED):
    banco = tmp_path / "teste.duckdb"
    pasta = tmp_path / "marts"
    pasta.mkdir()
    with duckdb.connect(banco) as con:
        con.execute("CREATE SCHEMA refined")
        for tabela in tabelas:
            con.execute(f"CREATE TABLE refined.{tabela} (x INTEGER)")
    monkeypatch.setattr(db, "ARQUIVO_BANCO", banco)
    monkeypatch.setattr(marts, "PASTA_MARTS", pasta)
    return banco, pasta


def escrever(pasta, nome, sql):
    (pasta / nome).write_text(sql, encoding="utf-8")


def consultar(banco, sql):
    with duckdb.connect(banco) as con:
        return con.execute(sql).fetchall()


def tabelas_marts(banco):
    return consultar(
        banco,
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'marts' ORDER BY table_name",
    )


def schema_marts_existe(banco):
    return consultar(
        banco,
        "SELECT count(*) FROM information_schema.schemata "
        "WHERE schema_name = 'marts'",
    ) == [(1,)]


def test_arquivo_vira_tabela_sem_o_prefixo(tmp_path, monkeypatch):
    banco, pasta = preparar(tmp_path, monkeypatch)
    escrever(pasta, "07_exemplo.sql", "SELECT 1 AS x")

    marts.main()

    assert consultar(banco, "SELECT x FROM marts.exemplo") == [(1,)]


def test_arquivo_sem_prefixo_para_antes_de_executar(tmp_path, monkeypatch, capsys):
    banco, pasta = preparar(tmp_path, monkeypatch)
    escrever(pasta, "01_bom.sql", "SELECT 1 AS x")
    escrever(pasta, "teste.sql", "SELECT 1 AS x")

    with pytest.raises(SystemExit) as saida:
        marts.main()

    assert saida.value.code == 1
    # Nem o schema foi criado: nada da transação chegou a rodar.
    assert not schema_marts_existe(banco)
    assert "  teste.sql\n" in capsys.readouterr().out


def test_prefixo_com_tres_digitos_nao_vale(tmp_path, monkeypatch, capsys):
    banco, pasta = preparar(tmp_path, monkeypatch)
    escrever(pasta, "123_x.sql", "SELECT 1 AS x")

    with pytest.raises(SystemExit):
        marts.main()

    assert not schema_marts_existe(banco)
    assert "  123_x.sql\n" in capsys.readouterr().out


def test_dois_arquivos_com_o_mesmo_nome_de_tabela_param_antes_de_executar(
    tmp_path, monkeypatch, capsys
):
    banco, pasta = preparar(tmp_path, monkeypatch)
    escrever(pasta, "01_igual.sql", "SELECT 1 AS x")
    escrever(pasta, "02_igual.sql", "SELECT 2 AS x")

    with pytest.raises(SystemExit) as saida:
        marts.main()

    assert saida.value.code == 1
    assert not schema_marts_existe(banco)
    tela = capsys.readouterr().out
    assert "01_igual.sql" in tela
    assert "02_igual.sql" in tela
    # O CREATE TABLE do segundo também daria SystemExit: só a mensagem prova
    # que a parada veio da checagem, antes de executar.
    assert "Falhou" not in tela


def test_nomes_que_diferem_so_em_maiuscula_colidem_antes_de_executar(
    tmp_path, monkeypatch, capsys
):
    banco, pasta = preparar(tmp_path, monkeypatch)
    escrever(pasta, "01_Lucro.sql", "SELECT 1 AS x")
    escrever(pasta, "02_lucro.sql", "SELECT 2 AS x")

    with pytest.raises(SystemExit):
        marts.main()

    assert not schema_marts_existe(banco)
    assert "Falhou" not in capsys.readouterr().out


def test_mart_vazio_encerra_e_deixa_marts_como_estava(tmp_path, monkeypatch, capsys):
    banco, pasta = preparar(tmp_path, monkeypatch)
    escrever(pasta, "01_estavel.sql", "SELECT 1 AS x")
    marts.main()
    capsys.readouterr()

    escrever(pasta, "01_estavel.sql", "SELECT 2 AS x")
    escrever(pasta, "02_vazio.sql", "SELECT 1 AS x WHERE false")
    with pytest.raises(SystemExit) as saida:
        marts.main()

    assert saida.value.code == 1
    assert tabelas_marts(banco) == [("estavel",)]
    assert consultar(banco, "SELECT x FROM marts.estavel") == [(1,)]
    tela = capsys.readouterr().out
    assert "marts.vazio" in tela
    assert "✓" not in tela


def test_erro_de_sql_mostra_o_arquivo_e_deixa_marts_como_estava(
    tmp_path, monkeypatch, capsys
):
    banco, pasta = preparar(tmp_path, monkeypatch)
    escrever(pasta, "01_estavel.sql", "SELECT 1 AS x")
    marts.main()
    capsys.readouterr()

    escrever(pasta, "02_quebrado.sql", "SELEC 1")
    with pytest.raises(SystemExit) as saida:
        marts.main()

    assert saida.value.code == 1
    assert tabelas_marts(banco) == [("estavel",)]
    tela = capsys.readouterr().out
    assert "02_quebrado.sql" in tela
    assert "SELEC" in tela
    assert "✓" not in tela


def test_sql_que_falha_nao_deixa_executar_os_seguintes(tmp_path, monkeypatch, capsys):
    _, pasta = preparar(tmp_path, monkeypatch)
    escrever(pasta, "01_primeiro.sql", "SELEC 1")
    escrever(pasta, "02_segundo.sql", "SELEC 2")

    with pytest.raises(SystemExit):
        marts.main()

    tela = capsys.readouterr().out
    assert "01_primeiro.sql" in tela
    assert "02_segundo.sql" not in tela


def test_arquivo_que_nao_e_utf8_para_com_o_nome_do_arquivo(
    tmp_path, monkeypatch, capsys
):
    _, pasta = preparar(tmp_path, monkeypatch)
    # \xe9 é "é" em latin-1 e não forma um caractere válido em utf-8.
    (pasta / "01_latin.sql").write_bytes(b"SELECT '\xe9' AS x")

    with pytest.raises(SystemExit) as saida:
        marts.main()

    assert saida.value.code == 1
    assert "01_latin.sql" in capsys.readouterr().out


def test_arquivo_apagado_faz_o_mart_sumir_na_execucao_seguinte(tmp_path, monkeypatch):
    banco, pasta = preparar(tmp_path, monkeypatch)
    escrever(pasta, "01_fica.sql", "SELECT 1 AS x")
    escrever(pasta, "02_some.sql", "SELECT 1 AS x")
    marts.main()
    assert tabelas_marts(banco) == [("fica",), ("some",)]

    (pasta / "02_some.sql").unlink()
    marts.main()

    assert tabelas_marts(banco) == [("fica",)]


def test_tabela_faltando_em_refined_encerra_antes_de_tudo(
    tmp_path, monkeypatch, capsys
):
    banco, pasta = preparar(tmp_path, monkeypatch, tabelas=("filmes",))
    # Sem prefixo: a checagem de refined tem de vir antes desta.
    escrever(pasta, "teste.sql", "SELECT 1 AS x")

    with pytest.raises(SystemExit) as saida:
        marts.main()

    assert saida.value.code == 1
    assert not schema_marts_existe(banco)
    tela = capsys.readouterr().out
    assert "  links\n" in tela
    assert "  avaliacoes\n" in tela
    assert "  filmes\n" not in tela
    assert "uv run python -m pipeline.transformacao" in tela
    assert "teste.sql" not in tela


def test_pasta_sem_arquivos_encerra(tmp_path, monkeypatch, capsys):
    preparar(tmp_path, monkeypatch)

    with pytest.raises(SystemExit) as saida:
        marts.main()

    assert saida.value.code == 1
    assert "Nenhum arquivo" in capsys.readouterr().out


def test_tira_ponto_e_virgula_e_espacos_do_final(tmp_path, monkeypatch):
    banco, pasta = preparar(tmp_path, monkeypatch)
    escrever(pasta, "01_final.sql", "SELECT 1 AS x ;  \n\n")

    marts.main()

    assert consultar(banco, "SELECT x FROM marts.final") == [(1,)]


def test_comentario_com_acento_e_with_no_comeco_funcionam(tmp_path, monkeypatch):
    banco, pasta = preparar(tmp_path, monkeypatch)
    escrever(
        pasta,
        "01_rotulo.sql",
        "-- Comentário com acento\nWITH base AS (SELECT '1 · até' AS r)\n"
        "SELECT r FROM base",
    )

    marts.main()

    assert consultar(banco, "SELECT r FROM marts.rotulo") == [("1 · até",)]


def test_arquivos_rodam_em_ordem_alfabetica(tmp_path, monkeypatch):
    banco, pasta = preparar(tmp_path, monkeypatch)
    # O 02 lê a tabela do 01: só funciona se o 01 vier antes.
    escrever(pasta, "02_depois.sql", "SELECT x + 1 AS x FROM marts.antes")
    escrever(pasta, "01_antes.sql", "SELECT 1 AS x")

    marts.main()

    assert consultar(banco, "SELECT x FROM marts.depois") == [(2,)]


def test_refined_continua_de_pe(tmp_path, monkeypatch):
    banco, pasta = preparar(tmp_path, monkeypatch)
    escrever(pasta, "01_exemplo.sql", "SELECT 1 AS x")

    marts.main()

    assert consultar(banco, "SELECT count(*) FROM refined.filmes") == [(0,)]


def test_saida_tem_milhar_com_ponto_e_linha_final(tmp_path, monkeypatch, capsys):
    _, pasta = preparar(tmp_path, monkeypatch)
    escrever(pasta, "01_grande.sql", "SELECT * FROM range(1234)")
    escrever(pasta, "02_top_lucro.sql", "SELECT * FROM range(10)")

    marts.main()

    assert capsys.readouterr().out.splitlines() == [
        "✓ marts.grande" + " " * 16 + "1.234 linhas",
        "✓ marts.top_lucro" + " " * 16 + "10 linhas",
        "2 marts, 1.244 linhas.",
    ]


def test_nome_comprido_ainda_tem_espaco_antes_do_numero(tmp_path, monkeypatch, capsys):
    _, pasta = preparar(tmp_path, monkeypatch)
    escrever(pasta, "01_nome_comprido_que_passa_da_coluna_do_numero.sql", "SELECT 1")

    marts.main()

    assert (
        "✓ marts.nome_comprido_que_passa_da_coluna_do_numero 1 linhas"
        in capsys.readouterr().out
    )


def test_rodar_duas_vezes_imprime_a_mesma_coisa(tmp_path, monkeypatch, capsys):
    _, pasta = preparar(tmp_path, monkeypatch)
    escrever(pasta, "01_exemplo.sql", "SELECT 1 AS x")

    marts.main()
    primeira = capsys.readouterr().out
    marts.main()
    segunda = capsys.readouterr().out

    assert primeira == segunda
