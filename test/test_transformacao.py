"""Testes de pipeline/transformacao.py: tabelas raw inventadas, banco em tmp_path."""

from datetime import date, datetime
from decimal import Decimal

import duckdb
import pytest

from pipeline import db, transformacao

COLUNAS_LINKS = ("movieId", "imdbId", "tmdbId")
COLUNAS_AVALIACOES = ("userId", "movieId", "rating", "timestamp")


def filme(**campos):
    """Linha válida de raw.filmes; cada teste muda só o campo que importa."""
    return {
        "id": "1",
        "imdb_id": "tt1",
        "title": "Filme",
        "original_title": "Filme",
        "original_language": "en",
        "release_date": "2000-01-31",
        "status": "Released",
        "budget": "100",
        "revenue": "200",
        "runtime": "90.0",
        "vote_average": "7.5",
        "vote_count": "10",
        "popularity": "1.5",
        "adult": "False",
    } | campos


def criar_tabela(con, tabela, colunas, linhas):
    definicao = ", ".join(f'"{coluna}" VARCHAR' for coluna in colunas)
    con.execute(f"CREATE TABLE raw.{tabela} ({definicao})")
    marcadores = ", ".join("?" for _ in colunas)
    for linha in linhas:
        con.execute(f"INSERT INTO raw.{tabela} VALUES ({marcadores})", list(linha))


def preparar(tmp_path, monkeypatch, filmes=(), links=(), avaliacoes=()):
    banco = tmp_path / "teste.duckdb"
    monkeypatch.setattr(db, "ARQUIVO_BANCO", banco)
    with duckdb.connect(banco) as con:
        con.execute("CREATE SCHEMA raw")
        criar_tabela(
            con,
            "filmes",
            tuple(filme()),
            [tuple(linha.values()) for linha in filmes],
        )
        criar_tabela(con, "links", COLUNAS_LINKS, links)
        criar_tabela(con, "avaliacoes", COLUNAS_AVALIACOES, avaliacoes)
    return banco


def consultar(banco, sql):
    with duckdb.connect(banco) as con:
        return con.execute(sql).fetchall()


def tabelas_refined(banco):
    return consultar(
        banco,
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'refined'",
    )


def test_linha_com_id_que_nao_e_so_digitos_sai(tmp_path, monkeypatch):
    banco = preparar(
        tmp_path,
        monkeypatch,
        filmes=[
            filme(id="1"),  # id válido: fica
            # Metade deslocada de linha partida: sai antes de qualquer CAST,
            # senão o budget com caminho de imagem pararia tudo.
            filme(id="1997-08-20", budget="/imagem.jpg"),
        ],
    )

    transformacao.main()

    assert consultar(banco, "SELECT filme_id FROM refined.filmes") == [(1,)]


def test_copia_exata_sai(tmp_path, monkeypatch):
    banco = preparar(
        tmp_path,
        monkeypatch,
        filmes=[
            filme(id="1"),  # original
            filme(id="1"),  # cópia inteira do anterior: sai
            filme(id="2"),  # outro filme: prova que só a cópia saiu
        ],
    )

    transformacao.main()

    assert consultar(banco, "SELECT filme_id FROM refined.filmes ORDER BY 1") == [
        (1,),
        (2,),
    ]


def test_copia_exata_em_links_sai(tmp_path, monkeypatch):
    banco = preparar(
        tmp_path,
        monkeypatch,
        links=[
            ("10", "0000001", "1"),  # original
            ("10", "0000001", "1"),  # cópia inteira do anterior: sai
        ],
    )

    transformacao.main()

    assert consultar(banco, "SELECT filme_ml_id FROM refined.links") == [(10,)]


def test_copia_exata_em_avaliacoes_sai(tmp_path, monkeypatch):
    banco = preparar(
        tmp_path,
        monkeypatch,
        avaliacoes=[
            ("7", "10", "4.0", "0"),  # original
            ("7", "10", "4.0", "0"),  # cópia inteira do anterior: sai
        ],
    )

    transformacao.main()

    assert consultar(banco, "SELECT filme_ml_id FROM refined.avaliacoes") == [(10,)]


def test_mesmo_id_com_popularidade_diferente_fica_a_linha_de_mais_votos(
    tmp_path, monkeypatch
):
    banco = preparar(
        tmp_path,
        monkeypatch,
        filmes=[
            # Menos votos e mais popularidade: perde, votos vêm primeiro.
            filme(id="1", vote_count="5", popularity="9.0"),
            filme(id="1", vote_count="8", popularity="1.0"),  # mais votos: fica
        ],
    )

    transformacao.main()

    assert consultar(banco, "SELECT votos_tmdb, popularidade FROM refined.filmes") == [
        (8, 1.0)
    ]


def test_empate_de_votos_fica_a_linha_de_maior_popularidade(tmp_path, monkeypatch):
    banco = preparar(
        tmp_path,
        monkeypatch,
        filmes=[
            filme(id="1", vote_count="5", popularity="1.0"),  # empata e perde
            filme(id="1", vote_count="5", popularity="2.0"),  # empata e ganha
        ],
    )

    transformacao.main()

    assert consultar(banco, "SELECT popularidade FROM refined.filmes") == [(2.0,)]


def test_mesmo_id_com_titulo_diferente_encerra(tmp_path, monkeypatch, capsys):
    banco = preparar(
        tmp_path,
        monkeypatch,
        filmes=[
            filme(id="1", title="Um título"),  # primeira versão do cadastro
            filme(id="1", title="Outro título"),  # título não é medida: conflito
        ],
    )

    with pytest.raises(SystemExit) as saida:
        transformacao.main()

    assert saida.value.code == 1
    assert tabelas_refined(banco) == []
    assert "Chave repetida com conteúdo diferente em raw.filmes" in (
        capsys.readouterr().out
    )


def test_orcamento_zero_vira_nulo(tmp_path, monkeypatch):
    banco = preparar(
        tmp_path,
        monkeypatch,
        filmes=[
            filme(budget="0"),  # 0 no TMDB quer dizer "não informado"
        ],
    )

    transformacao.main()

    assert consultar(banco, "SELECT orcamento FROM refined.filmes") == [(None,)]


def test_receita_zero_vira_nulo(tmp_path, monkeypatch):
    banco = preparar(
        tmp_path,
        monkeypatch,
        filmes=[
            filme(revenue="0"),  # mesma regra do orçamento
        ],
    )

    transformacao.main()

    assert consultar(banco, "SELECT receita FROM refined.filmes") == [(None,)]


def test_dinheiro_diferente_de_zero_vira_decimal_exato(tmp_path, monkeypatch):
    banco = preparar(
        tmp_path,
        monkeypatch,
        filmes=[
            filme(budget="1234567.89"),  # em float, os centavos não seriam exatos
        ],
    )

    transformacao.main()

    assert consultar(banco, "SELECT orcamento FROM refined.filmes") == [
        (Decimal("1234567.89"),)
    ]


def test_imdb_id_mantem_o_zero_a_esquerda(tmp_path, monkeypatch):
    banco = preparar(
        tmp_path,
        monkeypatch,
        links=[
            ("10", "0114709", "1"),  # como número, perderia o zero
        ],
    )

    transformacao.main()

    assert consultar(banco, "SELECT imdb_id FROM refined.links") == [("0114709",)]


def test_duracao_com_ponto_zero_vira_inteiro(tmp_path, monkeypatch):
    banco = preparar(
        tmp_path,
        monkeypatch,
        filmes=[
            filme(runtime="81.0"),  # o CSV traz a duração com casa decimal
        ],
    )

    transformacao.main()

    assert consultar(banco, "SELECT duracao_min FROM refined.filmes") == [(81,)]


def test_adulto_vira_booleano(tmp_path, monkeypatch):
    banco = preparar(
        tmp_path,
        monkeypatch,
        filmes=[
            filme(id="1", adult="True"),  # único texto que vira verdadeiro
            filme(id="2", adult="False"),  # o outro valor do CSV
        ],
    )

    transformacao.main()

    assert consultar(banco, "SELECT adulto FROM refined.filmes ORDER BY filme_id") == [
        (True,),
        (False,),
    ]


def test_data_valida_vira_date(tmp_path, monkeypatch):
    banco = preparar(
        tmp_path,
        monkeypatch,
        filmes=[
            filme(release_date="2000-01-31"),  # formato declarado na spec
        ],
    )

    transformacao.main()

    assert consultar(banco, "SELECT data_lancamento FROM refined.filmes") == [
        (date(2000, 1, 31),)
    ]


def test_data_invalida_encerra_sem_criar_tabela(tmp_path, monkeypatch, capsys):
    banco = preparar(
        tmp_path,
        monkeypatch,
        filmes=[
            filme(release_date="31/01/2000"),  # fora do formato '%Y-%m-%d'
        ],
    )

    with pytest.raises(SystemExit) as saida:
        transformacao.main()

    assert saida.value.code == 1
    assert tabelas_refined(banco) == []
    assert "refined.filmes, coluna data_lancamento" in capsys.readouterr().out


def test_numero_invalido_encerra_mostrando_a_coluna(tmp_path, monkeypatch, capsys):
    preparar(
        tmp_path,
        monkeypatch,
        filmes=[
            filme(vote_count="muitos"),  # não converte para INTEGER
        ],
    )

    with pytest.raises(SystemExit) as saida:
        transformacao.main()

    assert saida.value.code == 1
    assert "refined.filmes, coluna votos_tmdb" in capsys.readouterr().out


def test_tabela_faltando_em_raw_encerra(tmp_path, monkeypatch, capsys):
    banco = preparar(tmp_path, monkeypatch)
    with duckdb.connect(banco) as con:
        con.execute("DROP TABLE raw.links")

    with pytest.raises(SystemExit) as saida:
        transformacao.main()

    assert saida.value.code == 1
    tela = capsys.readouterr().out
    assert "  links\n" in tela
    assert "  filmes\n" not in tela
    assert "uv run python -m pipeline.ingestao" in tela


def test_data_hora_vem_dos_segundos_desde_1970(tmp_path, monkeypatch):
    banco = preparar(
        tmp_path,
        monkeypatch,
        avaliacoes=[
            ("7", "10", "4.5", "86400"),  # um dia depois de 1970-01-01, em UTC
        ],
    )

    transformacao.main()

    assert consultar(banco, "SELECT nota, data_hora FROM refined.avaliacoes") == [
        (Decimal("4.5"), datetime(1970, 1, 2))
    ]


def test_avaliacao_de_filme_fora_de_refined_fica(tmp_path, monkeypatch):
    banco = preparar(
        tmp_path,
        monkeypatch,
        avaliacoes=[
            ("7", "999", "3.0", "0"),  # filme 999 não existe em links nem filmes
        ],
    )

    transformacao.main()

    assert consultar(banco, "SELECT filme_ml_id FROM refined.avaliacoes") == [(999,)]


def test_filme_id_repetido_em_links_nao_e_duplicata(tmp_path, monkeypatch):
    banco = preparar(
        tmp_path,
        monkeypatch,
        links=[
            ("10", "0000001", "1"),  # primeiro cadastro do MovieLens do filme 1
            ("20", "0000002", "1"),  # segundo cadastro do mesmo filme 1
        ],
    )

    transformacao.main()

    assert consultar(banco, "SELECT filme_ml_id FROM refined.links ORDER BY 1") == [
        (10,),
        (20,),
    ]


def test_mesma_chave_com_conteudo_diferente_em_links_encerra(tmp_path, monkeypatch):
    preparar(
        tmp_path,
        monkeypatch,
        links=[
            ("10", "0000001", "1"),  # filme_ml_id 10 aponta para o filme 1
            ("10", "0000001", "2"),  # o mesmo 10 aponta para outro filme: conflito
        ],
    )

    with pytest.raises(SystemExit) as saida:
        transformacao.main()

    assert saida.value.code == 1


def test_mesma_chave_com_nota_diferente_em_avaliacoes_encerra(tmp_path, monkeypatch):
    preparar(
        tmp_path,
        monkeypatch,
        avaliacoes=[
            ("7", "10", "4.0", "0"),  # usuário 7 deu 4,0 ao filme 10
            ("7", "10", "2.0", "0"),  # o mesmo par com outra nota: conflito
        ],
    )

    with pytest.raises(SystemExit) as saida:
        transformacao.main()

    assert saida.value.code == 1


def test_nulo_nao_apaga_a_linha_nem_e_preenchido(tmp_path, monkeypatch):
    banco = preparar(
        tmp_path,
        monkeypatch,
        filmes=[
            filme(title=None, release_date=None),  # sem título e sem data: fica
        ],
    )

    transformacao.main()

    assert consultar(banco, "SELECT titulo, data_lancamento FROM refined.filmes") == [
        (None, None)
    ]


def test_rodar_de_novo_da_o_mesmo_resultado(tmp_path, monkeypatch):
    banco = preparar(
        tmp_path,
        monkeypatch,
        filmes=[
            filme(),  # uma linha basta: duas execuções não podem virar duas
        ],
    )

    transformacao.main()
    transformacao.main()

    assert consultar(banco, "SELECT count(*) FROM refined.filmes") == [(1,)]


def test_raw_nao_muda(tmp_path, monkeypatch):
    banco = preparar(
        tmp_path,
        monkeypatch,
        filmes=[
            filme(id="1"),  # original
            filme(id="1"),  # cópia: sai de refined, mas continua em raw
        ],
    )

    transformacao.main()

    assert consultar(banco, "SELECT count(*) FROM raw.filmes") == [(2,)]


def test_saida_mostra_o_que_saiu_os_nulos_e_o_total(tmp_path, monkeypatch, capsys):
    preparar(
        tmp_path,
        monkeypatch,
        filmes=[
            filme(id="1", budget="0"),  # fica, com orcamento nulo
            filme(id="1", budget="0"),  # cópia: conta em "cópias"
            filme(id="1", budget="0", popularity="0.5"),  # sai "por chave"
            filme(id="abc"),  # sai em "quebradas"
        ],
    )

    transformacao.main()

    tela = capsys.readouterr().out
    assert "1 quebradas, 1 cópias, 1 por chave" in tela
    assert "    orcamento" in tela
    assert "Total: 1 linhas" in tela
