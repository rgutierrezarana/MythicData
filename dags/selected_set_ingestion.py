"""
DAG de Apache Airflow: Ingesta de Cartas y Precios por Set Seleccionado
1. Proporciona selector interactivo de Set(s) mediante Airflow Params.
2. Descarga todas las cartas y detalles de los sets seleccionados.
3. Descarga y cruza la estructura de precios (hoy o histórico de 90 días).
4. Genera exactamente 1 archivo Parquet por cada set en el Data Lake (data/lake/cards_prices/{SET_CODE}.parquet).
5. Inserta/Actualiza en PostgreSQL:
   - Tabla 'cards' (diferenciadas por UUID único de impresión física).
   - Tabla 'card_current_prices' (snapshot actual de mercado por tienda).
   - Tabla 'card_price_history' (histórico temporal para gráficas de variación).
"""

import os
import json
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
    "retry_delay": timedelta(minutes=3),
}
data_dir = os.getenv("DATA_DIR", "/opt/airflow/data")


def get_available_sets_mapping() -> dict:
    """
    Obtiene dinámicamente las columnas 'code' y 'name' de la tabla 'sets' en PostgreSQL
    para alimentar las opciones del selector de parámetros en la interfaz de Airflow.
    Incluye respaldos ante fallas (Data Lake Parquet y catálogo predeterminado).
    """
    sets_dict = {}

    # 1. Intentar consultar PostgreSQL (tabla 'sets' en mtg_dw)
    try:
        import psycopg2

        host = os.getenv("POSTGRES_HOST", "postgres")
        port = int(os.getenv("POSTGRES_PORT", "5432"))
        dbname = os.getenv("POSTGRES_DB_MTG", "mtg_dw")
        user = os.getenv("POSTGRES_USER", "airflow")
        password = os.getenv("POSTGRES_PASSWORD", "airflow")

        conn = psycopg2.connect(
            host=host,
            port=port,
            dbname=dbname,
            user=user,
            password=password,
            connect_timeout=3,
        )
        with conn.cursor() as cur:
            cur.execute(
                "SELECT code, name FROM sets ORDER BY release_date DESC NULLS LAST, name ASC"
            )
            rows = cur.fetchall()
            if rows:
                sets_dict = {row[0]: f"{row[0]} - {row[1]}" for row in rows}
        conn.close()
    except Exception as e:
        logger.debug(
            f"No se pudo consultar PostgreSQL para cargar opciones de sets: {e}"
        )

    # 2. Respaldo: Leer Parquet del Data Lake si PostgreSQL aún no tiene registros
    if not sets_dict:
        try:
            import pyarrow.parquet as pq

            parquet_path = os.path.join(
                os.getenv("DATA_DIR", "/opt/airflow/data"),
                "lake",
                "sets",
                "sets.parquet",
            )
            print(f"parquet path =  {parquet_path}")
            if os.path.exists(parquet_path):
                table = pq.read_table(parquet_path, columns=["code", "name"])
                df = table.to_pandas()
                sets_dict = {
                    row["code"]: f"{row['code']} - {row['name']}"
                    for _, row in df.iterrows()
                }
        except Exception as e:
            logger.debug(f"No se pudo leer Parquet para cargar opciones de sets: {e}")

    # 3. Respaldo predeterminado con sets principales si no hay datos disponibles
    if not sets_dict:
        sets_dict = {
            "MH3": "MH3 - Modern Horizons 3",
            "FDN": "FDN - Foundations",
            "BLB": "BLB - Bloomburrow",
            "OTJ": "OTJ - Outlaws of Thunder Junction",
            "MKM": "MKM - Murders at Karlov Manor",
            "LCI": "LCI - The Lost Caverns of Ixalan",
            "WOE": "WOE - Wilds of Eldraine",
            "ONE": "ONE - Phyrexia: All Will Be One",
            "BRO": "BRO - The Brothers' War",
            "DMU": "DMU - Dominaria United",
            "NEO": "NEO - Kamigawa: Neon Dynasty",
            "LEA": "LEA - Limited Edition Alpha",
        }

    return sets_dict


AVAILABLE_SETS = get_available_sets_mapping()


def _clean_code(val: str) -> str:
    """Extrae el código limpio de set (ej. 'MH3 - Modern Horizons 3' -> 'MH3')."""
    s = str(val).strip()
    if " - " in s:
        s = s.split(" - ")[0].strip()
    elif " (" in s:
        s = s.split(" (")[0].strip()
    return s.upper()


def parse_and_validate_params(**context):
    """
    Parsea los parámetros ingresados por el usuario desde la UI de Airflow.
    Soporta formato lista, string separado por comas o JSON array.
    """
    params = context.get("params", {})
    raw_sets = params.get("set_codes", ["MH3", "FDN"])
    load_history = bool(params.get("load_history", False))

    selected_sets = []
    if isinstance(raw_sets, list):
        for item in raw_sets:
            if isinstance(item, str):
                for part in item.split(","):
                    cleaned = _clean_code(part)
                    if cleaned:
                        selected_sets.append(cleaned)
    elif isinstance(raw_sets, str):
        raw_str = raw_sets.strip()
        if raw_str.startswith("[") and raw_str.endswith("]"):
            try:
                parsed_list = json.loads(raw_str)
                selected_sets = [_clean_code(s) for s in parsed_list if _clean_code(s)]
            except json.JSONDecodeError:
                selected_sets = [
                    _clean_code(s)
                    for s in raw_str.strip("[]")
                    .replace('"', "")
                    .replace("'", "")
                    .split(",")
                    if _clean_code(s)
                ]
        else:
            selected_sets = [
                _clean_code(s) for s in raw_str.split(",") if _clean_code(s)
            ]

    # Eliminar duplicados manteniendo orden
    unique_sets = list(dict.fromkeys(selected_sets))

    if not unique_sets:
        raise ValueError(
            "Debe especificar al menos un código de set válido (ej. MH3, FDN, BLB)."
        )

    logger.info(f"Sets seleccionados para procesar: {unique_sets}")
    logger.info(f"Modo histórico completo: {load_history}")

    # Pasar a XCom para la siguiente tarea
    context["ti"].xcom_push(key="processed_set_codes", value=unique_sets)
    context["ti"].xcom_push(key="load_history", value=load_history)
    return unique_sets


def execute_spark_job_for_sets(**context):
    """
    Invoca el script PySpark pasando los sets validados.
    """
    ti = context["ti"]
    set_codes = ti.xcom_pull(
        task_ids="validate_selected_sets", key="processed_set_codes"
    )
    load_history = ti.xcom_pull(task_ids="validate_selected_sets", key="load_history")

    if not set_codes:
        raise ValueError("No se recibieron códigos de sets válidos desde XCom.")

    sets_arg = ",".join(set_codes)
    history_flag = "--history" if load_history else ""

    jaeger_ui = os.getenv("JAEGER_UI_URL", "http://localhost:16686")
    logger.info(
        f"Observabilidad: Trazas y métricas disponibles en Jaeger UI -> {jaeger_ui}"
    )
    cmd = f"python /opt/airflow/spark_jobs/process_cards_and_prices.py --sets '{sets_arg}' {history_flag}"
    logger.info(f"Ejecutando comando PySpark con soporte OpenTracing / Jaeger: {cmd}")

    ret_code = os.system(cmd)
    if ret_code != 0:
        raise RuntimeError(f"El job de PySpark falló con código de salida: {ret_code}")


def execute_spark_prediction_job(**context):
    """
    Ejecuta el pipeline de Machine Learning PySpark GBTRegressor para proyectar el próximo precio de las cartas.
    """
    cmd = "python /opt/airflow/spark_jobs/predict_card_prices.py --max-iter 25 --max-depth 5"
    logger.info(f"Ejecutando pipeline ML PySpark GBTRegressor: {cmd}")
    ret_code = os.system(cmd)
    if ret_code != 0:
        logger.warning(f"El job de predicción GBTRegressor retornó código {ret_code}, continuando...")


dag_name = Path(__file__).stem

with DAG(
    dag_id=dag_name,
    default_args=default_args,
    description=f"Descarga cartas y estructura de precios de sets seleccionados con PySpark [{data_dir}]",
    schedule_interval=None,  # Disparo bajo demanda con selector de parámetros
    catchup=False,
    max_active_runs=1,
    tags=["mtg", "pyspark", "cards", "pricing", "parquet", "postgres", "ml", "gbt"],
    params={
        "set_codes": Param(
            default=[],
            type="array",
            title="Seleccionar Set(s) a Ingerir",
            description="Seleccione uno o más sets disponibles en el catálogo (código y nombre)",
            values_display=AVAILABLE_SETS,
            examples=list(AVAILABLE_SETS.keys()),
        ),
        "load_history": Param(
            default=False,
            type="boolean",
            title="¿Incluir Histórico de Precios de 90 Días?",
            description="Activar para extraer los últimos 90 días (AllPrices.json.gz). Desactivar para obtener snapshot de hoy (AllPricesToday.json.gz).",
        ),
    },
) as dag:

    start_task = EmptyOperator(task_id="start_pipeline")

    # 1. Valida y procesa la selección de sets del usuario
    validate_params_task = PythonOperator(
        task_id="validate_selected_sets",
        python_callable=parse_and_validate_params,
        provide_context=True,
    )

    # 2. Ejecuta el Job PySpark para descargar cartas, cruzar precios, generar 1 parquet por set y cargar en Postgres
    spark_process_cards_task = PythonOperator(
        task_id="spark_ingest_cards_and_prices",
        python_callable=execute_spark_job_for_sets,
        provide_context=True,
    )

    # 3. Entrena el modelo GBTRegressor y genera predicciones de próximo precio
    spark_predict_prices_task = PythonOperator(
        task_id="spark_predict_prices_gbt",
        python_callable=execute_spark_prediction_job,
        provide_context=True,
    )

    end_task = EmptyOperator(task_id="end_pipeline")

    start_task >> validate_params_task >> spark_process_cards_task >> spark_predict_prices_task >> end_task

