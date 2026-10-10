"""
Script PySpark MLlib: Entrenamiento de Modelo Predictivo GBTRegressor para Precios de MTG.
1. Carga el histórico de precios (card_price_history) y metadatos de cartas desde PostgreSQL.
2. Construye variables explicativas de series temporales (Lags t-1, t-3, t-7, Medias Móviles 7d/14d, Momentum, Volatilidad).
3. Entrena un GBTRegressor (Gradient Boosted Tree Regressor) distribuido con PySpark MLlib.
4. Evalúa métricas del modelo (RMSE, MAE) y las registra en Jaeger con OpenTelemetry.
5. Infiere el próximo precio estimado (t+1) para cada carta activa.
6. Almacena las predicciones en PostgreSQL ('card_price_predictions') y en Data Lake Parquet.
"""

import os
import sys
import argparse
import pandas as pd
import numpy as np
from datetime import datetime
from typing import List, Dict, Any

# Asegurar import de utilidades comunes
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from common_utils import (
    get_spark_session,
    get_db_connection,
    upsert_records_sql,
    write_spark_df_parquet,
    logger,
    trace_function,
    trace_span,
    set_span_attribute,
    add_span_event,
    get_current_trace_id,
    get_jaeger_trace_url,
    LAKE_DATA_DIR
)

from pyspark.sql import functions as F
from pyspark.sql.window import Window
from pyspark.sql.types import (
    StructType, StructField, StringType, DoubleType, DateType, FloatType
)
from pyspark.ml.feature import VectorAssembler, StringIndexer
from pyspark.ml.regression import GBTRegressor
from pyspark.ml.evaluation import RegressionEvaluator
from pyspark.ml import Pipeline


@trace_function("spark.ml.load_training_data")
def load_price_data(conn, max_cards: int = 0) -> pd.DataFrame:
    """
    Carga el histórico cronológico de precios junto a metadatos de cartas desde PostgreSQL.
    """
    limit_clause = f"AND h.card_uuid IN (SELECT uuid FROM cards LIMIT {max_cards})" if max_cards > 0 else ""
    
    query = f"""
    SELECT 
        h.card_uuid,
        h.provider,
        h.finish,
        h.price_date,
        CAST(h.price AS FLOAT) as price,
        COALESCE(c.mana_value, 0.0) as mana_value,
        COALESCE(c.rarity, 'common') as rarity
    FROM card_price_history h
    JOIN cards c ON h.card_uuid = c.uuid
    WHERE h.price > 0
    {limit_clause}
    ORDER BY h.card_uuid, h.provider, h.finish, h.price_date ASC
    """
    
    set_span_attribute("query.max_cards", max_cards)
    logger.info("Extrayendo histórico de precios desde PostgreSQL...")
    pdf = pd.read_sql_query(query, conn)
    set_span_attribute("data.raw_rows", len(pdf))
    logger.info(f"Cargados {len(pdf)} registros históricos de precios.")
    return pdf


@trace_function("spark.ml.engineer_features")
def engineer_features(spark, pdf: pd.DataFrame):
    """
    Convierte a DataFrame Spark y calcula características de series temporales (Lags, Medias móviles, Volatilidad).
    """
    if pdf.empty:
        raise ValueError("No se encontraron datos históricos de precios para entrenar el modelo.")

    # Convertir tipos en pandas antes de subir a Spark
    pdf["price"] = pdf["price"].astype(float)
    pdf["mana_value"] = pdf["mana_value"].astype(float)
    pdf["price_date"] = pd.to_datetime(pdf["price_date"]).dt.date

    spark_df = spark.createDataFrame(pdf)

    # Ventana ordenada cronológicamente por serie (carta, tienda, acabado)
    window_spec = Window.partitionBy("card_uuid", "provider", "finish").orderBy("price_date")

    # Ventana móvil de últimas observaciones anteriores
    roll_7 = Window.partitionBy("card_uuid", "provider", "finish").orderBy("price_date").rowsBetween(-7, -1)
    roll_14 = Window.partitionBy("card_uuid", "provider", "finish").orderBy("price_date").rowsBetween(-14, -1)

    featured_df = spark_df \
        .withColumn("lag_1", F.lag("price", 1).over(window_spec)) \
        .withColumn("lag_3", F.lag("price", 3).over(window_spec)) \
        .withColumn("lag_7", F.lag("price", 7).over(window_spec)) \
        .withColumn("ma_7", F.coalesce(F.avg("price").over(roll_7), F.col("lag_1"))) \
        .withColumn("ma_14", F.coalesce(F.avg("price").over(roll_14), F.col("ma_7"))) \
        .withColumn("volatility_7d", F.coalesce(F.stddev("price").over(roll_7), F.lit(0.0))) \
        .withColumn(
            "momentum_7d",
            (F.col("lag_1") - F.col("lag_7")) / F.when(F.col("lag_7") > 0, F.col("lag_7")).otherwise(1.0)
        ) \
        .withColumn("target_price", F.col("price")) \
        .filter(F.col("lag_1").isNotNull() & F.col("lag_7").isNotNull())

    return featured_df


@trace_function("spark.ml.train_gbt_regressor")
def train_and_evaluate_gbt(
    df, 
    max_iter: int = 25, 
    max_depth: int = 5
):
    """
    Entrena el Pipeline ML con VectorAssembler y GBTRegressor en Apache Spark MLlib.
    """
    logger.info(f"Configurando GBTRegressor: maxIter={max_iter}, maxDepth={max_depth}")
    set_span_attribute("model.type", "GBTRegressor")
    set_span_attribute("model.max_iter", max_iter)
    set_span_attribute("model.max_depth", max_depth)

    # Indexar rareza categórica
    rarity_indexer = StringIndexer(inputCol="rarity", outputCol="rarity_idx", handleInvalid="keep")

    feature_cols = [
        "lag_1", "lag_3", "lag_7", "ma_7", "ma_14", 
        "volatility_7d", "momentum_7d", "mana_value", "rarity_idx"
    ]
    assembler = VectorAssembler(inputCols=feature_cols, outputCol="features")

    gbt = GBTRegressor(
        featuresCol="features",
        labelCol="target_price",
        predictionCol="predicted_price",
        maxIter=max_iter,
        maxDepth=max_depth,
        seed=42,
        stepSize=0.1
    )

    pipeline = Pipeline(stages=[rarity_indexer, assembler, gbt])

    # Split train/test (80% / 20%)
    train_data, test_data = df.randomSplit([0.8, 0.2], seed=42)
    logger.info("Entrenando modelo GBTRegressor en cluster Spark...")
    model = pipeline.fit(train_data)

    # Evaluación
    eval_predictions = model.transform(test_data)
    evaluator_rmse = RegressionEvaluator(labelCol="target_price", predictionCol="predicted_price", metricName="rmse")
    evaluator_mae = RegressionEvaluator(labelCol="target_price", predictionCol="predicted_price", metricName="mae")
    evaluator_r2 = RegressionEvaluator(labelCol="target_price", predictionCol="predicted_price", metricName="r2")

    rmse = float(evaluator_rmse.evaluate(eval_predictions))
    mae = float(evaluator_mae.evaluate(eval_predictions))
    r2 = float(evaluator_r2.evaluate(eval_predictions))

    logger.info(f"Resultados de Evaluación: RMSE={rmse:.4f}, MAE={mae:.4f}, R2={r2:.4f}")
    set_span_attribute("eval.rmse", rmse)
    set_span_attribute("eval.mae", mae)
    set_span_attribute("eval.r2", r2)

    return model, {"rmse": rmse, "mae": mae, "r2": r2}


@trace_function("spark.ml.infer_and_save_predictions")
def infer_and_save(spark, conn, model, eval_metrics: Dict[str, float]):
    """
    Genera la inferencia del próximo precio para cada carta activa a partir
    de sus observaciones más recientes y actualiza PostgreSQL y Data Lake.
    """
    logger.info("Generando inferencia de próximo precio para cartas activas...")
    
    # 1. Obtener la serie más reciente por carta
    query_latest = """
    WITH RankedPrices AS (
        SELECT 
            h.card_uuid,
            h.price_date,
            CAST(h.price AS FLOAT) as price,
            COALESCE(c.mana_value, 0.0) as mana_value,
            COALESCE(c.rarity, 'common') as rarity,
            ROW_NUMBER() OVER(PARTITION BY h.card_uuid ORDER BY h.price_date DESC) as rn
        FROM card_price_history h
        JOIN cards c ON h.card_uuid = c.uuid
        WHERE h.provider = 'tcgplayer' AND h.finish = 'normal' AND h.price > 0
    )
    SELECT card_uuid, price_date, price, mana_value, rarity, rn
    FROM RankedPrices
    WHERE rn <= 8
    ORDER BY card_uuid, price_date ASC;
    """
    pdf_latest = pd.read_sql_query(query_latest, conn)
    
    if pdf_latest.empty:
        # Fallback a cualquier provider disponible
        query_latest = """
        WITH RankedPrices AS (
            SELECT 
                h.card_uuid,
                h.price_date,
                CAST(h.price AS FLOAT) as price,
                COALESCE(c.mana_value, 0.0) as mana_value,
                COALESCE(c.rarity, 'common') as rarity,
                ROW_NUMBER() OVER(PARTITION BY h.card_uuid ORDER BY h.price_date DESC) as rn
            FROM card_price_history h
            JOIN cards c ON h.card_uuid = c.uuid
            WHERE h.price > 0
        )
        SELECT card_uuid, price_date, price, mana_value, rarity, rn
        FROM RankedPrices
        WHERE rn <= 8
        ORDER BY card_uuid, price_date ASC;
        """
        pdf_latest = pd.read_sql_query(query_latest, conn)

    if pdf_latest.empty:
        logger.warning("No hay suficientes datos recientes para generar inferencias.")
        return 0

    # Construir features para el día de mañana (t+1)
    inference_records = []
    grouped = pdf_latest.groupby("card_uuid")
    
    for card_uuid, group in grouped:
        prices = group["price"].tolist()
        if not prices:
            continue
        
        current_p = float(prices[-1])
        lag_1 = float(prices[-1])
        lag_3 = float(prices[-3]) if len(prices) >= 3 else lag_1
        lag_7 = float(prices[-7]) if len(prices) >= 7 else lag_1
        
        ma_7 = float(np.mean(prices[-7:])) if len(prices) >= 7 else current_p
        ma_14 = ma_7
        volatility_7d = float(np.std(prices[-7:])) if len(prices) >= 7 else 0.0
        momentum_7d = float((lag_1 - lag_7) / lag_7) if lag_7 > 0 else 0.0
        
        mana_val = float(group["mana_value"].iloc[-1])
        rarity_val = str(group["rarity"].iloc[-1])
        
        inference_records.append({
            "card_uuid": card_uuid,
            "current_price": current_p,
            "lag_1": lag_1,
            "lag_3": lag_3,
            "lag_7": lag_7,
            "ma_7": ma_7,
            "ma_14": ma_14,
            "volatility_7d": volatility_7d,
            "momentum_7d": momentum_7d,
            "mana_value": mana_val,
            "rarity": rarity_val
        })

    inf_pdf = pd.DataFrame(inference_records)
    inf_spark_df = spark.createDataFrame(inf_pdf)
    
    # Predecir con el modelo
    predictions_df = model.transform(inf_spark_df)
    
    pred_results = predictions_df.select(
        "card_uuid", "current_price", "predicted_price"
    ).collect()

    db_rows = []
    confidence = max(50.0, min(95.0, round(float(eval_metrics.get("r2", 0.75)) * 100, 1)))

    for row in pred_results:
        c_price = float(row["current_price"])
        p_price = max(0.01, round(float(row["predicted_price"]), 4))
        diff = p_price - c_price
        change_pct = round((diff / c_price) * 100, 2) if c_price > 0 else 0.0
        
        if change_pct > 1.5:
            direction = "UP"
        elif change_pct < -1.5:
            direction = "DOWN"
        else:
            direction = "STABLE"

        db_rows.append((
            str(row["card_uuid"]),
            c_price,
            p_price,
            change_pct,
            direction,
            confidence,
            "GBTRegressor",
            "lag_1,lag_3,lag_7,ma_7,ma_14,volatility_7d,momentum_7d,mana_val,rarity"
        ))

    # Guardar en PostgreSQL
    upsert_sql = """
    INSERT INTO card_price_predictions (
        card_uuid, current_price, predicted_next_price, expected_change_pct,
        direction, confidence_score, model_name, features_used
    ) VALUES %s
    ON CONFLICT (card_uuid) DO UPDATE SET
        current_price = EXCLUDED.current_price,
        predicted_next_price = EXCLUDED.predicted_next_price,
        expected_change_pct = EXCLUDED.expected_change_pct,
        direction = EXCLUDED.direction,
        confidence_score = EXCLUDED.confidence_score,
        model_name = EXCLUDED.model_name,
        features_used = EXCLUDED.features_used,
        updated_at = CURRENT_TIMESTAMP;
    """
    upsert_records_sql(conn, upsert_sql, db_rows)
    logger.info(f"Guardadas {len(db_rows)} predicciones en 'card_price_predictions'.")

    # Guardar en Data Lake Parquet (exportar únicamente campos tabulares serializables)
    export_pdf = pd.DataFrame([
        {
            "card_uuid": r[0],
            "current_price": r[1],
            "predicted_next_price": r[2],
            "expected_change_pct": r[3],
            "direction": r[4],
            "confidence_score": r[5],
            "model_name": r[6],
            "features_used": r[7],
        }
        for r in db_rows
    ])
    export_df = spark.createDataFrame(export_pdf)
    out_parquet = os.path.join(LAKE_DATA_DIR, "predictions", "card_price_predictions.parquet")
    write_spark_df_parquet(export_df, out_parquet)
    logger.info(f"Predicciones respaldadas en Data Lake: {out_parquet}")

    return len(db_rows)


@trace_function("spark.pipeline.predict_card_prices", log_jaeger_link=True)
def run_price_prediction_pipeline(max_cards: int = 0, max_iter: int = 25, max_depth: int = 5):
    trace_id = get_current_trace_id()
    if trace_id:
        logger.info(f"🔗 Jaeger Trace disponible: {get_jaeger_trace_url(trace_id)}")

    logger.info("=== INICIANDO PIPELINE DE MACHINE LEARNING: GBTRegressor DE PRECIOS ===")
    
    spark = get_spark_session("MTG_GBTRegressor_Price_Predictor")
    conn = get_db_connection()

    try:
        pdf = load_price_data(conn, max_cards=max_cards)
        if pdf.empty:
            logger.warning("No hay suficientes datos para entrenar el modelo.")
            return

        featured_df = engineer_features(spark, pdf)
        model, metrics = train_and_evaluate_gbt(featured_df, max_iter=max_iter, max_depth=max_depth)
        count = infer_and_save(spark, conn, model, metrics)
        logger.info(f"=== PIPELINE GBTRegressor FINALIZADO: {count} CARTAS PREFECHADAS ===")
    finally:
        conn.close()
        spark.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pipeline PySpark MLlib GBTRegressor para predicción de precios MTG.")
    parser.add_argument("--max-cards", type=int, default=0, help="Límite opcional de cartas para entrenar.")
    parser.add_argument("--max-iter", type=int, default=25, help="Número máximo de iteraciones de árboles GBT.")
    parser.add_argument("--max-depth", type=int, default=5, help="Profundidad máxima de cada árbol de decisión.")
    args = parser.parse_args()

    run_price_prediction_pipeline(
        max_cards=args.max_cards,
        max_iter=args.max_iter,
        max_depth=args.max_depth
    )
