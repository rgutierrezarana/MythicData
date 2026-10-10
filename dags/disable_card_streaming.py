"""
DAG de Apache Airflow: Deshabilitar Streaming de Precios Continuos (Basado en Cartas de la Base de Datos)
1. Lista únicamente las cartas que actualmente tienen 'is_streaming_enabled = TRUE' en la base de datos.
2. Permite deshabilitar cartas específicas por su UUID o apagar todo el streaming.
3. Sin filtros por set: opera directamente sobre las cartas activas de PostgreSQL.
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
    "retry_delay": timedelta(minutes=1),
}


def _get_active_cards_mapping() -> dict:
    """Carga directamente las cartas que actualmente tienen is_streaming_enabled = TRUE en la base de datos."""
    active_dict = {}
    try:
        import psycopg2
        default_host = "localhost" if os.name == "nt" else "postgres"
        host = os.getenv("POSTGRES_HOST", default_host)
        port = int(os.getenv("POSTGRES_PORT", "5432"))
        dbname = os.getenv("POSTGRES_DB_MTG", "mtg_dw")
        user = os.getenv("POSTGRES_USER", "airflow")
        password = os.getenv("POSTGRES_PASSWORD", "airflow")

        conn = psycopg2.connect(host=host, port=port, dbname=dbname, user=user, password=password, connect_timeout=3)
        with conn.cursor() as cur:
            cur.execute("""
                SELECT c.uuid, c.name, c.set_code, c.rarity, c.collector_number, c.streaming_enabled_at
                FROM cards c
                WHERE c.is_streaming_enabled = TRUE
                ORDER BY c.name ASC;
            """)
            for row in cur.fetchall():
                active_dict[row[0]] = f"🔴 [ACTIVO] {row[1]} ({row[2]}) [#{row[4] or ''}] • {row[3]}"
        conn.close()
    except Exception as e:
        logger.debug(f"Error consultando cartas activas: {e}")

    return active_dict


ACTIVE_CARDS = _get_active_cards_mapping()


def execute_disable_streaming(**context):
    """
    Lee los parámetros y actualiza is_streaming_enabled = FALSE en PostgreSQL.
    """
    sys.path.append("/opt/airflow")
    from backend.streaming.cardkingdom_streamer import disable_streaming_for_cards

    params = context.get("params", {})
    selected_uuids = params.get("card_uuids_to_disable", [])
    disable_all = bool(params.get("disable_all_streaming", False))
    manual_uuids_str = str(params.get("manual_card_uuids", "")).strip()

    target_uuids = []
    if isinstance(selected_uuids, list):
        target_uuids.extend([u.strip() for u in selected_uuids if u.strip()])
    elif isinstance(selected_uuids, str) and selected_uuids.strip():
        target_uuids.extend([u.strip() for u in selected_uuids.split(",") if u.strip()])

    if manual_uuids_str:
        target_uuids.extend([u.strip() for u in manual_uuids_str.split(",") if u.strip()])

    target_uuids = list(dict.fromkeys(target_uuids))

    if not disable_all and not target_uuids:
        raise ValueError("Debe seleccionar al menos una carta para deshabilitar o marcar '¿Deshabilitar TODO el streaming activo?'.")

    logger.info(f"Deshabilitando streaming: DisableAll={disable_all}, UUIDs={len(target_uuids)}")

    updated = disable_streaming_for_cards(
        card_uuids=target_uuids if target_uuids else None,
        disable_all=disable_all
    )

    logger.info(f"🛑 Éxito: Streaming deshabilitado para {updated} cartas en la base de datos.")
    context["ti"].xcom_push(key="disabled_count", value=updated)
    return {"status": "success", "disabled_count": updated}


dag_name = Path(__file__).stem

with DAG(
    dag_id=dag_name,
    default_args=default_args,
    description="Deshabilita el streaming continuo de precios para cartas activas en la base de datos",
    schedule_interval=None,  # Disparo manual bajo demanda
    catchup=False,
    max_active_runs=1,
    tags=["mtg", "streaming", "disable", "cardkingdom", "postgres"],
    params={
        "card_uuids_to_disable": Param(
            default=[],
            type="array",
            title="Cartas Activas a Deshabilitar",
            description="Seleccione las cartas activas de la base de datos cuyo streaming desea pausar/detener",
            values_display=ACTIVE_CARDS,
            examples=list(ACTIVE_CARDS.keys())[:10] if ACTIVE_CARDS else [],
        ),
        "disable_all_streaming": Param(
            default=False,
            type="boolean",
            title="¿Deshabilitar TODO el streaming activo?",
            description="Si es True, desactivará el streaming continuo para todas las cartas activas en la base de datos.",
        ),
        "manual_card_uuids": Param(
            default="",
            type="string",
            title="UUIDs manuales a deshabilitar (Opcional)",
            description="UUIDs separados por coma en caso de querer desactivar directamente por ID",
        ),
    },
) as dag:

    start_task = EmptyOperator(task_id="start_disable_flow")

    disable_cards_task = PythonOperator(
        task_id="disable_cards_in_database",
        python_callable=execute_disable_streaming,
        provide_context=True,
    )

    end_task = EmptyOperator(task_id="end_disable_flow")

    start_task >> disable_cards_task >> end_task
