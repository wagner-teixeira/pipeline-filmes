"""Ingestão dos CSVs de raw/ para o schema raw do filmes.duckdb.

Executar com: uv run python -m pipeline.ingestao

Spec (specs/ingestao.md), e por que cada regra existe:

1. Escopo e nomes
   Schema de destino: raw. Mapa arquivo -> tabela, completo e literal:
     movies_metadata.csv -> filmes
     links.csv           -> links
     ratings_small.csv   -> avaliacoes
   Ficam fora, de propósito, e não são lidos: credits.csv e keywords.csv
   (elenco e palavras-chave guardados como listas em texto, fora das
   perguntas do projeto) e ratings.csv (26 milhões de linhas, 710 MB: passa
   do limite de arquivo do GitHub; o ratings_small responde as mesmas
   perguntas).

2. Proibições
   Nenhuma conversão de tipo. Nenhuma linha descartada ou deduplicada.
   Nenhum nome de coluna alterado. Nenhum valor corrigido, preenchido ou
   normalizado. Motivo: a fronteira entre "o dado que chegou" e "o dado que
   eu decidi" fica na passagem de raw para refined. As linhas quebradas de
   movies_metadata.csv entram em raw como vieram.

3. Reexecução
   CREATE OR REPLACE, nunca acrescenta. Rodar dez vezes = rodar uma.

4. Leitura do arquivo
   pandas.read_csv com encoding="utf-8" declarado, dtype=str,
   keep_default_na=False e na_values=[""]: só o campo vazio vira nulo.
   Motivo: por padrão o pandas transforma em nulo textos como "NA", "null" e
   "None", e isso seria corrigir valor. O comportamento padrão de aspas é
   mantido porque movies_metadata.csv tem quebras de linha dentro do texto
   da sinopse.

5. Tipagem
   Toda coluna entra como texto. Motivo: em movies_metadata, budget, id e
   release_date têm valores que não são o que o nome promete (há linhas
   deslocadas); a conversão é decisão da etapa 2.

6. Saída na tela
   Uma linha por tabela, nome qualificado e contagem vinda do banco (não do
   DataFrame), milhar com ponto. Linha final com o total. stdout
   reconfigurado para utf-8, porque o console do Windows pode não ter como
   escrever o "✓" na codificação padrão.

7. Erro
   Antes de abrir o banco, verifica se os três arquivos existem em raw/.
   Faltando qualquer um: lista os que faltam, diz a pasta onde procurou e
   encerra com sys.exit(1), sem gravar nada. Verificar antes evita deixar uma
   carga pela metade.
"""

import sys

import pandas as pd

from pipeline.db import PASTA_RAW, conectar, criar_schema, gravar

SCHEMA = "raw"
ARQUIVOS = {
    "movies_metadata.csv": "filmes",
    "links.csv": "links",
    "ratings_small.csv": "avaliacoes",
}


def verificar_arquivos():
    faltando = [nome for nome in ARQUIVOS if not (PASTA_RAW / nome).is_file()]
    if faltando:
        print(f"Arquivos não encontrados em {PASTA_RAW}:")
        for nome in faltando:
            print(f"  {nome}")
        sys.exit(1)


def ler_csv(caminho):
    return pd.read_csv(
        caminho,
        encoding="utf-8",
        dtype=str,
        keep_default_na=False,
        na_values=[""],
    )


def formatar(numero):
    return f"{numero:,}".replace(",", ".")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    verificar_arquivos()

    con = conectar()
    try:
        criar_schema(con, SCHEMA)
        total = 0
        for arquivo, tabela in ARQUIVOS.items():
            linhas = gravar(con, ler_csv(PASTA_RAW / arquivo), SCHEMA, tabela)
            total += linhas
            print(f"✓ {f'{SCHEMA}.{tabela}':<20}{formatar(linhas):>9} linhas")
        print(f"Total: {formatar(total)} linhas")
    finally:
        con.close()


if __name__ == "__main__":
    main()
