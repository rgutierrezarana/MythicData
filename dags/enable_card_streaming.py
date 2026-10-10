"""
DAG de Apache Airflow: Habilitar Streaming de Precios Continuos (Basado en Cartas de la Base de Datos)
1. Carga las cartas registradas en la base de datos PostgreSQL.
2. Permite seleccionar cartas individuales por su UUID o habilitar todas las cartas disponibles.
3. Sin filtros por set: opera directamente sobre el catálogo de cartas de la base de datos.
4. Actualiza 'is_streaming_enabled = TRUE' y dispara el worker de precios.
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
from airflow.operators.trigger_dagrun import TriggerDagRunOperator

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


def _get_cards_mapping() -> dict:
    """
    Carga directamente las cartas disponibles en la base de datos PostgreSQL
    para el selector de cartas por UUID (ordenadas alfabéticamente por nombre).
    """
    cards_dict = {}
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
                SELECT c.uuid, c.name, c.set_code, c.rarity, c.collector_number, c.is_streaming_enabled
                FROM cards c
                WHERE c.scryfall_id IS NOT NULL
                ORDER BY c.is_streaming_enabled DESC, c.name ASC
                LIMIT 2500;
            """)
            for row in cur.fetchall():
                status_icon = "🟢 [ACTIVO]" if row[5] else "⚪"
                cards_dict[row[0]] = f"{status_icon} {row[1]} ({row[2]}) [#{row[4] or ''}] • {row[3]}"
        conn.close()
    except Exception as e:
        logger.debug(f"Fallback para cartas: {e}")

    return cards_dict


AVAILABLE_CARDS = _get_cards_mapping()


def execute_enable_streaming(**context):
    """
    Habilita el streaming marcando is_streaming_enabled = TRUE para las cartas seleccionadas
    o para todas las cartas registradas en la base de datos.
    """
    sys.path.append("/opt/airflow")
    from backend.streaming.cardkingdom_streamer import enable_streaming_for_cards

    params = context.get("params", {})
    selected_uuids = params.get("selected_card_uuids", [])
    enable_all = bool(params.get("enable_all_available_cards", False))
    manual_uuids_str = str(params.get("manual_card_uuids", "")).strip()

    target_uuids = []
    if isinstance(selected_uuids, list):
        target_uuids.extend([u.strip() for u in selected_uuids if u.strip()])
    elif isinstance(selected_uuids, str) and selected_uuids.strip():
        target_uuids.extend([u.strip() for u in selected_uuids.split(",") if u.strip()])

    if manual_uuids_str:
        target_uuids.extend([u.strip() for u in manual_uuids_str.split(",") if u.strip()])

    target_uuids = list(dict.fromkeys(target_uuids))

    if not enable_all and not target_uuids:
        raise ValueError("Debe seleccionar al menos una carta o activar 'Habilitar TODAS las cartas disponibles'.")

    updated = 0
    if enable_all:
        import psycopg2
        default_host = "localhost" if os.name == "nt" else "postgres"
        host = os.getenv("POSTGRES_HOST", default_host)
        port = int(os.getenv("POSTGRES_PORT", "5432"))
        dbname = os.getenv("POSTGRES_DB_MTG", "mtg_dw")
        user = os.getenv("POSTGRES_USER", "airflow")
        password = os.getenv("POSTGRES_PASSWORD", "airflow")

        conn = psycopg2.connect(host=host, port=port, dbname=dbname, user=user, password=password)
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE cards
                SET is_streaming_enabled = TRUE,
                    streaming_enabled_at = NOW(),
                    updated_at = NOW()
                WHERE scryfall_id IS NOT NULL;
            """)
            updated = cur.rowcount
            conn.commit()
        conn.close()
        logger.info(f"✅ Se habilitó el streaming continuo para TODAS las cartas de la base de datos ({updated} cartas).")
    else:
        updated = enable_streaming_for_cards(card_uuids=target_uuids)
        logger.info(f"✅ Se habilitó el streaming continuo para {updated} cartas seleccionadas.")

    context["ti"].xcom_push(key="enabled_count", value=updated)
    return {"status": "success", "enabled_count": updated}


dag_name = Path(__file__).stem

with DAG(
    dag_id=dag_name,
    default_args=default_args,
    description="Habilita streaming continuo para cartas disponibles en la base de datos (por UUID)",
    schedule_interval=None,  # Disparo bajo demanda
    catchup=False,
    max_active_runs=1,
    tags=["mtg", "streaming", "enable", "cardkingdom", "postgres"],
    params={
        "selected_card_uuids": Param(
            default=[],
            type="array",
            title="Cartas a Habilitar (Búsqueda por Nombre / UUID en Base de Datos)",
            description="Escriba el nombre de la carta para encontrarla y seleccionarla directamente",
            values_display=AVAILABLE_CARDS,
            examples=list(AVAILABLE_CARDS.keys())[:10] if AVAILABLE_CARDS else [],
        ),
        "enable_all_available_cards": Param(
            default=False,
            type="boolean",
            title="¿Habilitar TODAS las cartas de la Base de Datos?",
            description="Si es True, activará el streaming de precios para todo el catálogo de cartas en PostgreSQL.",
        ),
        "manual_card_uuids": Param(
            default="",
            type="string",
            title="UUIDs manuales (Opcional - separados por comas)",
            description="Pegue UUIDs directamente en caso de requerirse",
        ),
        "trigger_immediate_sync": Param(
            default=True,
            type="boolean",
            title="¿Sincronizar precios de inmediato?",
            description="Si es True, disparará automáticamente el DAG de precios para obtener cotizaciones al instante.",
        ),
    },
) as dag:

    start_task = EmptyOperator(task_id="start_enable_flow")

    enable_cards_task = PythonOperator(
        task_id="enable_cards_in_database",
        python_callable=execute_enable_streaming,
        provide_context=True,
    )

    trigger_streamer_dag = TriggerDagRunOperator(
        task_id="trigger_price_streamer_sync",
        trigger_dag_id="cardkingdom_price_streamer",
        wait_for_completion=False,
        conf={"triggered_by": "enable_card_streaming"},
    )

    end_task = EmptyOperator(task_id="end_enable_flow")

    start_task >> enable_cards_task >> trigger_streamer_dag >> end_task
