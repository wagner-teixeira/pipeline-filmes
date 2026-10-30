# Pipeline de bilheteria de filmes

Um pipeline de dados em Python e SQL que responde três perguntas sobre o
dinheiro do cinema: quanto os filmes renderam sobre o que custaram, quais
deram mais lucro e se bilheteria maior significa nota maior do público.

Construído com spec-driven development: cada etapa tem uma spec em `specs/`,
escrita antes do código, com o motivo de cada decisão e critérios de aceite
com números. O código foi escrito pela IA (Claude Code) a partir das specs
e conferido contra elas.

## Fonte do dado

[The Movies Dataset](https://www.kaggle.com/datasets/rounakbanik/the-movies-dataset),
de Rounak Banik, no Kaggle: metadados de 45 mil filmes coletados da API do
TMDB e avaliações de usuários do MovieLens (GroupLens). Filmes lançados até
julho de 2017. Licença: **CC0: Public Domain**, conforme a página do
dataset no Kaggle, o que permite versionar os dados num repositório
público. Este projeto não é endossado pelo TMDB nem pelo GroupLens.

Dos sete arquivos do dataset, entram três, versionados em `raw/`:

| Arquivo | Registros | Por que entra |
|---|---|---|
| `movies_metadata.csv` | 45.466 | orçamento, receita, data, status |
| `links.csv` | 45.843 | a ponte entre o id do MovieLens e o do TMDB |
| `ratings_small.csv` | 100.004 | notas de 671 usuários |

Ficam fora `credits.csv` e `keywords.csv` (elenco e palavras-chave guardados
como listas em texto, fora das perguntas), `links_small.csv` (um recorte do
`links`) e `ratings.csv` (26 milhões de linhas e 710 MB, acima do limite de
arquivo do GitHub; o `ratings_small` responde a mesma pergunta).

## As três camadas e o que é uma linha

```
raw/*.csv ──ingestao.py──▶ raw.* ──transformacao.py──▶ refined.* ──sql/marts/*.sql──▶ marts.*
            nada muda           tipos, duplicatas,           uma pergunta
            tudo texto          zeros decididos              por tabela
```

Tudo mora num arquivo só, `filmes.duckdb`, recriado do zero a cada execução.

| Tabela | Uma linha é | Chave | Linhas |
|---|---|---|---|
| `raw.filmes` | uma linha do CSV, como veio | nenhuma | 45.466 |
| `raw.links` | uma linha do CSV | nenhuma | 45.843 |
| `raw.avaliacoes` | uma linha do CSV | nenhuma | 100.004 |
| `refined.filmes` | um filme do TMDB | `filme_id` | 45.433 |
| `refined.links` | um cadastro do MovieLens | `filme_ml_id` | 45.843 |
| `refined.avaliacoes` | a nota de um usuário para um filme | `usuario_id, filme_ml_id` | 100.004 |
| `marts.retorno_por_ano` | um ano de lançamento | `ano` | 86 |
| `marts.top_lucro` | um filme, os 10 de maior lucro | `posicao` | 10 |
| `marts.nota_por_faixa_receita` | uma faixa de receita | `faixa` | 5 |

`filme_id` é sempre o id do TMDB, e `filme_ml_id` sempre o do MovieLens. São
numerações diferentes, e só `links` liga as duas. Atenção: 29 filmes do TMDB
têm dois cadastros no MovieLens, então `filmes ⋈ links` pelo `filme_id`
repete esses filmes.

## Como rodar do zero

Precisa do [uv](https://docs.astral.sh/uv/). Na raiz do projeto:

```
uv sync
uv run python -m pipeline.ingestao
uv run python -m pipeline.transformacao
uv run python -m pipeline.marts
```

Saída esperada do último comando:

```
✓ marts.retorno_por_ano          86 linhas
✓ marts.top_lucro                10 linhas
✓ marts.nota_por_faixa_receita    5 linhas
3 marts, 101 linhas.
```

Para explorar o banco no navegador (`localhost:4213`):
`uv run python ui.py`. Feche com Ctrl+C antes de rodar o pipeline: o arquivo
aceita um único processo escrevendo.

Testes (não abrem o banco nem os dados do projeto; usam dado inventado):

```
uv run pytest --cov
```

76 testes, 98,6% de coverage em `pipeline/`.

## Os indicadores

Todos os valores estão em dólares da época, sem correção de inflação.
Os marts 01 e 02 usam só filmes lançados com orçamento **e** receita de pelo
menos US$ 1 milhão: 4.631 filmes.

**01 · Retorno por ano** (`sql/marts/01_retorno_por_ano.sql`). Receita total
dividida pelo orçamento total de cada ano. Em 2015, 181 filmes renderam 3,65
vezes o que custaram; em 1997, 2,65 vezes. É razão de somas, não média das
razões: a média daria a um filme pequeno o mesmo peso de um blockbuster.

**02 · Top 10 de lucro** (`sql/marts/02_top_lucro.sql`). Receita menos
orçamento. Avatar (US$ 2,55 bi), Star Wars: The Force Awakens e Titanic
lideram.

**03 · Nota por faixa de receita** (`sql/marts/03_nota_por_faixa_receita.sql`).
Junta as notas do MovieLens à receita do TMDB passando por `links`. 9.025
filmes, 99.810 avaliações.

| Faixa de receita | Filmes | Nota média |
|---|---|---|
| sem receita informada | 4.288 | 3,37 |
| até US$ 10 mi | 1.246 | 3,37 |
| US$ 10 a 100 mi | 2.250 | 3,17 |
| US$ 100 mi a 1 bi | 1.216 | 3,15 |
| acima de US$ 1 bi | 25 | 3,49 |

Bilheteria maior não traz nota maior: a nota cai das faixas pequenas para
as médias e só sobe nos 25 filmes acima de US$ 1 bi.

## As decisões que mudam os números

Cada uma tem o motivo completo na spec da etapa.

- **Orçamento e receita iguais a 0 viram nulo** (`specs/transformacao.md`,
  item 7). No TMDB, 0 quer dizer "não informado": 36.553 filmes têm
  orçamento 0. Com eles, a média de orçamento cairia para um terço.
- **Orçamentos de US$ 1 a 999 ficam em refined, mas fora dos marts.** São
  244, provavelmente digitados em milhões. Refined não corrige fato; o filtro
  de US$ 1 milhão nos marts é a decisão, escrita no comentário de cada `.sql`.
- **13 filmes aparecem duas vezes com popularidade diferente.** Fica a linha
  com mais votos, a medição mais recente. O resto do conteúdo é idêntico.
- **`imdb_id` é texto.** 30.248 começam com zero (`0114709`); como número,
  perderiam o zero e deixariam de casar com o IMDB.
- **No mart 03, cada filme conta uma vez.** Primeiro a média das notas de
  cada filme, depois a média da faixa. A média direta das avaliações daria
  peso a quem tem mais notas: na faixa acima de US$ 1 bi, a nota subiria de
  3,49 para 3,76.

## Onde a IA errou, assumiu ou me corrigiu

Cada etapa terminou com a IA listando o que assumiu e não estava na spec.
Os casos que importaram, e como cada um foi descoberto:

1. **A minha spec estava errada, e a IA percebeu.** A spec da transformação
   dizia que as 3 linhas quebradas de `movies_metadata.csv` "não são filmes".
   Contando as linhas, a IA mostrou que são a segunda metade de 3 filmes
   (82663, 122662, 249260) cuja linha se partiu no CSV, e que a primeira
   metade ficava em refined sem título nem data. Corrigi o texto da spec.
   Nenhum indicador mudou, porque nenhum dos três tem orçamento nem receita.
2. **Um comentário meu contradizia o código.** O mart 02 dizia usar "o mesmo
   filtro do mart 01", mas não exige data de lançamento. A IA apontou isso
   ao escrever os testes, e se recusou a fixar a divergência num teste.
   Corrigi o comentário.
3. **O git ia alterar a camada bruta.** Ao versionar `raw/`, o git avisou que
   trocaria o fim de linha de `movies_metadata.csv`, que tem quebras de linha
   dentro das sinopses. Quem clonasse no Windows receberia um CSV diferente
   do original. O `.gitattributes` com `raw/** -text` impede isso.
4. **Coverage alto não provava nada sozinho.** Os testes chegaram a 98,6%,
   mas a IA quebrou 35 regras de propósito e duas passaram sem nenhum teste
   falhar: cópias exatas em `links` e `avaliacoes`, e a garantia de que o
   executor para *antes* de rodar SQL. Ganharam testes próprios.
5. **Suposições que ficaram registradas como limitação:**
   - a ingestão não é atômica: se um CSV vier corrompido, as tabelas
     anteriores já estarão gravadas;
   - o `read_csv` descarta linhas em branco por padrão, o que contraria a
     regra de não descartar nada em raw (hoje não há nenhuma);
   - o `CAST` arredonda em silêncio uma duração fracionária, e qualquer valor
     de `adult` diferente de `'True'` vira `False` (hoje não ocorre);
   - um `.sql` com dois comandos (`SELECT ...; DROP TABLE ...`) seria
     executado inteiro pelo executor de marts.
6. **O texto engana a ordenação.** Em `raw.avaliacoes`, o maior `timestamp`
   como texto é `999892199` (2001), não o mais recente (2016): em texto,
   `'9'` vem depois de `'1'`. Por isso a conversão de tipos acontece antes
   de qualquer conta.

## Estrutura

```
raw/             os três CSVs, como vieram do Kaggle
specs/           uma spec por etapa, fonte da verdade do código
pipeline/        db.py, ingestao.py, transformacao.py, marts.py
sql/marts/       um SELECT por indicador, com o grão na primeira linha
test/            testes unitários com pytest
ui.py            notebook SQL do DuckDB no navegador
```
