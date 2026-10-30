CONTEXTO
Estou construindo um pipeline de dados em Python sobre o dataset público
"The Movies Dataset" (Kaggle, Rounak Banik: metadados do TMDB e notas do
MovieLens, filmes até julho de 2017). Trabalho com spec-driven development:
a spec abaixo é a fonte da verdade e o código é consequência dela. Não
acrescente requisito que não esteja escrito aqui. Se algo estiver ambíguo,
pergunte antes de escrever código.

STACK
- Python 3.13, uv, DuckDB 2.0 (filmes.duckdb na raiz do projeto)
- Rodo no Windows.

O QUE JÁ EXISTE (use, não reimplemente)
pipeline/db.py: conectar(), criar_schema(con, nome), ARQUIVO_BANCO
O schema raw, criado por pipeline/ingestao.py: raw.filmes, raw.links,
raw.avaliacoes, todas as colunas VARCHAR, campo vazio como NULL.

ARTEFATO A PRODUZIR
pipeline/transformacao.py, executável com:
  uv run python -m pipeline.transformacao

SPEC

1. ESCOPO
   Lê de raw, escreve no schema refined. Nunca escreve em raw.
   Três tabelas: raw.filmes -> refined.filmes, raw.links -> refined.links,
   raw.avaliacoes -> refined.avaliacoes.
   Toda a transformação é SQL executado pelo DuckDB, disparado pelo Python.
   Motivo: o dado já está no banco; trazer para o pandas converteria
   dinheiro em float.

2. NOMES E COLUNAS
   refined.filmes fica só com as colunas abaixo. As outras de raw.filmes
   (genres, production_companies, overview, poster_path...) ficam fora.
   Motivo: listas guardadas como texto e textos livres que nenhum
   indicador do projeto usa; continuam disponíveis em raw.
     id -> filme_id                    imdb_id -> imdb_id
     title -> titulo                   original_title -> titulo_original
     original_language -> idioma_original
     release_date -> data_lancamento   status -> status
     budget -> orcamento               revenue -> receita
     runtime -> duracao_min            vote_average -> nota_tmdb
     vote_count -> votos_tmdb          popularity -> popularidade
     adult -> adulto
   refined.links
     movieId -> filme_ml_id            imdbId -> imdb_id
     tmdbId -> filme_id
   refined.avaliacoes
     userId -> usuario_id              movieId -> filme_ml_id
     rating -> nota                    timestamp -> data_hora
   Motivo dos nomes: filme_id é sempre o id do TMDB, e filme_ml_id sempre o
   do MovieLens. São numerações diferentes, e só links liga as duas.

3. TIPOS
   filme_id, filme_ml_id, usuario_id, duracao_min, votos_tmdb: INTEGER.
     duracao_min vem como '81.0': CAST para DOUBLE e depois para INTEGER
     (nenhuma das 45.463 linhas válidas tem fração).
   orcamento, receita: DECIMAL(15,2). Motivo: dinheiro; o maior valor
     é 2.787.965.087 (Avatar).
   nota_tmdb: DECIMAL(3,1). nota: DECIMAL(2,1). popularidade: DOUBLE.
   data_lancamento: DATE, formato declarado '%Y-%m-%d' (strptime).
   data_hora: TIMESTAMP em UTC, a partir dos segundos desde 1970:
     make_timestamp(CAST(timestamp AS BIGINT) * 1000000).
     Motivo: to_timestamp devolve TIMESTAMPTZ e o resultado mudaria
     conforme o fuso da máquina.
   adulto: BOOLEAN (adult = 'True').
   imdb_id: VARCHAR nas duas tabelas. Motivo: em links, 30.248 imdbId
     começam com zero ('0114709'); como número perderiam o zero.
   Todo o resto continua VARCHAR.

4. CONVERSÃO QUE FALHA
   Para tudo. strptime e CAST, nunca try_strptime ou TRY_CAST.
   Ao falhar: tabela, coluna, um exemplo do valor, sys.exit(1).
   Motivo: nulo fabricado pela conversão fica indistinguível do nulo real.

5. LINHAS QUEBRADAS (só em filmes)
   Antes de converter, saem as linhas cujo id não é só dígitos
   (regexp_full_match(id, '[0-9]+')). São 3 no dado atual: a segunda metade
   de 3 filmes cuja linha se partiu no CSV (82663, 122662, 249260), com as
   colunas deslocadas (o id contém uma data, o budget um caminho de imagem).
   A metade com o id fica em refined, sem data, status, notas e votos.
   Juntar as metades fica fora do escopo: são só 3 filmes e nenhum tem
   orçamento nem receita, então nenhum indicador muda.
   A saída na tela mostra quantas saíram. Qualquer outra falha de
   conversão continua parando tudo (item 4).

6. DUPLICATAS
   Chaves: filmes (filme_id), links (filme_ml_id),
           avaliacoes (usuario_id, filme_ml_id).
   Linha inteira repetida: mantém uma e conta. Em filmes são 17.
   Chave repetida com conteúdo diferente: em filmes, 13 filmes aparecem
   duas vezes, e as linhas diferem só em popularity (13) e vote_count (2),
   que são medidas do TMDB tiradas em momentos diferentes. Mantém a linha
   com maior votos_tmdb e, no empate, a com maior popularidade
   (row_number() OVER (PARTITION BY id ORDER BY ...)). Motivo: é a
   medição mais recente; o resto do conteúdo é idêntico.
   Se aparecer chave repetida diferindo em qualquer outra coluna, ou em
   links ou avaliacoes: para, mostra a chave e as linhas, sys.exit(1).
   filme_id repetido em links NÃO é duplicata (29 filme_id aparecem em
   mais de uma linha): dois cadastros do MovieLens apontam para o mesmo
   filme do TMDB. A chave de links é filme_ml_id, e ela não repete.

7. NULOS E ZEROS
   Nenhuma linha é apagada por ter nulo. Nenhum nulo é preenchido.
   Exceção única, escrita: orcamento e receita iguais a 0 viram NULL
   (NULLIF). Motivo: no TMDB, 0 quer dizer "não informado". 36.553
   filmes têm orçamento 0; a média de orçamento com eles seria um terço
   do valor real.
   Anomalias de fato ficam, sem correção:
     244 filmes com orçamento menor que US$ 1.000 e 154 com receita menor
     que US$ 1.000 (provavelmente digitados em milhões);
     87 filmes sem data de lançamento; 84 sem status; 3 sem título
     (os 3 sem título são os filmes de linha partida do item 5, e também
     entram nos 87 e nos 84).
   Motivo: refined não corrige fato; o filtro é decisão de cada mart.
   Avaliações de filmes que não estão em refined.filmes também ficam.

8. SAÍDA NA TELA
   Uma linha por tabela:
     refined.filmes        45.466 ->  45.433 linhas  (3 quebradas, 17 cópias, 13 por chave)
   Abaixo, indentadas, as colunas com nulo e a contagem. Contagens do banco,
   milhar com ponto, linha final com o total. stdout em utf-8.

REEXECUÇÃO
   CREATE OR REPLACE TABLE. Rodar dez vezes = rodar uma.

ERRO
   Faltando qualquer das três tabelas em raw: lista quais, manda rodar
   "uv run python -m pipeline.ingestao", sys.exit(1).

CRITÉRIOS DE ACEITE
- refined.filmes 45.433, refined.links 45.843, refined.avaliacoes 100.004.
  Total: 191.280.
- count(DISTINCT filme_id) em refined.filmes = 45.433.
- Nulos em refined.filmes: orcamento 36.553, receita 38.035,
  data_lancamento 87, duracao_min 260.
- sum(receita) em refined.filmes = 509.401.325.991,00, igual à soma de
  revenue em raw contando uma vez cada id válido
  (SELECT DISTINCT id, revenue ...).
- imdb_id em refined.links mantém o zero: '0114709', não 114709.
- data_hora vai de 1995-01-09 11:46:49 a 2016-10-16 17:57:24.
- Rodar duas vezes seguidas imprime exatamente a mesma coisa.

ENTREGA
1. A spec como docstring no topo do arquivo, com o motivo de cada regra.
2. O código, comentado só onde a decisão não é óbvia.
3. Uma lista final do que você assumiu e que não estava na spec.
