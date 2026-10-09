"""
Script PySpark: Ingesta de Todos los Sets de Magic: The Gathering con OpenTracing y Jaeger.
1. Descarga el archivo SetList.json.gz oficial de MTGJSON.
2. Transforma y normaliza los datos con PySpark DataFrame.
3. Guarda los datos transformados en formato Parquet en el Data Lake.
4. Realiza Upsert en la tabla PostgreSQL 'sets'.
5. Instrumentación con OpenTelemetry / Jaeger y correlación con logs.
"""

import os
import sys
import argparse
from datetime import datetime

# Asegurar import de módulos locales
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from common_utils import (
    get_spark_session,
    get_db_connection,
    download_json_gz,
    upsert_records_sql,
    write_spark_df_parquet,
    logger,
    trace_function,
    trace_span,
    set_span_attribute,
    add_span_event,
    get_current_trace_id,
    get_jaeger_trace_url,
    RAW_DATA_DIR,
    LAKE_DATA_DIR,
)

SET_LIST_URL = "https://mtgjson.com/api/v5/SetList.json.gz"


@trace_function("spark.pipeline.process_sets", log_jaeger_link=True)
def run_process_sets(force_download: bool = False):
    trace_id = get_current_trace_id()
    if trace_id:
        logger.info(f"🔗 Jaeger Trace disponible: {get_jaeger_trace_url(trace_id)}")
    
    logger.info("=== INICIANDO PIPELINE DE INGESTA DE SETS ===")
    set_span_attribute("pipeline.name", "process_sets")
    set_span_attribute("pipeline.force_download", force_download)

    # 1. Definir rutas
    raw_file = os.path.join(RAW_DATA_DIR, "SetList.json.gz")
    lake_sets_parquet = os.path.join(LAKE_DATA_DIR, "sets", "sets.parquet")

    # 2. Descargar archivo
    data_json = download_json_gz(SET_LIST_URL, raw_file)
    sets_list = data_json.get("data", [])
    logger.info(f"Total de sets recibidos desde MTGJSON: {len(sets_list)}")
    set_span_attribute("mtgjson.sets_received", len(sets_list))

    if not sets_list:
        raise ValueError("No se encontraron sets en la respuesta de MTGJSON")

    # 3. Limpiar y estructurar registros para PySpark
    with trace_span("spark.clean_and_parse_sets", {"sets.raw_count": len(sets_list)}):
        cleaned_rows = []
        for s in sets_list:
            code = (s.get("code") or "").strip().upper()
            if not code:
                continue

            release_date_str = s.get("releaseDate")
            release_date = None
            if release_date_str:
                try:
                    release_date = datetime.strptime(release_date_str, "%Y-%m-%d").date()
                except ValueError:
                    release_date = None

            cleaned_rows.append(
                {
                    "code": code,
                    "name": s.get("name") or "Unknown Set",
                    "release_date": release_date,
                    "base_set_size": int(s.get("baseSetSize", 0) or 0),
                    "total_set_size": int(s.get("totalSetSize", 0) or 0),
                    "set_type": s.get("type"),
                    "block": s.get("block"),
                    "keyrune_code": s.get("keyruneCode"),
                    "is_online_only": bool(s.get("isOnlineOnly", False)),
                    "is_foil_only": bool(s.get("isFoilOnly", False)),
                }
            )
        set_span_attribute("sets.cleaned_count", len(cleaned_rows))

    # 4. Procesamiento con PySpark
    with trace_span("spark.create_sets_dataframe", {"sets.count": len(cleaned_rows)}):
        from pyspark.sql.types import (
            StructType,
            StructField,
            StringType,
            IntegerType,
            BooleanType,
            DateType,
        )
        from pyspark.sql import functions as F

        spark = get_spark_session("MTG_Sets_Ingestion")

        schema = StructType(
            [
                StructField("code", StringType(), False),
                StructField("name", StringType(), False),
                StructField("release_date", DateType(), True),
                StructField("base_set_size", IntegerType(), True),
                StructField("total_set_size", IntegerType(), True),
                StructField("set_type", StringType(), True),
                StructField("block", StringType(), True),
                StructField("keyrune_code", StringType(), True),
                StructField("is_online_only", BooleanType(), True),
                StructField("is_foil_only", BooleanType(), True),
            ]
        )

        df_sets = spark.createDataFrame(cleaned_rows, schema=schema)
        df_sets = df_sets.withColumn("updated_at", F.current_timestamp())

    # 5. Guardar en Parquet en Data Lake (Paso 1 del requerimiento)
    logger.info(f"Guardando {len(cleaned_rows)} sets en Parquet: {lake_sets_parquet}")
    write_spark_df_parquet(df_sets, lake_sets_parquet, coalesce_one=True)
    logger.info("-> Parquet de Sets guardado exitosamente.")

    # 6. Cargar en Base de Datos PostgreSQL
    with trace_span("database.load_sets_postgres", {"sets.records_to_insert": len(cleaned_rows)}):
        logger.info("Cargando sets en base de datos PostgreSQL (mtg_dw.sets)...")
        records_to_insert = [
            (
                r["code"],
                r["name"],
                r["release_date"],
                r["base_set_size"],
                r["total_set_size"],
                r["set_type"],
                r["block"],
                r["keyrune_code"],
                r["is_online_only"],
                r["is_foil_only"],
            )
            for r in cleaned_rows
        ]

        upsert_query = """
        INSERT INTO sets (
            code, name, release_date, base_set_size, total_set_size,
            set_type, block, keyrune_code, is_online_only, is_foil_only
        ) VALUES %s
        ON CONFLICT (code) DO UPDATE SET
            name = EXCLUDED.name,
            release_date = EXCLUDED.release_date,
            base_set_size = EXCLUDED.base_set_size,
            total_set_size = EXCLUDED.total_set_size,
            set_type = EXCLUDED.set_type,
            block = EXCLUDED.block,
            keyrune_code = EXCLUDED.keyrune_code,
            is_online_only = EXCLUDED.is_online_only,
            is_foil_only = EXCLUDED.is_foil_only,
            updated_at = CURRENT_TIMESTAMP;
        """

        conn = get_db_connection()
        try:
            upsert_records_sql(conn, upsert_query, records_to_insert)
            logger.info(
                f"-> {len(records_to_insert)} sets insertados/actualizados en PostgreSQL."
            )
            add_span_event("postgres_sets_loaded", {"total": len(records_to_insert)})
        finally:
            conn.close()
            spark.stop()

    logger.info("=== PIPELINE DE SETS FINALIZADO CON ÉXITO ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Ingesta de Sets MTG a Parquet y Postgres"
    )
    parser.add_argument(
        "--force", action="store_true", help="Forzar re-descarga de archivos"
    )
    args = parser.parse_args()

    run_process_sets(force_download=args.force)
