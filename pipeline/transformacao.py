"""Transformação do schema raw para o schema refined do filmes.duckdb.

Executar com: uv run python -m pipeline.transformacao

Spec (specs/transformacao.md), e por que cada regra existe:

1. Escopo
   Lê de raw, escreve em refined, nunca escreve em raw. Três tabelas:
   raw.filmes -> refined.filmes, raw.links -> refined.links,
   raw.avaliacoes -> refined.avaliacoes. Toda a transformação é SQL executado
   pelo DuckDB, disparado pelo Python. Motivo: o dado já está no banco; trazer
   para o pandas converteria dinheiro em float.

2. Nomes e colunas
   refined.filmes fica só com as colunas mapeadas em TABELAS. As outras de
   raw.filmes (genres, production_companies, overview, poster_path...) ficam
   fora. Motivo: listas guardadas como texto e textos livres que nenhum
   indicador do projeto usa; continuam disponíveis em raw.
   filme_id é sempre o id do TMDB e filme_ml_id sempre o do MovieLens. São
   numerações diferentes, e só links liga as duas.

3. Tipos
   filme_id, filme_ml_id, usuario_id, duracao_min, votos_tmdb: INTEGER.
     duracao_min vem como '81.0': CAST para DOUBLE e depois para INTEGER
     (nenhuma das 45.463 linhas válidas tem fração).
   orcamento, receita: DECIMAL(15,2). Motivo: dinheiro; o maior valor é
     2.787.965.087 (Avatar).
   nota_tmdb: DECIMAL(3,1). nota: DECIMAL(2,1). popularidade: DOUBLE.
   data_lancamento: DATE, formato declarado '%Y-%m-%d' (strptime).
   data_hora: TIMESTAMP em UTC, a partir dos segundos desde 1970, com
     make_timestamp(CAST(timestamp AS BIGINT) * 1000000). Motivo: to_timestamp
     devolve TIMESTAMPTZ e o resultado mudaria conforme o fuso da máquina.
   adulto: BOOLEAN (adult = 'True').
   imdb_id: VARCHAR nas duas tabelas. Motivo: em links, 30.248 imdbId começam
     com zero ('0114709'); como número perderiam o zero.
   Todo o resto continua VARCHAR.

4. Conversão que falha
   Para tudo. strptime e CAST, nunca try_strptime ou TRY_CAST. Ao falhar:
   tabela, coluna, um exemplo do valor, sys.exit(1). Motivo: nulo fabricado
   pela conversão fica indistinguível do nulo real.

5. Linhas quebradas (só em filmes)
   Antes de converter, saem as linhas cujo id não é só dígitos
   (regexp_full_match(id, '[0-9]+')). São 3 no dado atual: a segunda metade de
   3 filmes cuja linha se partiu no CSV (82663, 122662, 249260), com as colunas
   deslocadas (o id contém uma data, o budget um caminho de imagem). A metade
   com o id fica em refined, sem data, status, notas e votos. Juntar as metades
   fica fora do escopo: são só 3 filmes e nenhum tem orçamento nem receita,
   então nenhum indicador muda. A saída na tela mostra quantas saíram. Qualquer
   outra falha de conversão continua parando tudo.

6. Duplicatas
   Chaves: filmes (filme_id), links (filme_ml_id), avaliacoes (usuario_id,
   filme_ml_id).
   Linha inteira repetida: mantém uma e conta. Em filmes são 17.
   Chave repetida com conteúdo diferente: em filmes, 13 filmes aparecem duas
   vezes, e as linhas diferem só em popularity (13) e vote_count (2), que são
   medidas do TMDB tiradas em momentos diferentes. Mantém a linha com maior
   votos_tmdb e, no empate, a com maior popularidade. Motivo: é a medição mais
   recente; o resto do conteúdo é idêntico.
   Chave repetida diferindo em qualquer outra coluna, ou em links ou
   avaliacoes: para, mostra a chave e as linhas, sys.exit(1).
   filme_id repetido em links não é duplicata (29 filme_id aparecem em mais de
   uma linha): dois cadastros do MovieLens apontam para o mesmo filme do TMDB.
   A chave de links é filme_ml_id, e ela não repete.

7. Nulos e zeros
   Nenhuma linha é apagada por ter nulo. Nenhum nulo é preenchido. Exceção
   única: orcamento e receita iguais a 0 viram NULL (NULLIF). Motivo: no TMDB,
   0 quer dizer "não informado". 36.553 filmes têm orçamento 0; a média de
   orçamento com eles seria um terço do valor real.
   Anomalias de fato ficam, sem correção: 244 filmes com orçamento menor que
   US$ 1.000 e 154 com receita menor que US$ 1.000 (provavelmente digitados em
   milhões); 87 filmes sem data de lançamento; 84 sem status; 3 sem título (os
   3 sem título são os filmes de linha partida do item 5, e também entram nos
   87 e nos 84).
   Motivo: refined não corrige fato; o filtro é decisão de cada mart.
   Avaliações de filmes que não estão em refined.filmes também ficam.

8. Saída na tela
   Uma linha por tabela, com as contagens de entrada e saída e o que saiu;
   abaixo, indentadas, as colunas com nulo e a contagem. Contagens do banco,
   milhar com ponto, linha final com o total. stdout em utf-8.

Reexecução
   CREATE OR REPLACE TABLE. Rodar dez vezes = rodar uma.

Erro
   Faltando qualquer das três tabelas em raw: lista quais, manda rodar
   "uv run python -m pipeline.ingestao", sys.exit(1).
"""

import sys

import duckdb

from pipeline.db import conectar, criar_schema
from pipeline.ingestao import formatar

SCHEMA_ORIGEM = "raw"
SCHEMA_DESTINO = "refined"

# "origem": de onde se lê, já sem as linhas quebradas (item 5).
# "chave": colunas de raw, porque a checagem de duplicatas roda antes do CAST.
# "medidas": colunas que podem diferir dentro da mesma chave (item 6).
# "desempate": qual linha fica quando as medidas diferem (item 6).
TABELAS = {
    "filmes": {
        "origem": "(SELECT * FROM raw.filmes WHERE regexp_full_match(id, '[0-9]+'))",
        "chave": ("id",),
        "medidas": ("popularity", "vote_count"),
        "desempate": """
            QUALIFY row_number() OVER (
                PARTITION BY id
                ORDER BY CAST(vote_count AS INTEGER) DESC,
                         CAST(popularity AS DOUBLE) DESC
            ) = 1""",
        "colunas": {
            "filme_id": "CAST(id AS INTEGER)",
            "imdb_id": "imdb_id",
            "titulo": "title",
            "titulo_original": "original_title",
            "idioma_original": "original_language",
            "data_lancamento": "CAST(strptime(release_date, '%Y-%m-%d') AS DATE)",
            "status": "status",
            "orcamento": "NULLIF(CAST(budget AS DECIMAL(15,2)), 0)",
            "receita": "NULLIF(CAST(revenue AS DECIMAL(15,2)), 0)",
            "duracao_min": "CAST(CAST(runtime AS DOUBLE) AS INTEGER)",
            "nota_tmdb": "CAST(vote_average AS DECIMAL(3,1))",
            "votos_tmdb": "CAST(vote_count AS INTEGER)",
            "popularidade": "CAST(popularity AS DOUBLE)",
            "adulto": "adult = 'True'",
        },
    },
    "links": {
        "origem": "raw.links",
        "chave": ("movieId",),
        "medidas": (),
        "desempate": "",
        "colunas": {
            "filme_ml_id": "CAST(movieId AS INTEGER)",
            "imdb_id": "imdbId",
            "filme_id": "CAST(tmdbId AS INTEGER)",
        },
    },
    "avaliacoes": {
        "origem": "raw.avaliacoes",
        "chave": ("userId", "movieId"),
        "medidas": (),
        "desempate": "",
        "colunas": {
            "usuario_id": "CAST(userId AS INTEGER)",
            "filme_ml_id": "CAST(movieId AS INTEGER)",
            "nota": "CAST(rating AS DECIMAL(2,1))",
            "data_hora": "make_timestamp(CAST(timestamp AS BIGINT) * 1000000)",
        },
    },
}

# Os três tipos que CAST, strptime e make_timestamp levantam ao falhar.
ERROS_DE_CONVERSAO = (
    duckdb.ConversionException,
    duckdb.InvalidInputException,
    duckdb.OutOfRangeException,
)


def verificar_tabelas_raw(con):
    existentes = {
        nome
        for (nome,) in con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = ?",
            [SCHEMA_ORIGEM],
        ).fetchall()
    }
    faltando = [tabela for tabela in TABELAS if tabela not in existentes]
    if faltando:
        print(f"Tabelas não encontradas no schema {SCHEMA_ORIGEM}:")
        for tabela in faltando:
            print(f"  {tabela}")
        print("Rode a ingestão primeiro:")
        print("  uv run python -m pipeline.ingestao")
        sys.exit(1)


def verificar_conversoes(con, tabela):
    # Uma consulta por coluna porque o erro do DuckDB traz o valor, mas não
    # a coluna de destino. A mensagem dele é o exemplo exigido pelo item 4:
    # descobrir o valor por conta própria exigiria TRY_CAST.
    definicao = TABELAS[tabela]
    for coluna, expressao in definicao["colunas"].items():
        try:
            con.execute(f"SELECT count({expressao}) FROM {definicao['origem']}")
        except ERROS_DE_CONVERSAO as erro:
            print(f"Conversão falhou em {SCHEMA_DESTINO}.{tabela}, coluna {coluna}:")
            print(f"  {str(erro).splitlines()[0]}")
            sys.exit(1)


def verificar_chaves(con, tabela):
    definicao = TABELAS[tabela]
    origem = definicao["origem"]
    chave = ", ".join(definicao["chave"])
    # Sem as medidas, duas linhas distintas com a mesma chave só podem diferir
    # em coluna que não devia mudar.
    exclusao = ""
    if definicao["medidas"]:
        exclusao = f"EXCLUDE ({', '.join(definicao['medidas'])})"

    repetida = con.execute(f"""
        SELECT {chave}
        FROM (SELECT DISTINCT * {exclusao} FROM {origem})
        GROUP BY {chave}
        HAVING count(*) > 1
        ORDER BY {chave}
        LIMIT 1
    """).fetchone()
    if repetida is None:
        return

    condicao = " AND ".join(f"{coluna} = ?" for coluna in definicao["chave"])
    linhas = con.execute(
        f"SELECT DISTINCT * FROM {origem} WHERE {condicao}", list(repetida)
    ).fetchall()
    print(f"Chave repetida com conteúdo diferente em {SCHEMA_ORIGEM}.{tabela}:")
    print(f"  {chave} = {', '.join(repetida)}")
    for linha in linhas:
        print(f"  {linha}")
    sys.exit(1)


def contar(con, origem):
    return con.execute(f"SELECT count(*) FROM {origem}").fetchone()[0]


def transformar(con, tabela):
    definicao = TABELAS[tabela]
    origem = definicao["origem"]
    colunas = ",\n            ".join(
        f"{expressao} AS {coluna}" for coluna, expressao in definicao["colunas"].items()
    )
    con.execute(f"""
        CREATE OR REPLACE TABLE {SCHEMA_DESTINO}.{tabela} AS
        SELECT
            {colunas}
        FROM (SELECT DISTINCT * FROM {origem})
        {definicao["desempate"]}
    """)

    entrada = contar(con, f"{SCHEMA_ORIGEM}.{tabela}")
    validas = contar(con, origem)
    distintas = contar(con, f"(SELECT DISTINCT * FROM {origem})")
    saida = contar(con, f"{SCHEMA_DESTINO}.{tabela}")

    if tabela == "filmes":
        detalhe = (
            f"{formatar(entrada - validas)} quebradas, "
            f"{formatar(validas - distintas)} cópias, "
            f"{formatar(distintas - saida)} por chave"
        )
    else:
        detalhe = f"{formatar(validas - distintas)} cópias"
    nome = f"{SCHEMA_DESTINO}.{tabela}"
    print(f"{nome:<20}{formatar(entrada):>8} -> {formatar(saida):>7} linhas  ({detalhe})")
    return saida


def mostrar_nulos(con, tabela):
    colunas = list(TABELAS[tabela]["colunas"])
    contagens = ", ".join(f"count(*) - count({coluna})" for coluna in colunas)
    nulos = con.execute(
        f"SELECT {contagens} FROM {SCHEMA_DESTINO}.{tabela}"
    ).fetchone()
    for coluna, quantidade in zip(colunas, nulos):
        if quantidade:
            print(f"    {coluna:<18}{formatar(quantidade):>7}")


def main():
    sys.stdout.reconfigure(encoding="utf-8")

    con = conectar()
    try:
        verificar_tabelas_raw(con)
        # Tudo é verificado antes da primeira escrita: uma falha na última
        # tabela não deixa refined pela metade.
        for tabela in TABELAS:
            verificar_conversoes(con, tabela)
            verificar_chaves(con, tabela)

        criar_schema(con, SCHEMA_DESTINO)
        total = 0
        for tabela in TABELAS:
            total += transformar(con, tabela)
            mostrar_nulos(con, tabela)
        print(f"Total: {formatar(total)} linhas")
    finally:
        con.close()


if __name__ == "__main__":
    main()
