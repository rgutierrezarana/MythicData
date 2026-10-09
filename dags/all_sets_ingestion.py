"""
DAG de Apache Airflow: Ingesta de Todos los Sets Disponibles (MTGJSON)
1. Descarga todos los sets disponibles desde la API v5 de MTGJSON.
2. Procesa y normaliza los sets con PySpark.
3. Guarda el catálogo completo en un archivo Parquet en el Data Lake.
4. Carga/Actualiza la tabla 'sets' en la base de datos PostgreSQL.
"""

import os
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.empty import EmptyOperator
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator

default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "start_date": datetime(2026, 1, 1),
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=3),
}
from pathlib import Path

dag_name = Path(__file__).stem

with DAG(
    dag_id=dag_name,
    default_args=default_args,
    description="Descarga y procesa todos los sets disponibles a Parquet y PostgreSQL",
    schedule_interval="@daily",  # Se ejecuta diariamente para descubrir nuevos sets
    catchup=False,
    max_active_runs=1,
    tags=["mtg", "pyspark", "sets", "parquet", "postgres"],
) as dag:

    start_task = EmptyOperator(task_id="start_pipeline")

    # Ejecuta el job de PySpark que descarga SetList.json.gz, genera Parquet y carga a Postgres
    spark_ingest_sets = BashOperator(
        task_id="spark_ingest_all_sets",
        bash_command=("python /opt/airflow/spark_jobs/process_sets.py"),
        env={**os.environ, "PYTHONPATH": "/opt/airflow:/opt/airflow/spark_jobs"},
    )

    end_task = EmptyOperator(task_id="end_pipeline")

    start_task >> spark_ingest_sets >> end_task
