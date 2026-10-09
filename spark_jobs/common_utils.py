"""
Utilidades comunes para Jobs de PySpark, Conexión a Base de Datos MTG y Trazabilidad Jaeger.
"""

import os
import sys
import gzip
import json
import logging
import urllib.request
from typing import Dict, Any, List, Optional

# Asegurar importación de utilidades de tracing
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from tracing_utils import (
    configure_traced_logger,
    trace_function,
    trace_span,
    add_span_event,
    set_span_attribute,
    get_current_trace_id,
    get_current_span_id,
    get_jaeger_trace_url,
    init_tracer,
)

# Inicializar logger con soporte para inyección de Trace ID y Span ID en logs
logger = configure_traced_logger("MTGPipeline")

# Variables de entorno por defecto
DB_HOST = os.getenv("POSTGRES_HOST", "postgres")
DB_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
DB_NAME = os.getenv("POSTGRES_DB_MTG", "mtg_dw")
DB_USER = os.getenv("POSTGRES_USER", "airflow")
DB_PASS = os.getenv("POSTGRES_PASSWORD", "airflow")

DATA_DIR = os.getenv("DATA_DIR", "/opt/airflow/data")
RAW_DATA_DIR = os.path.join(DATA_DIR, "raw")
LAKE_DATA_DIR = os.path.join(DATA_DIR, "lake")


@trace_function("spark.session.initialize")
def get_spark_session(app_name: str = "MTG_Ingestion_Job"):
    """
    Inicializa una sesión de Spark optimizada con soporte para Cluster Dedicado (spark://spark-master:7077)
    o modo local, incluyendo compatibilidad con Parquet y PostgreSQL JDBC.
    """
    import socket
    from pyspark.sql import SparkSession
    
    spark_master = os.getenv("SPARK_MASTER", "spark://spark-master:7077")
    driver_host = os.getenv("SPARK_DRIVER_HOST", socket.gethostname())
    
    set_span_attribute("spark.app_name", app_name)
    set_span_attribute("spark.master", spark_master)
    set_span_attribute("spark.driver_host", driver_host)
    
    logger.info(f"Conectando a Spark Master: {spark_master} (Driver Host: {driver_host})")
    
    builder = (
        SparkSession.builder
        .appName(app_name)
        .master(spark_master)
        .config("spark.driver.host", driver_host)
        .config("spark.driver.bindAddress", "0.0.0.0")
        .config("spark.driver.memory", "2g")
        .config("spark.executor.memory", "2g")
        .config("spark.sql.parquet.compression.codec", "snappy")
        .config("spark.sql.execution.arrow.pyspark.enabled", "false")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.hadoop.mapreduce.fileoutputcommitter.algorithm.version", "2")
        .config("spark.hadoop.mapreduce.fileoutputcommitter.marksuccessfuljobs", "false")
    )
    
    # Si existe el driver jar de postgres, agregarlo
    jar_path = os.getenv("POSTGRES_JDBC_JAR", "/opt/spark/jars/postgresql-42.7.3.jar")
    if os.path.exists(jar_path):
        builder = builder.config("spark.jars", jar_path)
        builder = builder.config("spark.driver.extraClassPath", jar_path)
        builder = builder.config("spark.executor.extraClassPath", jar_path)
        set_span_attribute("spark.jdbc_jar", jar_path)
    
    spark = builder.getOrCreate()
    spark.sparkContext.setLogLevel("WARN")
    set_span_attribute("spark.version", spark.version)
    return spark


@trace_function("spark.parquet.write")
def write_spark_df_parquet(df, output_path: str, coalesce_one: bool = True):
    """
    Escribe un DataFrame de Spark en formato Parquet de forma segura y portable.
    Convierte las filas recolectadas a PyArrow sin depender de llamadas internas inseguras
    de memoria JVM de Arrow ni de renombrados atómicos de Hadoop en Windows/Docker.
    """
    import pandas as pd
    import pyarrow as pa
    import pyarrow.parquet as pq
    import shutil
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    set_span_attribute("parquet.output_path", output_path)
    
    # Si existía previamente como directorio o archivo
    if os.path.exists(output_path):
        if os.path.isdir(output_path):
            shutil.rmtree(output_path, ignore_errors=True)
        else:
            try:
                os.remove(output_path)
            except OSError:
                pass

    try:
        rows = [r.asDict() for r in df.collect()]
        row_count = len(rows)
        set_span_attribute("parquet.rows_written", row_count)
        
        pdf = pd.DataFrame(rows)
        arrow_table = pa.Table.from_pandas(pdf, preserve_index=False)
        pq.write_table(arrow_table, output_path, compression="snappy")
        
        if os.path.exists(output_path):
            set_span_attribute("parquet.file_size_bytes", os.path.getsize(output_path))
            
        add_span_event("parquet_write_success", {"rows": row_count, "path": output_path})
    except Exception as e:
        logger.warning(f"Fallback a Spark nativo parquet writer para {output_path}: {e}")
        writer = df.coalesce(1) if coalesce_one else df
        writer.write.mode("overwrite").parquet(output_path)
        add_span_event("parquet_write_fallback", {"error": str(e), "path": output_path})


@trace_function("database.connection.open")
def get_db_connection():
    """
    Retorna una conexión activa a PostgreSQL (mtg_dw).
    """
    import psycopg2
    set_span_attribute("db.system", "postgresql")
    set_span_attribute("db.name", DB_NAME)
    set_span_attribute("db.host", DB_HOST)
    set_span_attribute("db.port", DB_PORT)
    
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS
    )


@trace_function("http.download_json_gz")
def download_json_gz(url: str, output_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Descarga un archivo JSON comprimido en GZIP desde una URL y lo parsea a diccionario.
    Opcionalmente lo almacena localmente en disco.
    """
    set_span_attribute("http.url", url)
    if output_path:
        set_span_attribute("file.destination", output_path)
        
    logger.info(f"Descargando datos desde: {url}")
    headers = {"User-Agent": "MTGDataPipeline/1.0 (Apache Airflow & PySpark)"}
    req = urllib.request.Request(url, headers=headers)
    
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            content = resp.read()
            set_span_attribute("http.response_bytes", len(content))
            
            # Si se especificó ruta de guardado en disco
            if output_path:
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                with open(output_path, "wb") as f:
                    f.write(content)
                logger.info(f"Archivo guardado en: {output_path} ({len(content)} bytes)")
            
            # Descomprimir si es gzip o leer directamente si es json plano
            if url.endswith(".gz") or content[:2] == b'\x1f\x8b':
                decompressed = gzip.decompress(content)
                data = json.loads(decompressed.decode("utf-8"))
            else:
                data = json.loads(content.decode("utf-8"))
                
            add_span_event("download_complete", {"bytes": len(content)})
            return data
            
    except Exception as e:
        logger.error(f"Error descargando {url}: {str(e)}")
        raise


@trace_function("database.upsert_records")
def upsert_records_sql(conn, query: str, records: List[tuple], page_size: int = 2000):
    """
    Ejecuta un lote de inserción/upsert eficiente en PostgreSQL usando psycopg2 execute_values.
    """
    if not records:
        return
    set_span_attribute("db.operation", "upsert")
    set_span_attribute("db.record_count", len(records))
    set_span_attribute("db.page_size", page_size)
    
    from psycopg2.extras import execute_values
    with conn.cursor() as cur:
        execute_values(cur, query, records, page_size=page_size)
    conn.commit()
    add_span_event("records_upserted", {"count": len(records)})
