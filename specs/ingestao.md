CONTEXTO
Estou construindo um pipeline de dados em Python sobre o dataset público
"The Movies Dataset" (Kaggle, Rounak Banik: metadados do TMDB e notas do
MovieLens, filmes lançados até julho de 2017). Trabalho com spec-driven
development: a spec abaixo é a fonte da verdade e o código é consequência
dela. Não acrescente requisito que não esteja escrito aqui. Se algo estiver
ambíguo, pergunte antes de escrever código.

STACK
- Python 3.13, dependências gerenciadas com uv (duckdb e pandas já instalados)
- DuckDB como banco, arquivo filmes.duckdb na raiz do projeto
- Nenhum orquestrador. Script executável pela linha de comando.
- Rodo no Windows (Prompt de Comando e PowerShell).

O QUE JÁ EXISTE
A pasta raw/, na raiz, com três arquivos .csv (não comprimidos):
  movies_metadata.csv, links.csv, ratings_small.csv

ARTEFATOS A PRODUZIR
1. pipeline/__init__.py (vazio) e pipeline/db.py, com:
     PASTA_RAW                        Path da pasta raw/ na raiz do projeto
     ARQUIVO_BANCO                    Path do filmes.duckdb na raiz
     conectar()                       abre o filmes.duckdb, criando se faltar
     criar_schema(con, nome)          CREATE SCHEMA IF NOT EXISTS
     gravar(con, df, schema, tabela)  CREATE OR REPLACE a partir do DataFrame
                                      e devolve a contagem lida do banco
2. pipeline/ingestao.py, executável com:
     uv run python -m pipeline.ingestao
3. ui.py, na raiz, executável com:
     uv run python ui.py
4. .gitignore com: .venv/, __pycache__/, *.duckdb, *.duckdb.wal, .pytest_cache/,
   .coverage

SPEC

1. ESCOPO E NOMES
   Schema de destino: raw
   Mapa arquivo -> tabela, completo e literal:
     movies_metadata.csv  -> filmes
     links.csv            -> links
     ratings_small.csv    -> avaliacoes
   Ficam fora, de propósito, e não são lidos: credits.csv e keywords.csv
   (elenco e palavras-chave guardados como listas em texto, fora das
   perguntas do projeto) e ratings.csv (26 milhões de linhas, 710 MB:
   passa do limite de arquivo do GitHub; o ratings_small responde as
   mesmas perguntas).

2. PROIBIÇÕES (a regra central desta etapa)
   Nenhuma conversão de tipo. Nenhuma linha descartada ou deduplicada.
   Nenhum nome de coluna alterado. Nenhum valor corrigido, preenchido ou
   normalizado. Motivo: a fronteira entre "o dado que chegou" e "o dado que
   eu decidi" fica na passagem de raw para refined. Em particular, as
   linhas quebradas de movies_metadata.csv entram em raw como vieram.

3. REEXECUÇÃO
   CREATE OR REPLACE, nunca acrescenta. Rodar dez vezes = rodar uma.

4. LEITURA DO ARQUIVO
   pandas.read_csv com encoding="utf-8" declarado, dtype=str,
   keep_default_na=False e na_values=[""]: só o campo vazio vira nulo.
   Motivo: por padrão o pandas transforma em nulo textos como "NA", "null"
   e "None", e isso seria corrigir valor.
   Mantenha o comportamento padrão de aspas: movies_metadata.csv tem
   quebras de linha dentro do texto da sinopse.

5. TIPAGEM
   Toda coluna entra como texto. Motivo: em movies_metadata, budget,
   id e release_date têm valores que não são o que o nome promete (há
   linhas deslocadas); a conversão é decisão da etapa 2.

6. SAÍDA NA TELA
   Uma linha por tabela, nome qualificado e contagem vinda do banco
   (não do DataFrame), milhar com ponto:
     ✓ raw.filmes             45.466 linhas
   Linha final com o total. stdout reconfigurado para utf-8.

7. ERRO
   Antes de abrir o banco, verifica se os três arquivos existem em raw/.
   Faltando qualquer um: lista os que faltam, diz a pasta onde procurou e
   encerra com sys.exit(1), sem gravar nada.

CRITÉRIOS DE ACEITE (ingestão)
- raw.filmes 45.466, raw.links 45.843, raw.avaliacoes 100.004.
  Total: 191.313 linhas.
- Rodar duas vezes seguidas imprime exatamente a mesma coisa.
- DESCRIBE raw.filmes mostra todas as colunas como VARCHAR.
- Renomear links.csv faz o script parar antes de gravar qualquer tabela.
- O script termina sozinho e devolve o terminal.

SPEC DO ui.py
U1. Abre o filmes.duckdb da raiz, roda INSTALL ui; LOAD ui; CALL start_ui()
    (servidor em http://localhost:4213, abre o navegador).
U2. Fica de pé até Ctrl+C, imprimindo a URL e "Ctrl+C para encerrar"; no
    Ctrl+C fecha a conexão e sai sem traceback. Motivo: o arquivo aceita um
    único processo escrevendo; com o ui.py de pé, o pipeline dá erro de lock.
U3. Se filmes.duckdb não existir, diz para rodar a ingestão e sys.exit(1).
    Não usa conectar(), que criaria um banco vazio.
U4. Não importa pipeline/ingestao.py, e a ingestão não importa ui.py.
U5. stdout reconfigurado para utf-8.

ENTREGA, para cada arquivo
1. A spec como docstring no topo, dizendo por que cada regra existe.
2. O código, comentado só onde a decisão não é óbvia.
3. Uma lista final do que você assumiu e que não estava na spec.
