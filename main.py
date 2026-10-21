"""Carga periódica da view dados_meta_dashboard (Cloud SQL / PostgreSQL) no BigQuery.

Cloud Function (2ª geração, gatilho HTTP) chamada pelo Cloud Scheduler a cada 15 minutos.
A cada execução lê a view inteira e substitui a tabela de destino (WRITE_TRUNCATE): o volume
é pequeno, a troca é atômica e a carga é idempotente.

Conexão com o banco:
  - na GCP: Cloud SQL Python Connector por IP privado (INSTANCE_CONNECTION_NAME);
  - local:  defina DB_HOST/DB_PORT para usar o túnel IAP (localhost:3308).
"""
import logging
import os
from datetime import datetime, timezone

import functions_framework
import pg8000.dbapi
from google.cloud import bigquery

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("carga_meta_dashboard")

SRC_VIEW = os.environ.get("SRC_VIEW", "sch_vendadiretaprd.dados_meta_dashboard")
BQ_TABLE = os.environ.get("BQ_TABLE", "volvo-iam.vendas.dados_meta_dashboard")
QUERY_TIMEOUT_MS = int(os.environ.get("QUERY_TIMEOUT_MS", "120000"))

COLUNAS = ["grupo", "dealer", "regional", "modelo", "ano", "mes", "meta", "faturados"]

SCHEMA = [
    bigquery.SchemaField("grupo", "STRING"),
    bigquery.SchemaField("dealer", "STRING"),
    bigquery.SchemaField("regional", "STRING"),
    bigquery.SchemaField("modelo", "STRING"),
    bigquery.SchemaField("ano", "INT64"),
    bigquery.SchemaField("mes", "INT64"),
    bigquery.SchemaField("meta", "INT64"),
    bigquery.SchemaField("faturados", "INT64"),
    bigquery.SchemaField("data_carga", "TIMESTAMP", description="Momento (UTC) da carga"),
]

_connector = None


def _connect():
    user, password = os.environ["DB_USER"], os.environ["DB_PASSWORD"]
    dbname = os.environ.get("DB_NAME", "dbvolvovendadireta")

    if os.environ.get("DB_HOST"):  # execução local, pelo túnel
        conn = pg8000.dbapi.connect(host=os.environ["DB_HOST"], port=int(os.environ.get("DB_PORT", "3308")),
                                    user=user, password=password, database=dbname, timeout=30)
    else:
        global _connector
        from google.cloud.sql.connector import Connector, IPTypes

        if _connector is None:
            _connector = Connector(ip_type=IPTypes.PRIVATE, refresh_strategy="lazy")
        conn = _connector.connect(os.environ["INSTANCE_CONNECTION_NAME"], "pg8000",
                                  user=user, password=password, db=dbname)

    cur = conn.cursor()
    cur.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
    cur.execute(f"SET statement_timeout = {QUERY_TIMEOUT_MS}")
    return conn


def extrair() -> list[dict]:
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT {', '.join(COLUNAS)} FROM {SRC_VIEW}")
        return [dict(zip(COLUNAS, linha)) for linha in cur.fetchall()]
    finally:
        conn.close()


def carregar(linhas: list[dict]) -> int:
    agora = datetime.now(timezone.utc).isoformat()
    for linha in linhas:
        linha["data_carga"] = agora

    client = bigquery.Client(project=BQ_TABLE.split(".")[0])
    # WRITE_TRUNCATE também substitui o schema (a tabela foi criada sem colunas)
    job_config = bigquery.LoadJobConfig(
        schema=SCHEMA,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        create_disposition=bigquery.CreateDisposition.CREATE_IF_NEEDED,
    )
    job = client.load_table_from_json(linhas, BQ_TABLE, job_config=job_config)
    job.result()
    return client.get_table(BQ_TABLE).num_rows


def executar() -> dict:
    linhas = extrair()
    log.info("lidas %d linhas de %s", len(linhas), SRC_VIEW)
    if not linhas:
        # view vazia quase sempre é falha a montante: não apaga o que já está no BigQuery
        raise RuntimeError(f"{SRC_VIEW} retornou 0 linhas; carga abortada")
    total = carregar(linhas)
    log.info("%s agora tem %d linhas", BQ_TABLE, total)
    return {"origem": SRC_VIEW, "destino": BQ_TABLE, "linhas": total}


@functions_framework.http
def carga_meta_dashboard(request):
    try:
        return executar(), 200
    except Exception as e:  # o Scheduler registra a falha e faz retry
        log.exception("falha na carga")
        return {"erro": str(e)}, 500


if __name__ == "__main__":
    print(executar())
