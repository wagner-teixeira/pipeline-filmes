"""Abre a interface web do DuckDB sobre o filmes.duckdb.

Executar com: uv run python ui.py

Spec (specs/ingestao.md), e por que cada regra existe:

U1. Abre o filmes.duckdb da raiz, roda INSTALL ui; LOAD ui; CALL start_ui()
    (servidor em http://localhost:4213, abre o navegador).
U2. Fica de pé até Ctrl+C, imprimindo a URL e "Ctrl+C para encerrar"; no
    Ctrl+C fecha a conexão e sai sem traceback. Motivo: o arquivo aceita um
    único processo escrevendo; com o ui.py de pé, o pipeline dá erro de lock.
U3. Se filmes.duckdb não existir, diz para rodar a ingestão e sys.exit(1).
    Não usa conectar(), que criaria um banco vazio.
U4. Não importa pipeline/ingestao.py, e a ingestão não importa ui.py: são
    dois processos que disputam o mesmo arquivo, sem depender um do outro.
U5. stdout reconfigurado para utf-8, pelo mesmo motivo da ingestão: a
    codificação padrão do console do Windows pode não ser utf-8.
"""

import sys
import time

import duckdb

from pipeline.db import ARQUIVO_BANCO

URL = "http://localhost:4213"


def main():
    sys.stdout.reconfigure(encoding="utf-8")

    if not ARQUIVO_BANCO.exists():
        print(f"{ARQUIVO_BANCO} não existe. Rode a ingestão primeiro:")
        print("  uv run python -m pipeline.ingestao")
        sys.exit(1)

    con = duckdb.connect(ARQUIVO_BANCO)
    try:
        con.execute("INSTALL ui; LOAD ui; CALL start_ui();")
        print(URL)
        print("Ctrl+C para encerrar")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        con.close()


if __name__ == "__main__":
    main()
