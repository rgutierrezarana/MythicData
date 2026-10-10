"""
DAG de Apache Airflow: Ingesta Continua de Precios Card Kingdom
1. Consulta periódica del catálogo público de precios de Card Kingdom (https://api.cardkingdom.com/api/v2/pricelist).
2. Procesa en streaming los precios de las cartas habilitadas en la base de datos PostgreSQL (is_streaming_enabled = TRUE).
3. Sin filtros por set: sincroniza directamente las cartas activas de la base de datos.
4. Realiza Upsert en PostgreSQL en las tablas 'card_current_prices', 'card_price_history' y 'cards'.
"""

import os
import sys
import logging
from datetime import datetime, timedelta
from pathlib import Path
from airflow import DAG
from airflow.models.param import Param
from airflow.operators.empty import EmptyOperator
from airflow.operators.python import PythonOperator

logger = logging.getLogger("airflow.task")

default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "start_date": datetime(2026, 1, 1),
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=2),
}

dag_name = Path(__file__).stem


def run_cardkingdom_sync(**context):
    """
    Tarea Python que ejecuta la captura y persistencia de precios
    para las cartas habilitadas en la base de datos.
    """
    sys.path.append("/opt/airflow")
    from backend.streaming.cardkingdom_streamer import CardKingdomPriceStreamer

    params = context.get("params", {})
    sync_all_db = bool(params.get("sync_all_database_cards", False))

    logger.info(f"Iniciando sincronización Card Kingdom (sync_all_db={sync_all_db})")

    # Si sync_all_db es True, desactiva stream_enabled_only para traer todas las cartas de la DB
    streamer = CardKingdomPriceStreamer(
        stream_enabled_only=not sync_all_db,
        auto_load_from_db=True
    )

    events = list(streamer.stream_price_events())
    logger.info(f"Eventos capturados: {len(events)}")

    persisted = streamer.persist_events_to_db(events)
    logger.info(f"Precios actualizados en base de datos: {persisted}")

    return {
        "status": "success",
        "events_count": len(events),
        "persisted_count": persisted
    }


with DAG(
    dag_id=dag_name,
    default_args=default_args,
    description="Sincronización continua de precios de Card Kingdom para cartas disponibles en la base de datos",
    schedule_interval="0 * * * *",  # Ejecución cada hora
    catchup=False,
    max_active_runs=1,
    params={
        "sync_all_database_cards": Param(
            default=False,
            type="boolean",
            title="¿Sincronizar TODAS las cartas de la base de datos?",
            description="Desmarcado: sincroniza solo las cartas con streaming habilitado en la DB. Marcado: sincroniza todo el catálogo de la DB.",
        ),
    },
    tags=["mtg", "cardkingdom", "streaming", "prices", "postgres"],
) as dag:

    start_task = EmptyOperator(task_id="start_sync")

    sync_prices_task = PythonOperator(
        task_id="fetch_and_persist_ck_prices",
        python_callable=run_cardkingdom_sync,
        provide_context=True,
    )

    end_task = EmptyOperator(task_id="end_sync")

    start_task >> sync_prices_task >> end_task
