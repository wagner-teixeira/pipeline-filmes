CONTEXTO
Estou construindo um pipeline de dados em Python sobre o dataset público
"The Movies Dataset" (Kaggle). Trabalho com spec-driven development: a spec
abaixo é a fonte da verdade e o código é consequência dela. Não acrescente
requisito que não esteja escrito aqui. Se algo estiver ambíguo, pergunte
antes de escrever código.

STACK
- Python 3.13, uv, DuckDB 2.0
- pytest e pytest-cov, já instalados com uv add --dev
- Rodo no Windows.

O QUE JÁ EXISTE (leia tudo antes de escrever qualquer teste)
pipeline/db.py, pipeline/ingestao.py, pipeline/transformacao.py,
pipeline/marts.py, ui.py e sql/marts/*.sql.
Cada módulo tem a sua spec na docstring do topo, e as specs completas
estão em specs/.

ARTEFATOS A PRODUZIR
Pasta test/ na raiz, com: test_db.py, test_ingestao.py,
test_transformacao.py, test_marts.py, test_sql_marts.py.
Executável com:
  uv run pytest --cov
Configuração no pyproject.toml:
  [tool.pytest.ini_options]
  testpaths = ["test"]
  pythonpath = ["."]
  [tool.coverage.run]
  source = ["."]
  omit = ["test/*", "ui.py", ".venv/*"]
  [tool.coverage.report]
  fail_under = 60
  show_missing = true

SPEC
1. META
   60% de coverage de linhas no TOTAL de pipeline/. ui.py fica fora:
   só sobe a interface do DuckDB, e testar servidor por coverage não
   prova nada.

2. NUNCA O BANCO NEM OS DADOS DO PROJETO
   Nenhum teste abre filmes.duckdb nem lê os arquivos de raw/.
   Cada teste usa tmp_path: um DuckDB novo dentro dele e, quando precisar
   de CSV, arquivos pequenos escritos pelo próprio teste. Para o código
   achar esses arquivos e esse banco, use monkeypatch.setattr nas
   constantes de caminho (PASTA_RAW, ARQUIVO_BANCO, a pasta de sql/marts)
   do módulo onde elas são usadas.
   Motivo: o teste roda em qualquer máquina, sem o pipeline ter rodado,
   e não altera o banco de ninguém.
   Exceção: test_sql_marts.py lê os arquivos .sql reais de sql/marts/,
   porque são eles o código sob teste; o dado continua inventado.

3. DADO INVENTADO, RESULTADO DA REGRA
   Toda entrada é inventada: poucas linhas, cada uma com um comentário
   dizendo por que está ali. O valor esperado sai da conta feita sobre
   essa entrada, nunca de um número medido no dataset (45.433, 191.280,
   4.631, 99.810...). Motivo: o dado muda; a regra não.

4. O QUE TESTAR
   Os critérios de aceite das docstrings são a lista de partida. Em especial:
   - ingestão: o CSV vira tabela com as mesmas linhas, tudo VARCHAR;
     o texto "NA" continua "NA" (não vira nulo); arquivo faltando encerra
     com SystemExit sem gravar nada.
   - transformação: linha com id que não é só dígitos sai; cópia exata
     sai; mesmo id com popularidade diferente fica a linha de mais votos;
     orçamento 0 vira NULL; imdb_id '0114709' mantém o zero; data inválida
     encerra com SystemExit; tabela faltando em raw encerra com SystemExit.
   - marts (executor): arquivo sem prefixo NN_ para antes de executar;
     mart vazio encerra e deixa o schema marts como estava; arquivo apagado
     faz o mart sumir na execução seguinte.
   - sql/marts, rodados sobre tabelas refined inventadas:
     01: filme com orçamento abaixo de 1 milhão fica fora; retorno é
         receita total / orçamento total do ano, não a média dos retornos.
     02: empate de lucro é desempatado por filme_id.
     03: um filme com 3 avaliações e outro com 1 pesam igual na média da
         faixa; dois filme_ml_id que apontam para o mesmo filme_id contam
         como um filme só; receita nula cai em '0 · sem receita informada'.
   Caminho de erro com sys.exit: pytest.raises(SystemExit).

5. ESTILO
   pytest puro: funções test_* com assert. Fixtures, só tmp_path,
   monkeypatch e capsys. DuckDB de verdade, nunca mock do banco.
   O nome do teste é a frase que ele prova:
     test_orcamento_zero_vira_nulo
   Proibido: teste sem assert, skip, xfail, try/except em volta do assert,
   pytest.approx em dinheiro. Motivo: cada um sobe o coverage sem provar
   nada.

6. NÃO ALTERE O CÓDIGO DO PROJETO
   Nenhum arquivo muda fora de test/ e do pyproject.toml. Se uma parte só
   for testável mudando o código, não mude: liste na entrega, com o motivo.

CRITÉRIOS DE ACEITE
- uv run pytest --cov termina sem falha, com TOTAL de 60% ou mais.
- Com filmes.duckdb renomeado, o resultado é o mesmo.
- Uma busca por 45433, 45.433, 191280 e 99810 dentro de test/ não encontra
  nada.
- git status mostra mudança só em test/ e no pyproject.toml.

ENTREGA
1. Os arquivos de teste.
2. A saída de uv run pytest --cov, com a tabela por arquivo.
3. As linhas que ficaram sem teste (coluna Missing) e por quê.
4. Uma lista final do que você assumiu e que não estava na spec.
