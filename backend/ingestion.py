"""
Módulo de Integración para Ingesta de Datos, Pipelines de Apache Airflow y Trazas Jaeger.
Gestiona el disparo de DAGs, cálculo de progreso en tiempo real, extracción de logs y observabilidad.
"""

import os
import re
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import requests
from sqlalchemy.orm import Session
from sqlalchemy import text

from backend.config import settings
from backend import schemas

logger = logging.getLogger("MTGIngestionService")

AIRFLOW_AUTH = (settings.AIRFLOW_USER, settings.AIRFLOW_PASSWORD)
TIMEOUT = 6


def _check_airflow_connection() -> bool:
    """Verifica si el servidor web de Airflow responde."""
    try:
        url = f"{settings.AIRFLOW_API_URL}/health"
        r = requests.get(url, timeout=3)
        return r.status_code == 200
    except Exception:
        # Intento fallback con endpoint de dags
        try:
            r = requests.get(f"{settings.AIRFLOW_API_URL}/dags?limit=1", auth=AIRFLOW_AUTH, timeout=3)
            return r.status_code == 200
        except Exception:
            return False


def _check_jaeger_connection() -> bool:
    """Verifica si Jaeger API responde."""
    try:
        url = f"{settings.JAEGER_API_URL}/services"
        r = requests.get(url, timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def get_available_sets_for_ingestion(db: Session) -> List[Dict[str, str]]:
    """
    Obtiene la lista de sets disponibles en PostgreSQL (o fallback local)
    para el selector de la interfaz de usuario.
    """
    try:
        result = db.execute(
            text("SELECT code, name FROM sets ORDER BY release_date DESC NULLS LAST, name ASC")
        ).fetchall()
        if result:
            return [{"code": r[0], "name": r[1] or r[0]} for r in result]
    except Exception as e:
        logger.warning(f"Error consultando sets en BD: {e}")

    # Fallback si PostgreSQL aún no tiene la tabla poblada
    return [
        {"code": "MH3", "name": "Modern Horizons 3"},
        {"code": "FDN", "name": "Foundations"},
        {"code": "BLB", "name": "Bloomburrow"},
        {"code": "OTJ", "name": "Outlaws of Thunder Junction"},
        {"code": "MKM", "name": "Murders at Karlov Manor"},
        {"code": "LCI", "name": "The Lost Caverns of Ixalan"},
        {"code": "WOE", "name": "Wilds of Eldraine"},
        {"code": "ONE", "name": "Phyrexia: All Will Be One"},
        {"code": "BRO", "name": "The Brothers' War"},
        {"code": "DMU", "name": "Dominaria United"},
        {"code": "NEO", "name": "Kamigawa: Neon Dynasty"},
        {"code": "LEA", "name": "Limited Edition Alpha"},
    ]


def get_ingestion_config(db: Session) -> schemas.IngestionConfigResponse:
    """Retorna la configuración, sets disponibles y estado de Airflow y Jaeger."""
    available_dags = [
        {
            "dag_id": "selected_set_ingestion",
            "name": "Cartas y Precios por Set Seleccionado (PySpark)",
            "description": "Descarga cartas, precios de mercado multitienda, genera 1 Parquet por set y actualiza tablas en PostgreSQL.",
            "supports_sets": True,
            "supports_history": True,
        },
        {
            "dag_id": "all_sets_ingestion",
            "name": "Catálogo Completo de Sets (MTGJSON)",
            "description": "Descarga y procesa todos los sets disponibles en MTGJSON a Parquet y PostgreSQL.",
            "supports_sets": False,
            "supports_history": False,
        },
        {
            "dag_id": "price_prediction_pipeline",
            "name": "Predicción de Precios ML (GBTRegressor PySpark)",
            "description": "Entrena el modelo de Machine Learning distribuido y calcula el próximo precio estimado (t+1) para las cartas.",
            "supports_sets": False,
            "supports_history": False,
        },
    ]

    sets = get_available_sets_for_ingestion(db)
    af_ok = _check_airflow_connection()
    jg_ok = _check_jaeger_connection()

    return schemas.IngestionConfigResponse(
        available_dags=available_dags,
        available_sets=sets,
        airflow_connected=af_ok,
        jaeger_connected=jg_ok,
        airflow_web_url=settings.AIRFLOW_WEB_URL,
        jaeger_ui_url=settings.JAEGER_UI_URL,
    )


def trigger_dag_run(req: schemas.IngestionTriggerRequest) -> schemas.IngestionTriggerResponse:
    """
    Desencadena una ejecución manual de un DAG en Apache Airflow mediante su REST API v1.
    """
    dag_id = req.dag_id or "selected_set_ingestion"
    url = f"{settings.AIRFLOW_API_URL}/dags/{dag_id}/dagRuns"

    conf: Dict[str, Any] = {}
    if dag_id == "selected_set_ingestion":
        cleaned_sets = [s.strip().upper() for s in req.set_codes if s.strip()]
        if not cleaned_sets:
            cleaned_sets = ["MH3", "FDN"]
        conf = {
            "set_codes": cleaned_sets,
            "load_history": bool(req.load_history)
        }
    elif dag_id == "price_prediction_pipeline":
        conf = {
            "max_cards": 0,
            "max_iter": 25,
            "max_depth": 5
        }
    else:
        conf = {}

    payload = {"conf": conf}

    try:
        # Asegurar que el DAG no esté pausado
        requests.patch(
            f"{settings.AIRFLOW_API_URL}/dags/{dag_id}",
            json={"is_paused": False},
            auth=AIRFLOW_AUTH,
            timeout=TIMEOUT
        )

        resp = requests.post(url, json=payload, auth=AIRFLOW_AUTH, timeout=TIMEOUT)
        if resp.status_code not in (200, 201):
            error_msg = f"Airflow retornó status {resp.status_code}: {resp.text}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        data = resp.json()
        dag_run_id = data.get("dag_run_id", "")
        state = data.get("state", "queued")
        logical_date = data.get("logical_date")

        airflow_run_url = f"{settings.AIRFLOW_WEB_URL}/dags/{dag_id}/grid?dag_run_id={dag_run_id}"

        return schemas.IngestionTriggerResponse(
            dag_id=dag_id,
            dag_run_id=dag_run_id,
            state=state,
            logical_date=str(logical_date) if logical_date else None,
            conf=conf,
            message=f"Pipeline '{dag_id}' iniciado correctamente en Airflow.",
            airflow_url=airflow_run_url,
        )
    except Exception as e:
        logger.error(f"Fallo al contactar Airflow API para trigger: {e}")
        raise RuntimeError(f"No se pudo iniciar el job en Airflow: {str(e)}")


def _extract_trace_id_from_text(text_content: str) -> Optional[str]:
    """Extrae el traceID de Jaeger buscando URLs o patrones de 32 chars hex."""
    if not text_content:
        return None
    # Buscar formato 'trace/<hex_id>'
    match = re.search(r"trace/([a-f0-9]{32})", text_content, re.IGNORECASE)
    if match:
        return match.group(1)
    # Buscar formato 'TraceID: <hex_id>'
    match2 = re.search(r"trace[_\s]?id[:=]\s*([a-f0-9]{32})", text_content, re.IGNORECASE)
    if match2:
        return match2.group(1)
    return None


def get_dag_run_status(dag_id: str, dag_run_id: str) -> schemas.IngestionStatusResponse:
    """
    Obtiene el estado detallado de una ejecución de DAG, sus tareas,
    calcula el porcentaje de progreso dinámico y extrae el traceID de Jaeger.
    """
    url_dag_run = f"{settings.AIRFLOW_API_URL}/dags/{dag_id}/dagRuns/{dag_run_id}"
    url_tasks = f"{settings.AIRFLOW_API_URL}/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances"

    airflow_url = f"{settings.AIRFLOW_WEB_URL}/dags/{dag_id}/grid?dag_run_id={dag_run_id}"
    jaeger_url = f"{settings.JAEGER_UI_URL}/search?service=mtg-spark-pipeline"

    try:
        r_run = requests.get(url_dag_run, auth=AIRFLOW_AUTH, timeout=TIMEOUT)
        if r_run.status_code != 200:
            raise RuntimeError(f"DAG Run '{dag_run_id}' no encontrado en Airflow ({r_run.status_code})")
        run_data = r_run.json()

        dag_state = run_data.get("state", "queued")
        conf = run_data.get("conf", {})
        start_date = run_data.get("start_date")
        end_date = run_data.get("end_date")
        execution_date = run_data.get("execution_date")

        # Obtener instancias de tareas
        task_items: List[schemas.TaskInstanceItem] = []
        task_dict: Dict[str, Dict[str, Any]] = {}
        r_tasks = requests.get(url_tasks, auth=AIRFLOW_AUTH, timeout=TIMEOUT)
        if r_tasks.status_code == 200:
            tasks_data = r_tasks.json().get("task_instances", [])
            for t in tasks_data:
                tid = t.get("task_id", "")
                tstate = t.get("state")
                task_dict[tid] = t
                task_items.append(
                    schemas.TaskInstanceItem(
                        task_id=tid,
                        state=tstate,
                        duration=t.get("duration"),
                        start_date=t.get("start_date"),
                        end_date=t.get("end_date"),
                        try_number=t.get("try_number", 1),
                    )
                )

        # Cálculo dinámico de porcentaje y descripción del paso actual
        progress = 0
        step_description = "En cola para ejecución..."
        detected_trace_id: Optional[str] = None

        if dag_state == "success":
            progress = 100
            step_description = "Ingesta completada exitosamente. Datos sincronizados en PostgreSQL y Data Lake."
        elif dag_state == "failed":
            progress = 90
            step_description = "Fallo en la ejecución del pipeline. Revise los logs de Airflow."
        else:
            # dag_state is 'running' or 'queued'
            if dag_id == "selected_set_ingestion":
                start_ti = task_dict.get("start_pipeline", {})
                validate_ti = task_dict.get("validate_selected_sets", {})
                spark_ti = task_dict.get("spark_ingest_cards_and_prices", {})
                end_ti = task_dict.get("end_pipeline", {})

                if end_ti.get("state") == "success":
                    progress = 100
                    step_description = "Ingesta completada exitosamente."
                elif spark_ti.get("state") == "success":
                    progress = 95
                    step_description = "Finalizando pipeline y registrando métricas..."
                elif spark_ti.get("state") == "running":
                    # Intentar leer los logs de la tarea para saber el punto exacto
                    try_num = spark_ti.get("try_number", 1)
                    log_text = _fetch_task_log(dag_id, dag_run_id, "spark_ingest_cards_and_prices", try_num)
                    detected_trace_id = _extract_trace_id_from_text(log_text)

                    # Estimar progreso analizando los logs generados por PySpark
                    if "=== PIPELINE DE INGESTA FINALIZADO CON ÉXITO ===" in log_text:
                        progress = 92
                        step_description = "PySpark: Finalizando carga en PostgreSQL..."
                    elif "Cargando en base de datos PostgreSQL" in log_text or "upsert" in log_text.lower():
                        progress = 80
                        step_description = "PostgreSQL: Insertando y actualizando tablas de cartas y precios..."
                    elif "Guardando archivo Parquet" in log_text or "parquet" in log_text.lower():
                        progress = 65
                        step_description = "Data Lake: Generando archivos Parquet por Set..."
                    elif "Descargando estructura de precios" in log_text or "AllPrices" in log_text:
                        progress = 45
                        step_description = "MTGJSON: Extrayendo y cruzando cotizaciones de mercado..."
                    elif "Descargando cartas del set" in log_text:
                        progress = 30
                        step_description = "PySpark: Descargando catálogo de cartas seleccionadas..."
                    elif "INICIANDO PIPELINE" in log_text:
                        progress = 25
                        step_description = "Iniciando Job PySpark y Spark Session..."
                    else:
                        # Si no hay log todavía o está iniciando
                        progress = 20
                        step_description = "Job PySpark en ejecución..."
                elif validate_ti.get("state") == "success":
                    progress = 15
                    step_description = "Sets validados. Esperando inicio de worker Spark..."
                elif validate_ti.get("state") == "running":
                    progress = 8
                    step_description = "Validando parámetros de sets y configuración..."
                elif start_ti.get("state") in ("success", "running"):
                    progress = 5
                    step_description = "Pipeline iniciado..."
                else:
                    progress = 2
                    step_description = "En cola de Airflow..."

            elif dag_id == "all_sets_ingestion":
                spark_sets_ti = task_dict.get("spark_ingest_all_sets", {})
                if spark_sets_ti.get("state") == "success":
                    progress = 95
                    step_description = "Carga de catálogo completada."
                elif spark_sets_ti.get("state") == "running":
                    try_num = spark_sets_ti.get("try_number", 1)
                    log_text = _fetch_task_log(dag_id, dag_run_id, "spark_ingest_all_sets", try_num)
                    detected_trace_id = _extract_trace_id_from_text(log_text)

                    if "PIPELINE DE SETS FINALIZADO" in log_text:
                        progress = 90
                        step_description = "Sets cargados en PostgreSQL..."
                    elif "Guardando" in log_text and "Parquet" in log_text:
                        progress = 65
                        step_description = "Generando Parquet de sets..."
                    elif "Total de sets recibidos" in log_text:
                        progress = 40
                        step_description = "Procesando sets recibidos de MTGJSON..."
                    else:
                        progress = 20
                        step_description = "Descargando listado de sets..."
                else:
                    progress = 5
                    step_description = "Iniciando pipeline de sets..."

            elif dag_id == "price_prediction_pipeline":
                verify_ti = task_dict.get("verify_predictions_in_db", {})
                spark_pred_ti = task_dict.get("spark_train_and_predict_gbt", {})
                val_ti = task_dict.get("validate_and_prepare_params", {})

                if verify_ti.get("state") == "success":
                    progress = 100
                    step_description = "Pipeline de ML completado. Predicciones actualizadas en PostgreSQL."
                elif verify_ti.get("state") == "running":
                    progress = 92
                    step_description = "Verificando métricas de predicción en base de datos..."
                elif spark_pred_ti.get("state") == "success":
                    progress = 88
                    step_description = "Modelo GBTRegressor entrenado e inferencias generadas."
                elif spark_pred_ti.get("state") == "running":
                    try_num = spark_pred_ti.get("try_number", 1)
                    log_text = _fetch_task_log(dag_id, dag_run_id, "spark_train_and_predict_gbt", try_num)
                    detected_trace_id = _extract_trace_id_from_text(log_text)

                    if "Guardando snapshot Parquet" in log_text or "Guardando predicciones" in log_text:
                        progress = 80
                        step_description = "Guardando predicciones en PostgreSQL y Data Lake Parquet..."
                    elif "Generando inferencias" in log_text:
                        progress = 65
                        step_description = "Generando predicciones de próximo precio (t+1)..."
                    elif "Entrenando modelo PySpark GBTRegressor" in log_text:
                        progress = 45
                        step_description = "Entrenando ensamble GBTRegressor distribuido en PySpark..."
                    elif "Construyendo variables predictivas" in log_text:
                        progress = 30
                        step_description = "Ingeniería de atributos: calculando lags temporales, medias móviles y volatilidad..."
                    elif "Cargando series históricas" in log_text:
                        progress = 18
                        step_description = "Extrayendo historial de precios desde PostgreSQL DW..."
                    else:
                        progress = 12
                        step_description = "Iniciando Spark Session y preparando datos ML..."
                elif val_ti.get("state") == "success":
                    progress = 10
                    step_description = "Parámetros ML validados. Iniciando worker Spark..."
                else:
                    progress = 5
                    step_description = "Iniciando pipeline de predicción de precios..."

        # Si encontramos trace_id, armar URL directa
        if detected_trace_id:
            jaeger_url = f"{settings.JAEGER_UI_URL}/trace/{detected_trace_id}"
        else:
            # Intentar consultar última traza en Jaeger si el DAG ya corrió
            latest_trace = _get_latest_jaeger_trace_id()
            if latest_trace:
                detected_trace_id = latest_trace
                jaeger_url = f"{settings.JAEGER_UI_URL}/trace/{latest_trace}"

        return schemas.IngestionStatusResponse(
            dag_id=dag_id,
            dag_run_id=dag_run_id,
            state=dag_state,
            progress_percent=progress,
            current_step=step_description,
            start_date=str(start_date) if start_date else None,
            end_date=str(end_date) if end_date else None,
            execution_date=str(execution_date) if execution_date else None,
            conf=conf,
            tasks=task_items,
            airflow_url=airflow_url,
            jaeger_url=jaeger_url,
            latest_trace_id=detected_trace_id,
        )

    except Exception as e:
        logger.error(f"Error consultando estado de DAG '{dag_id}/{dag_run_id}': {e}")
        return schemas.IngestionStatusResponse(
            dag_id=dag_id,
            dag_run_id=dag_run_id,
            state="unknown",
            progress_percent=0,
            current_step=f"No se pudo consultar el estado: {str(e)}",
            airflow_url=airflow_url,
            jaeger_url=jaeger_url,
        )


def _fetch_task_log(dag_id: str, dag_run_id: str, task_id: str, try_number: int = 1) -> str:
    """Obtiene los logs de una tarea desde Airflow REST API o desde el disco montado."""
    # 1. Intento por Airflow REST API
    url = f"{settings.AIRFLOW_API_URL}/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances/{task_id}/logs/{try_number}"
    try:
        r = requests.get(url, auth=AIRFLOW_AUTH, timeout=4)
        if r.status_code == 200 and r.text.strip():
            return r.text
    except Exception:
        pass

    # 2. Respaldo por sistema de archivos montado en /opt/airflow/logs
    try:
        # Formato Airflow 2.x: /opt/airflow/logs/dag_id=.../run_id=.../task_id=.../attempt=1.log
        expected_path = os.path.join(
            settings.AIRFLOW_LOGS_DIR,
            f"dag_id={dag_id}",
            f"run_id={dag_run_id}",
            f"task_id={task_id}",
            f"attempt={try_number}.log"
        )
        if os.path.exists(expected_path):
            with open(expected_path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
    except Exception as e:
        logger.debug(f"No se pudo leer log desde disco: {e}")

    return ""


def get_dag_run_logs(dag_id: str, dag_run_id: str, task_id: Optional[str] = None) -> schemas.IngestionLogResponse:
    """
    Retorna el contenido de log acumulado para una tarea específica o la tarea principal de Spark.
    """
    target_task = task_id
    if not target_task:
        if dag_id == "selected_set_ingestion":
            target_task = "spark_ingest_cards_and_prices"
        elif dag_id == "price_prediction_pipeline":
            target_task = "spark_train_and_predict_gbt"
        else:
            target_task = "spark_ingest_all_sets"

    log_content = _fetch_task_log(dag_id, dag_run_id, target_task, 1)
    if not log_content and target_task != "validate_selected_sets" and dag_id == "selected_set_ingestion":
        # Si spark aún no tiene logs, mostrar logs de validación
        val_log = _fetch_task_log(dag_id, dag_run_id, "validate_selected_sets", 1)
        if val_log:
            log_content = val_log
            target_task = "validate_selected_sets"
    elif not log_content and dag_id == "price_prediction_pipeline":
        val_log = _fetch_task_log(dag_id, dag_run_id, "validate_and_prepare_params", 1)
        if val_log:
            log_content = val_log
            target_task = "validate_and_prepare_params"

    trace_id = _extract_trace_id_from_text(log_content)
    trace_url = f"{settings.JAEGER_UI_URL}/trace/{trace_id}" if trace_id else None

    if not log_content:
        log_content = "Esperando salida de log de Airflow... La tarea puede estar en cola o iniciando."

    return schemas.IngestionLogResponse(
        dag_id=dag_id,
        dag_run_id=dag_run_id,
        task_id=target_task,
        log=log_content,
        jaeger_trace_id=trace_id,
        jaeger_trace_url=trace_url,
    )


def get_ingestion_history(limit: int = 15) -> schemas.IngestionHistoryResponse:
    """
    Obtiene el historial de ejecuciones recientes de DAGs de ingesta en Airflow.
    """
    all_runs: List[schemas.IngestionHistoryItem] = []

    for dag_id in ["selected_set_ingestion", "all_sets_ingestion", "price_prediction_pipeline"]:
        url = f"{settings.AIRFLOW_API_URL}/dags/{dag_id}/dagRuns?order_by=-execution_date&limit={limit}"
        try:
            r = requests.get(url, auth=AIRFLOW_AUTH, timeout=TIMEOUT)
            if r.status_code == 200:
                data = r.json().get("dag_runs", [])
                for d in data:
                    state = d.get("state", "unknown")
                    progress = 100 if state == "success" else (50 if state == "running" else 0)
                    dag_run_id = d.get("dag_run_id", "")
                    airflow_url = f"{settings.AIRFLOW_WEB_URL}/dags/{dag_id}/grid?dag_run_id={dag_run_id}"

                    all_runs.append(
                        schemas.IngestionHistoryItem(
                            dag_id=dag_id,
                            dag_run_id=dag_run_id,
                            state=state,
                            progress_percent=progress,
                            start_date=d.get("start_date"),
                            end_date=d.get("end_date"),
                            conf=d.get("conf", {}),
                            run_type=d.get("run_type"),
                            airflow_url=airflow_url,
                            jaeger_url=f"{settings.JAEGER_UI_URL}/search?service=mtg-spark-pipeline",
                        )
                    )
        except Exception as e:
            logger.warning(f"Error listando historial para DAG {dag_id}: {e}")

    # Ordenar por start_date o fecha descendente
    all_runs.sort(key=lambda x: x.start_date or "", reverse=True)

    return schemas.IngestionHistoryResponse(
        runs=all_runs[:limit],
        total=len(all_runs)
    )


def _get_latest_jaeger_trace_id() -> Optional[str]:
    """Consulta la traza más reciente registrada en Jaeger para mtg-spark-pipeline."""
    try:
        url = f"{settings.JAEGER_API_URL}/traces?service=mtg-spark-pipeline&limit=1"
        r = requests.get(url, timeout=3)
        if r.status_code == 200:
            traces = r.json().get("data", [])
            if traces and len(traces) > 0:
                return traces[0].get("traceID")
    except Exception:
        pass
    return None


def get_jaeger_traces(limit: int = 10) -> schemas.JaegerTracesResponse:
    """
    Obtiene las últimas trazas distribuidas registradas en Jaeger.
    """
    traces_list: List[schemas.JaegerTraceSummary] = []
    try:
        url = f"{settings.JAEGER_API_URL}/traces?service=mtg-spark-pipeline&limit={limit}"
        r = requests.get(url, timeout=TIMEOUT)
        if r.status_code == 200:
            data = r.json().get("data", [])
            for item in data:
                tid = item.get("traceID", "")
                spans = item.get("spans", [])
                root_span = spans[0] if spans else {}
                op_name = root_span.get("operationName", "spark.pipeline")
                duration_ms = (root_span.get("duration", 0)) / 1000.0
                start_us = root_span.get("startTime", 0)
                start_iso = datetime.fromtimestamp(start_us / 1000000.0, tz=timezone.utc).isoformat() if start_us else ""

                traces_list.append(
                    schemas.JaegerTraceSummary(
                        trace_id=tid,
                        operation_name=op_name,
                        duration_ms=round(duration_ms, 2),
                        start_time=start_iso,
                        spans_count=len(spans),
                        jaeger_url=f"{settings.JAEGER_UI_URL}/trace/{tid}",
                    )
                )
    except Exception as e:
        logger.warning(f"Error consultando trazas en Jaeger: {e}")

    return schemas.JaegerTracesResponse(
        traces=traces_list,
        total=len(traces_list)
    )
