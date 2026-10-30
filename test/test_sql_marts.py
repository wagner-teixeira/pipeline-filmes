"""Testes dos sql/marts/*.sql reais, rodados sobre tabelas refined inventadas."""

from decimal import Decimal
from pathlib import Path

import duckdb

PASTA_SQL = Path(__file__).resolve().parent.parent / "sql" / "marts"
RETORNO_POR_ANO = "01_retorno_por_ano.sql"
TOP_LUCRO = "02_top_lucro.sql"
NOTA_POR_FAIXA = "03_nota_por_faixa_receita.sql"
UM_MILHAO = 1_000_000


def filme(
    filme_id=1,
    orcamento=UM_MILHAO,
    receita=UM_MILHAO,
    data="2000-06-15",
    status="Released",
    titulo="Filme",
):
    return (filme_id, titulo, data, status, orcamento, receita)


def rodar_mart(tmp_path, arquivo, filmes=(), links=(), avaliacoes=()):
    sql = (PASTA_SQL / arquivo).read_text(encoding="utf-8")
    with duckdb.connect(tmp_path / "teste.duckdb") as con:
        con.execute("CREATE SCHEMA refined")
        con.execute("""
            CREATE TABLE refined.filmes (
                filme_id INTEGER,
                titulo VARCHAR,
                data_lancamento DATE,
                status VARCHAR,
                orcamento DECIMAL(15,2),
                receita DECIMAL(15,2)
            )
        """)
        con.execute(
            "CREATE TABLE refined.links (filme_ml_id INTEGER, filme_id INTEGER)"
        )
        con.execute(
            "CREATE TABLE refined.avaliacoes "
            "(usuario_id INTEGER, filme_ml_id INTEGER, nota DECIMAL(2,1))"
        )
        for linha in filmes:
            con.execute("INSERT INTO refined.filmes VALUES (?, ?, ?, ?, ?, ?)", linha)
        for linha in links:
            con.execute("INSERT INTO refined.links VALUES (?, ?)", linha)
        for linha in avaliacoes:
            con.execute("INSERT INTO refined.avaliacoes VALUES (?, ?, ?)", linha)
        return con.execute(sql).fetchall()


def test_01_filme_com_orcamento_abaixo_de_1_milhao_fica_fora(tmp_path):
    linhas = rodar_mart(
        tmp_path,
        RETORNO_POR_ANO,
        filmes=[
            filme(1, orcamento=999_999, receita=5_000_000),  # um dólar abaixo: fora
            filme(2, orcamento=2_000_000, receita=6_000_000),  # entra
        ],
    )

    assert linhas == [(2000, 1, Decimal("2000000.00"), Decimal("6000000.00"), 3.0)]


def test_01_orcamento_de_exatamente_1_milhao_entra(tmp_path):
    linhas = rodar_mart(
        tmp_path,
        RETORNO_POR_ANO,
        filmes=[
            filme(1, orcamento=UM_MILHAO, receita=UM_MILHAO),  # bem no limite
        ],
    )

    assert [linha[1] for linha in linhas] == [1]


def test_01_receita_abaixo_de_1_milhao_fica_fora(tmp_path):
    linhas = rodar_mart(
        tmp_path,
        RETORNO_POR_ANO,
        filmes=[
            filme(1, receita=999_999),  # um dólar abaixo: fora
            filme(2, receita=2_000_000),  # entra
        ],
    )

    assert [linha[1] for linha in linhas] == [1]


def test_01_filme_sem_orcamento_ou_sem_status_released_fica_fora(tmp_path):
    linhas = rodar_mart(
        tmp_path,
        RETORNO_POR_ANO,
        filmes=[
            filme(1, orcamento=None),  # nulo (0 no TMDB): fora
            filme(2, status="Rumored"),  # não foi lançado: fora
            filme(3, data=None),  # sem ano onde agrupar: fora
            filme(4),  # o único que cumpre tudo
        ],
    )

    assert [linha[1] for linha in linhas] == [1]


def test_01_retorno_e_receita_total_sobre_orcamento_total(tmp_path):
    # Receita total 19 mi / orçamento total 10 mi = 1,9.
    # A média dos retornos daria (10 + 1) / 2 = 5,5.
    linhas = rodar_mart(
        tmp_path,
        RETORNO_POR_ANO,
        filmes=[
            filme(1, orcamento=1_000_000, receita=10_000_000),  # pequeno, retorno 10
            filme(2, orcamento=9_000_000, receita=9_000_000),  # grande, retorno 1
        ],
    )

    assert linhas == [(2000, 2, Decimal("10000000.00"), Decimal("19000000.00"), 1.9)]


def test_01_cada_ano_vira_uma_linha_em_ordem(tmp_path):
    linhas = rodar_mart(
        tmp_path,
        RETORNO_POR_ANO,
        filmes=[
            filme(1, data="2001-01-01"),  # ano mais novo inserido primeiro
            filme(2, data="1999-12-31"),  # ano mais velho: tem de vir na frente
            filme(3, data="1999-01-01"),  # mesmo ano do anterior: soma com ele
        ],
    )

    assert [(ano, filmes) for ano, filmes, *_ in linhas] == [(1999, 2), (2001, 1)]


def test_02_empate_de_lucro_e_desempatado_por_filme_id(tmp_path):
    linhas = rodar_mart(
        tmp_path,
        TOP_LUCRO,
        filmes=[
            filme(7, orcamento=2_000_000, receita=5_000_000),  # lucro 3 mi, id maior
            filme(3, orcamento=1_000_000, receita=4_000_000),  # lucro 3 mi, id menor
        ],
    )

    assert [(posicao, filme_id) for posicao, filme_id, *_ in linhas] == [(1, 3), (2, 7)]


def test_02_lucro_e_receita_menos_orcamento(tmp_path):
    linhas = rodar_mart(
        tmp_path,
        TOP_LUCRO,
        filmes=[
            filme(1, orcamento=2_000_000, receita=5_000_000),  # lucro 3 mi, retorno 2,5
        ],
    )

    assert linhas[0][4:] == (
        Decimal("2000000.00"),
        Decimal("5000000.00"),
        Decimal("3000000.00"),
        2.5,
    )


def test_02_fica_so_com_os_10_de_maior_lucro(tmp_path):
    linhas = rodar_mart(
        tmp_path,
        TOP_LUCRO,
        # Onze filmes com lucros crescentes: o de id 1, menor lucro, sai.
        filmes=[filme(i, receita=UM_MILHAO * (i + 1)) for i in range(1, 12)],
    )

    assert [linha[1] for linha in linhas] == list(range(11, 1, -1))


def test_02_filme_abaixo_de_1_milhao_fica_fora(tmp_path):
    linhas = rodar_mart(
        tmp_path,
        TOP_LUCRO,
        filmes=[
            filme(1, orcamento=1, receita=9_000_000),  # orçamento digitado errado
            filme(2),  # entra, mesmo com lucro menor
        ],
    )

    assert [linha[1] for linha in linhas] == [2]


def test_03_filme_com_3_avaliacoes_e_outro_com_1_pesam_igual(tmp_path):
    # Por filme: (4 + 2) / 2 = 3,0. Por avaliação seria (4 + 4 + 4 + 2) / 4 = 3,5.
    linhas = rodar_mart(
        tmp_path,
        NOTA_POR_FAIXA,
        filmes=[
            filme(1, receita=5_000_000),  # mesma faixa do filme 2
            filme(2, receita=5_000_000),  # mesma faixa do filme 1
        ],
        links=[
            (10, 1),  # ponte do filme 1
            (20, 2),  # ponte do filme 2
        ],
        avaliacoes=[
            (1, 10, "4.0"),  # primeira das três notas do filme 1
            (2, 10, "4.0"),  # segunda
            (3, 10, "4.0"),  # terceira
            (1, 20, "2.0"),  # única nota do filme 2
        ],
    )

    assert linhas == [("1 · até 10 mi", 2, 4, 3.0)]


def test_03_dois_filme_ml_id_do_mesmo_filme_contam_como_um_so(tmp_path):
    linhas = rodar_mart(
        tmp_path,
        NOTA_POR_FAIXA,
        filmes=[
            filme(1, receita=5_000_000),  # o filme com dois cadastros
        ],
        links=[
            (10, 1),  # primeiro cadastro do MovieLens
            (20, 1),  # segundo cadastro do mesmo filme
        ],
        avaliacoes=[
            (1, 10, "4.0"),  # nota dada pelo primeiro cadastro
            (2, 20, "2.0"),  # nota dada pelo segundo: entram na mesma média
        ],
    )

    assert linhas == [("1 · até 10 mi", 1, 2, 3.0)]


def test_03_receita_nula_cai_em_sem_receita_informada(tmp_path):
    linhas = rodar_mart(
        tmp_path,
        NOTA_POR_FAIXA,
        filmes=[
            filme(1, receita=None),  # sem receita: tem faixa própria
        ],
        links=[
            (10, 1),  # ponte do filme
        ],
        avaliacoes=[
            (1, 10, "3.5"),  # precisa de nota para aparecer no mart
        ],
    )

    assert linhas == [("0 · sem receita informada", 1, 1, 3.5)]


def test_03_cada_limite_de_faixa_abre_a_faixa_de_cima(tmp_path):
    linhas = rodar_mart(
        tmp_path,
        NOTA_POR_FAIXA,
        filmes=[
            filme(1, receita=9_999_999),  # último valor da faixa 1
            filme(2, receita=10_000_000),  # primeiro da faixa 2
            filme(3, receita=100_000_000),  # primeiro da faixa 3
            filme(4, receita=1_000_000_000),  # primeiro da faixa 4
        ],
        links=[
            (10, 1),  # ponte do filme 1
            (20, 2),  # ponte do filme 2
            (30, 3),  # ponte do filme 3
            (40, 4),  # ponte do filme 4
        ],
        avaliacoes=[
            (1, 10, "1.0"),  # uma nota por filme, para todos aparecerem
            (1, 20, "2.0"),  # idem
            (1, 30, "3.0"),  # idem
            (1, 40, "4.0"),  # idem
        ],
    )

    assert linhas == [
        ("1 · até 10 mi", 1, 1, 1.0),
        ("2 · 10 a 100 mi", 1, 1, 2.0),
        ("3 · 100 mi a 1 bi", 1, 1, 3.0),
        ("4 · acima de 1 bi", 1, 1, 4.0),
    ]


def test_03_avaliacao_sem_filme_correspondente_fica_fora(tmp_path):
    linhas = rodar_mart(
        tmp_path,
        NOTA_POR_FAIXA,
        filmes=[
            filme(1, receita=5_000_000),  # o único filme que casa
        ],
        links=[
            (10, 1),  # ponte que casa
            (20, 999),  # aponta para filme que não está em refined.filmes
            (30, None),  # sem filme do TMDB
        ],
        avaliacoes=[
            (1, 10, "4.0"),  # a única nota que conta
            (1, 20, "1.0"),  # filme 999 não existe: fora
            (1, 30, "1.0"),  # link sem filme_id: fora
            (1, 40, "1.0"),  # filme_ml_id sem link: fora
        ],
    )

    assert linhas == [("1 · até 10 mi", 1, 1, 4.0)]
