-- Filme de bilheteria maior recebe nota maior dos usuários?
-- Grão: uma faixa de receita.
-- A nota é do MovieLens (avaliacoes) e a receita do TMDB (filmes): a ponte é
-- links, de filme_ml_id para filme_id.
-- Cada filme conta UMA vez, com a média das suas notas (CTE nota_filme).
-- Motivo: a média direta das avaliações daria peso a quem tem mais notas;
-- na faixa acima de 1 bi ela sobe de 3,49 para 3,76.
-- nota_filme agrupa por filme_id, não por filme_ml_id: 29 filmes do TMDB
-- têm dois cadastros no MovieLens, e cada um contaria duas vezes.
-- A coluna avaliacoes soma; a coluna filmes também (cada filme cai numa faixa).
WITH nota_filme AS (
    -- Grão: um filme do TMDB com pelo menos uma avaliação.
    SELECT
        l.filme_id,
        avg(a.nota) AS nota,
        count(*)    AS avaliacoes
    FROM refined.avaliacoes AS a
    JOIN refined.links      AS l ON l.filme_ml_id = a.filme_ml_id
    WHERE l.filme_id IS NOT NULL
    GROUP BY l.filme_id
),
filme_faixa AS (
    -- Grão: um filme avaliado que existe em refined.filmes.
    SELECT
        n.filme_id,
        n.nota,
        n.avaliacoes,
        CASE
            WHEN f.receita IS NULL         THEN '0 · sem receita informada'
            WHEN f.receita < 10000000      THEN '1 · até 10 mi'
            WHEN f.receita < 100000000     THEN '2 · 10 a 100 mi'
            WHEN f.receita < 1000000000    THEN '3 · 100 mi a 1 bi'
            ELSE                                '4 · acima de 1 bi'
        END AS faixa
    FROM nota_filme     AS n
    JOIN refined.filmes AS f ON f.filme_id = n.filme_id
)
SELECT
    faixa,
    count(*)              AS filmes,
    sum(avaliacoes)       AS avaliacoes,
    round(avg(nota), 2)   AS nota_media
FROM filme_faixa
GROUP BY faixa
ORDER BY faixa
