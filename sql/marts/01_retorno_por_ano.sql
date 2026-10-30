-- Quanto os filmes renderam, ano a ano, sobre o que custaram?
-- Grão: um ano de lançamento.
-- Entram só filmes lançados (status 'Released') com orçamento E receita de
-- pelo menos US$ 1 milhão. Motivo: abaixo disso estão os 244 orçamentos e
-- 154 receitas digitados em milhões (US$ 1, US$ 8...), que fariam o retorno
-- de um filme valer milhões de vezes. Nulo (0 no TMDB) também fica fora.
-- retorno = receita total / orçamento total do ano, não a média dos retornos
-- de cada filme: média de razões daria a um filme pequeno o mesmo peso de
-- um blockbuster.
SELECT
    year(data_lancamento)                     AS ano,
    count(*)                                  AS filmes,
    sum(orcamento)                            AS orcamento_total,
    sum(receita)                              AS receita_total,
    round(sum(receita) / sum(orcamento), 2)   AS retorno
FROM refined.filmes
WHERE status = 'Released'
  AND orcamento >= 1000000
  AND receita   >= 1000000
  AND data_lancamento IS NOT NULL
GROUP BY ano
ORDER BY ano
