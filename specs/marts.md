CONTEXTO
Estou construindo um pipeline de dados em Python sobre o dataset público
"The Movies Dataset" (Kaggle). Trabalho com spec-driven development: a spec
abaixo é a fonte da verdade e o código é consequência dela. Não acrescente
requisito que não esteja escrito aqui. Se algo estiver ambíguo, pergunte
antes de escrever código.

STACK
- Python 3.13, uv, DuckDB 2.0 (filmes.duckdb na raiz do projeto)
- Rodo no Windows.

O QUE JÁ EXISTE (use, não reimplemente)
pipeline/db.py: conectar(), criar_schema(con, nome), ARQUIVO_BANCO
pipeline/ingestao.py: formatar() (milhar com ponto)
O schema refined, com três tabelas (filmes, links, avaliacoes), criado por
pipeline/transformacao.py.
A pasta sql/marts/, com arquivos NN_nome.sql. Cada arquivo tem um único
SELECT, que pode começar com comentários (--) e com WITH. Hoje são três:
  01_retorno_por_ano.sql, 02_top_lucro.sql, 03_nota_por_faixa_receita.sql

ARTEFATO A PRODUZIR
pipeline/marts.py, executável com:
  uv run python -m pipeline.marts

SPEC
1. ESCOPO
   Lê de refined, escreve no schema marts. Nunca escreve em raw nem em
   refined. O schema marts é apagado e recriado a cada execução
   (DROP SCHEMA IF EXISTS marts CASCADE). Motivo: um mart cujo arquivo foi
   apagado não pode continuar existindo no banco.

2. UM ARQUIVO, UMA TABELA
   Lê todos os sql/marts/*.sql em ordem alfabética.
   Nome da tabela = nome do arquivo sem a extensão e sem o prefixo NN_:
     sql/marts/01_retorno_por_ano.sql -> marts.retorno_por_ano
   Executa: CREATE TABLE marts.<nome> AS <conteúdo do arquivo>
   Tira espaços e um ponto e vírgula do final do conteúdo, e nada mais.
   O Python não altera, não monta e não completa a SQL.
   Motivo: a regra de negócio mora inteira no arquivo .sql.
   Lê o arquivo com encoding="utf-8": os comentários têm acento e o "·"
   dos rótulos de faixa.

3. SAÍDA NA TELA
   Uma linha por mart, com a contagem vinda do banco, milhar com ponto:
     ✓ marts.retorno_por_ano          86 linhas
   Linha final com o número de marts e o total de linhas.
   stdout reconfigurado para utf-8.

4. ERRO
   Antes de tudo: se faltar qualquer uma das três tabelas em refined,
   lista quais, diz para rodar "uv run python -m pipeline.transformacao" e
   encerra com sys.exit(1).
   Se sql/marts/ não tiver nenhum arquivo: avisa e sys.exit(1).
   Antes de executar qualquer SQL: arquivo sem prefixo NN_ ou dois arquivos
   que dão o mesmo nome de tabela -> lista quais e sys.exit(1).
   Se um .sql falhar: mostra o nome do arquivo e a mensagem do DuckDB, não
   executa os seguintes, sys.exit(1).
   Se um mart voltar com zero linhas: mostra o nome e sys.exit(1).
   Motivo: mart vazio é quase sempre um JOIN que não casou.
   Tudo roda numa transação só (BEGIN ... COMMIT, ROLLBACK em qualquer
   falha, inclusive mart vazio): o schema marts volta a ser o da última
   execução que deu certo. Motivo: um schema pela metade engana quem lê.

CRITÉRIOS DE ACEITE
- Com os três arquivos de hoje:
    ✓ marts.retorno_por_ano          86 linhas
    ✓ marts.top_lucro                10 linhas
    ✓ marts.nota_por_faixa_receita    5 linhas
  3 marts, 101 linhas.
- Os marts conversam com refined:
    sum(filmes) de marts.retorno_por_ano = 4.631, igual a
      SELECT count(*) FROM refined.filmes WHERE status = 'Released'
      AND orcamento >= 1000000 AND receita >= 1000000
      AND data_lancamento IS NOT NULL;
    sum(avaliacoes) de marts.nota_por_faixa_receita = 99.810, e
      sum(filmes) = 9.025;
    marts.top_lucro começa com Avatar (lucro 2.550.965.087,00).
- Um arquivo sql/marts/00_teste.sql com "SELECT 1 AS x" cria marts.teste
  com 1 linha; apagar o arquivo e rodar de novo faz marts.teste sumir.
- Um arquivo com erro de sintaxe para tudo, com o nome do arquivo na tela,
  e marts continua exatamente como estava antes.
- Um arquivo teste.sql, sem prefixo, para antes de executar qualquer SQL.
- Rodar duas vezes seguidas imprime exatamente a mesma coisa.
Os testes dos critérios de erro usam arquivos temporários: ao terminar,
sql/marts/ tem só os três arquivos de hoje.

ENTREGA
1. A spec como docstring no topo do arquivo, com o motivo de cada regra.
2. O código, comentado só onde a decisão não é óbvia.
3. Uma lista final do que você assumiu e que não estava na spec.
