-- Quais filmes deram mais lucro?
-- Grão: um filme, os 10 de maior lucro.
-- lucro = receita - orçamento, em dólares da época (sem correção de inflação).
-- Mesmo filtro do mart 01: lançado, orçamento e receita de pelo menos US$ 1 mi.
-- filme_id desempata lucros iguais: sem ele, a ordem pode mudar entre execuções.
SELECT
    row_number() OVER (ORDER BY receita - orcamento DESC, filme_id) AS posicao,
    filme_id,
    titulo,
    year(data_lancamento)                   AS ano,
    orcamento,
    receita,
    receita - orcamento                     AS lucro,
    round(receita / orcamento, 2)           AS retorno
FROM refined.filmes
WHERE status = 'Released'
  AND orcamento >= 1000000
  AND receita   >= 1000000
ORDER BY posicao
LIMIT 10
