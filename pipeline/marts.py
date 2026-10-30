"""Executor dos marts: cada sql/marts/NN_nome.sql vira uma tabela em marts.

Executar com: uv run python -m pipeline.marts

Spec (specs/marts.md), e por que cada regra existe:

1. Escopo
   Lê de refined, escreve no schema marts, nunca escreve em raw nem em
   refined. O schema marts é apagado e recriado a cada execução
   (DROP SCHEMA IF EXISTS marts CASCADE). Motivo: um mart cujo arquivo foi
   apagado não pode continuar existindo no banco.

2. Um arquivo, uma tabela
   Lê todos os sql/marts/*.sql em ordem alfabética. Nome da tabela = nome do
   arquivo sem a extensão e sem o prefixo NN_:
     sql/marts/01_retorno_por_ano.sql -> marts.retorno_por_ano
   Executa: CREATE TABLE marts.<nome> AS <conteúdo do arquivo>
   Tira espaços e um ponto e vírgula do final do conteúdo, e nada mais. O
   Python não altera, não monta e não completa a SQL. Motivo: a regra de
   negócio mora inteira no arquivo .sql.
   Lê o arquivo com encoding="utf-8". Motivo: os comentários têm acento e os
   rótulos de faixa têm "·".

3. Saída na tela
   Uma linha por mart, com a contagem vinda do banco, milhar com ponto:
     ✓ marts.retorno_por_ano          86 linhas
   Linha final com o número de marts e o total de linhas. stdout
   reconfigurado para utf-8, porque o console do Windows pode não ter como
   escrever o "✓" na codificação padrão.

4. Erro
   Antes de tudo: se faltar qualquer uma das três tabelas em refined, lista
   quais, diz para rodar "uv run python -m pipeline.transformacao" e encerra
   com sys.exit(1).
   Se sql/marts/ não tiver nenhum arquivo: avisa e sys.exit(1).
   Antes de executar qualquer SQL: arquivo sem prefixo NN_ ou dois arquivos
   que dão o mesmo nome de tabela -> lista quais e sys.exit(1).
   Se um .sql falhar: mostra o nome do arquivo e a mensagem do DuckDB, não
   executa os seguintes, sys.exit(1).
   Se um mart voltar com zero linhas: mostra o nome e sys.exit(1). Motivo:
   mart vazio é quase sempre um JOIN que não casou.
   Tudo roda numa transação só (BEGIN ... COMMIT, ROLLBACK em qualquer falha,
   inclusive mart vazio): o schema marts volta a ser o da última execução que
   deu certo. Motivo: um schema pela metade engana quem lê.
"""

import re
import sys

import duckdb

from pipeline.db import RAIZ, conectar, criar_schema
from pipeline.ingestao import formatar

SCHEMA_ORIGEM = "refined"
SCHEMA_DESTINO = "marts"
TABELAS_ORIGEM = ("filmes", "links", "avaliacoes")
PASTA_MARTS = RAIZ / "sql" / "marts"
PREFIXO = re.compile(r"[0-9]{2}_(.+)")
# Da primeira letra do nome ao último dígito, descontado o espaço que os separa.
LARGURA_LINHA = 32


def verificar_tabelas_refined(con):
    existentes = {
        nome
        for (nome,) in con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = ?",
            [SCHEMA_ORIGEM],
        ).fetchall()
    }
    faltando = [tabela for tabela in TABELAS_ORIGEM if tabela not in existentes]
    if faltando:
        print(f"Tabelas não encontradas no schema {SCHEMA_ORIGEM}:")
        for tabela in faltando:
            print(f"  {tabela}")
        print("Rode a transformação primeiro:")
        print("  uv run python -m pipeline.transformacao")
        sys.exit(1)


def listar_arquivos():
    arquivos = sorted(PASTA_MARTS.glob("*.sql"))
    if not arquivos:
        print(f"Nenhum arquivo .sql em {PASTA_MARTS}")
        sys.exit(1)
    return arquivos


def nomear_marts(arquivos):
    sem_prefixo = []
    por_tabela = {}
    for arquivo in arquivos:
        prefixado = PREFIXO.fullmatch(arquivo.stem)
        if prefixado is None:
            sem_prefixo.append(arquivo)
        else:
            # O DuckDB não diferencia maiúsculas em nomes de tabela: Lucro e
            # lucro colidiriam só no CREATE TABLE, depois de executar SQL.
            por_tabela.setdefault(prefixado[1].lower(), []).append(
                (arquivo, prefixado[1])
            )
    repetidos = {
        tabela: marts for tabela, marts in por_tabela.items() if len(marts) > 1
    }

    if sem_prefixo:
        print("Arquivos sem o prefixo NN_:")
        for arquivo in sem_prefixo:
            print(f"  {arquivo.name}")
    for tabela, marts in repetidos.items():
        print(f"Arquivos que dão a mesma tabela {SCHEMA_DESTINO}.{tabela}:")
        for arquivo, _ in marts:
            print(f"  {arquivo.name}")
    if sem_prefixo or repetidos:
        sys.exit(1)
    return [mart for marts in por_tabela.values() for mart in marts]


def criar_mart(con, arquivo, tabela):
    try:
        sql = arquivo.read_text(encoding="utf-8").rstrip().removesuffix(";").rstrip()
        con.execute(f'CREATE TABLE "{SCHEMA_DESTINO}"."{tabela}" AS {sql}')
    except (duckdb.Error, UnicodeDecodeError) as erro:
        print(f"Falhou em {arquivo.name}:")
        print(f"  {erro}")
        sys.exit(1)

    linhas = con.execute(
        f'SELECT count(*) FROM "{SCHEMA_DESTINO}"."{tabela}"'
    ).fetchone()[0]
    if linhas == 0:
        print(f"Mart vazio: {SCHEMA_DESTINO}.{tabela} ({arquivo.name})")
        sys.exit(1)
    return linhas


def executar(con, marts):
    con.execute("BEGIN")
    try:
        con.execute(f'DROP SCHEMA IF EXISTS "{SCHEMA_DESTINO}" CASCADE')
        criar_schema(con, SCHEMA_DESTINO)
        contagens = {
            tabela: criar_mart(con, arquivo, tabela) for arquivo, tabela in marts
        }
    # BaseException porque sys.exit, usado acima, não é Exception.
    except BaseException:
        con.execute("ROLLBACK")
        raise
    con.execute("COMMIT")
    return contagens


def main():
    sys.stdout.reconfigure(encoding="utf-8")

    con = conectar()
    try:
        verificar_tabelas_refined(con)
        marts = nomear_marts(listar_arquivos())
        contagens = executar(con, marts)
    finally:
        con.close()

    # Só depois do COMMIT: um ✓ impresso antes de uma falha mostraria um mart
    # que o ROLLBACK desfez.
    for tabela, linhas in contagens.items():
        nome = f"{SCHEMA_DESTINO}.{tabela}"
        largura = max(LARGURA_LINHA - len(nome), 0)
        print(f"✓ {nome} {formatar(linhas):>{largura}} linhas")
    print(f"{len(contagens)} marts, {formatar(sum(contagens.values()))} linhas.")


if __name__ == "__main__":
    main()
