"""
DAG de Apache Airflow: Pipeline de Machine Learning de Predicción de Precios (PySpark GBTRegressor)
1. Valida parámetros de ejecución (iteraciones, profundidad del árbol, límite opcional de cartas).
2. Ejecuta el job distribuido de Apache Spark MLlib (predict_card_prices.py).
3. Entrena el modelo GBTRegressor con lags temporales (t-1, t-3, t-7), medias móviles y volatilidad.
4. Genera inferencias de próximo precio (t+1) y actualiza la tabla 'card_price_predictions' en PostgreSQL.
5. Exporta el snapshot de predicciones a Parquet en el Data Lake y verifica resultados.
"""

import os
import sys
import logging
from pathlib import Path
from datetime import datetime, timedelta
from airflow import DAG
from airflow.models.param import Param
from airflow.operators.empty import EmptyOperator
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator

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


def validate_prediction_params(**context):
    """
    Valida y extrae los parámetros de configuración (conf o params de Airflow).
    """
    ti = context["ti"]
    dag_run = context.get("dag_run")
    conf = dag_run.conf if dag_run and dag_run.conf else {}

    max_cards = int(conf.get("max_cards", context["params"].get("max_cards", 0)))
    max_iter = int(conf.get("max_iter", context["params"].get("max_iter", 25)))
    max_depth = int(conf.get("max_depth", context["params"].get("max_depth", 5)))

    logger.info(f"Parámetros ML validados: max_cards={max_cards}, max_iter={max_iter}, max_depth={max_depth}")
    
    ti.xcom_push(key="max_cards", value=max_cards)
    ti.xcom_push(key="max_iter", value=max_iter)
    ti.xcom_push(key="max_depth", value=max_depth)


def execute_spark_gbt_job(**context):
    """
    Ejecuta el script PySpark MLlib predict_card_prices.py en el cluster Spark
    inyectando variables de entorno de observabilidad y trazabilidad Jaeger.
    """
    ti = context["ti"]
    max_cards = ti.xcom_pull(task_ids="validate_and_prepare_params", key="max_cards")
    max_iter = ti.xcom_pull(task_ids="validate_and_prepare_params", key="max_iter")
    max_depth = ti.xcom_pull(task_ids="validate_and_prepare_params", key="max_depth")

    jaeger_ui = os.getenv("JAEGER_UI_URL", "http://localhost:16686")
    logger.info(f"Observabilidad: Trazas distribuidas disponibles en Jaeger UI -> {jaeger_ui}")

    cmd = (
        f"python /opt/airflow/spark_jobs/predict_card_prices.py "
        f"--max-cards {max_cards} --max-iter {max_iter} --max-depth {max_depth}"
    )
    logger.info(f"Ejecutando comando PySpark GBTRegressor: {cmd}")

    ret_code = os.system(cmd)
    if ret_code != 0:
        raise RuntimeError(f"El job PySpark de predicción falló con código de salida: {ret_code}")


def verify_predictions_metrics(**context):
    """
    Verifica que las predicciones se hayan insertado correctamente en PostgreSQL
    e imprime estadísticas resumidas en los logs de Airflow.
    """
    import psycopg2

    db_host = os.getenv("POSTGRES_HOST", "postgres")
    db_port = int(os.getenv("POSTGRES_PORT", "5432"))
    db_name = os.getenv("POSTGRES_DB_MTG", "mtg_dw")
    db_user = os.getenv("POSTGRES_USER", "airflow")
    db_pass = os.getenv("POSTGRES_PASSWORD", "airflow")

    conn = psycopg2.connect(
        host=db_host,
        port=db_port,
        dbname=db_name,
        user=db_user,
        password=db_pass,
    )
    cur = conn.cursor()

    try:
        cur.execute("SELECT COUNT(*), AVG(confidence_score), AVG(expected_change_pct) FROM card_price_predictions;")
        total, avg_conf, avg_change = cur.fetchone()
        logger.info(
            f"✅ Verificación exitosa en PostgreSQL: {total} cartas con predicciones vigentes. "
            f"Confianza media: {float(avg_conf or 0):.1f}%, Variación media: {float(avg_change or 0):+.2f}%"
        )

        cur.execute("""
            SELECT c.name, p.current_price, p.predicted_next_price, p.expected_change_pct, p.direction
            FROM card_price_predictions p
            JOIN cards c ON p.card_uuid = c.uuid
            ORDER BY ABS(p.expected_change_pct) DESC
            LIMIT 5;
        """)
        top_movers = cur.fetchall()
        logger.info("Top 5 cartas con mayor proyección de cambio:")
        for r in top_movers:
            logger.info(f"  - {r[0]}: ${r[1]} -> ${r[2]} ({r[3]:+.2f}% {r[4]})")
    finally:
        cur.close()
        conn.close()


with DAG(
    dag_id=dag_name,
    default_args=default_args,
    description="Entrena el modelo PySpark MLlib GBTRegressor y calcula las predicciones de precios para MTG",
    schedule_interval=None,  # Disparo bajo demanda y tras ingestas de precios
    catchup=False,
    max_active_runs=1,
    tags=["mtg", "pyspark", "ml", "gbt", "predictions", "pricing", "postgres"],
    params={
        "max_cards": Param(
            default=0,
            type="integer",
            title="Límite de Cartas a Procesar (0 = Todas)",
            description="Número de cartas a procesar (utilizar 0 para entrenar y predecir sobre todo el catálogo)",
        ),
        "max_iter": Param(
            default=25,
            type="integer",
            title="Número de Iteraciones (Árboles GBT)",
            description="Cantidad máxima de árboles en el ensamble de boosting de Spark MLlib",
        ),
        "max_depth": Param(
            default=5,
            type="integer",
            title="Profundidad Máxima de Árboles",
            description="Profundidad máxima permitida por cada árbol de regresión",
        ),
    },
) as dag:

    start_task = EmptyOperator(task_id="start_pipeline")

    validate_params_task = PythonOperator(
        task_id="validate_and_prepare_params",
        python_callable=validate_prediction_params,
        provide_context=True,
    )

    spark_gbt_task = PythonOperator(
        task_id="spark_train_and_predict_gbt",
        python_callable=execute_spark_gbt_job,
        provide_context=True,
    )

    verify_task = PythonOperator(
        task_id="verify_predictions_in_db",
        python_callable=verify_predictions_metrics,
        provide_context=True,
    )

    end_task = EmptyOperator(task_id="end_pipeline")

    start_task >> validate_params_task >> spark_gbt_task >> verify_task >> end_task
