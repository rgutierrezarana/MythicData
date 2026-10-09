"""
Script PySpark: Ingesta de Cartas y Estructura de Precios por Set con OpenTracing y Jaeger.
1. Descarga los metadatos de cartas del set seleccionado (o sets) desde MTGJSON.
2. Descarga y extrae los precios asociados (hoy / histórico) cruzados por UUID de carta.
3. Genera exactamente 1 archivo Parquet por cada set en el Data Lake (data/lake/cards_prices/{SET_CODE}.parquet).
4. Inserta/Actualiza en PostgreSQL:
   - Tabla 'cards': metadatos de las cartas.
   - Tabla 'card_current_prices': snapshot actual de precios por tienda/acabado.
   - Tabla 'card_price_history': histórico cronológico para gráficas de variación.
5. Instrumentación con OpenTelemetry / Jaeger y correlación con logs.
"""

import os
import sys
import argparse
from datetime import datetime
from typing import List, Dict, Any, Tuple

# Asegurar import de utilidades
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
    LAKE_DATA_DIR
)

PRICES_TODAY_URL = "https://mtgjson.com/api/v5/AllPricesToday.json.gz"
PRICES_HISTORY_URL = "https://mtgjson.com/api/v5/AllPrices.json.gz"
SET_BASE_URL = "https://mtgjson.com/api/v5/{set_code}.json.gz"


@trace_function("spark.extract_price_records")
def extract_price_records(
    uuid_set: set, 
    all_prices_data: Dict[str, Any], 
    set_code: str
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Extrae todos los registros de precios para los UUIDs dados.
    Retorna:
      - all_price_points: todos los precios históricos disponibles.
      - latest_price_points: el precio más reciente por cada combinación única.
    """
    set_span_attribute("set_code", set_code)
    set_span_attribute("uuid_count", len(uuid_set))
    
    all_price_points = []
    latest_price_map = {}  # key -> record

    for card_uuid in uuid_set:
        if card_uuid not in all_prices_data:
            continue
            
        card_price_obj = all_prices_data[card_uuid]
        
        for game_format, providers in card_price_obj.items():
            if not isinstance(providers, dict):
                continue
                
            for provider_name, provider_data in providers.items():
                if not isinstance(provider_data, dict):
                    continue
                    
                currency = provider_data.get("currency", "USD")
                
                for price_type in ["retail", "buylist"]:
                    type_data = provider_data.get(price_type, {})
                    if not isinstance(type_data, dict):
                        continue
                        
                    for finish in ["normal", "foil", "etched"]:
                        finish_data = type_data.get(finish, {})
                        if not isinstance(finish_data, dict):
                            continue
                            
                        for date_str, price_val in finish_data.items():
                            if price_val is None:
                                continue
                            try:
                                p_val = float(price_val)
                                p_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                            except (ValueError, TypeError):
                                continue

                            rec = {
                                "card_uuid": card_uuid,
                                "set_code": set_code,
                                "provider": provider_name.lower(),
                                "game_format": game_format.lower(),
                                "price_type": price_type.lower(),
                                "finish": finish.lower(),
                                "currency": currency.upper(),
                                "price_date": p_date,
                                "price": p_val
                            }
                            all_price_points.append(rec)
                            
                            # Para el snapshot actual: mantener el precio de la fecha más reciente
                            unique_key = (card_uuid, provider_name.lower(), game_format.lower(), price_type.lower(), finish.lower(), currency.upper())
                            if unique_key not in latest_price_map or p_date > latest_price_map[unique_key]["price_date"]:
                                latest_price_map[unique_key] = rec

    latest_prices = list(latest_price_map.values())
    set_span_attribute("price_records.total_history", len(all_price_points))
    set_span_attribute("price_records.total_latest", len(latest_prices))
    return all_price_points, latest_prices


def get_card_latest_prices(
    card_uuid: str,
    latest_prices_for_card: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Calcula los precios consolidados más recientes (USD, EUR, Foil) para una carta individual.
    """
    summary = {
        "current_price_usd": None,
        "current_price_eur": None,
        "current_price_foil": None,
        "current_price_date": None,
        "current_price_provider": None,
    }
    
    if not latest_prices_for_card:
        return summary

    latest_date = None
    
    for p in latest_prices_for_card:
        p_date = p.get("price_date")
        if p_date and (latest_date is None or p_date > latest_date):
            latest_date = p_date

        currency = (p.get("currency") or "").upper()
        finish = (p.get("finish") or "").lower()
        price_type = (p.get("price_type") or "").lower()
        provider = (p.get("provider") or "").lower()
        price_val = p.get("price")

        if price_val is None:
            continue

        # Priorizar retail normal
        if price_type == "retail":
            if currency == "USD" and finish == "normal":
                if provider == "tcgplayer" or summary["current_price_usd"] is None:
                    summary["current_price_usd"] = price_val
                    summary["current_price_provider"] = provider
            elif currency == "EUR" and finish == "normal":
                if provider == "cardmarket" or summary["current_price_eur"] is None:
                    summary["current_price_eur"] = price_val
            elif finish in ["foil", "etched"]:
                if summary["current_price_foil"] is None or (provider == "tcgplayer" and currency == "USD"):
                    summary["current_price_foil"] = price_val

    # Fallbacks si no se encontró precio retail normal en USD
    if summary["current_price_usd"] is None:
        for p in latest_prices_for_card:
            if p.get("currency") == "USD" and p.get("price") is not None:
                summary["current_price_usd"] = p["price"]
                summary["current_price_provider"] = p.get("provider")
                break

    summary["current_price_date"] = latest_date
    return summary


@trace_function("spark.process_single_set")
def process_single_set(
    spark,
    conn,
    set_code: str,
    all_prices_data: Dict[str, Any]
):
    set_code = set_code.strip().upper()
    set_span_attribute("set.code", set_code)
    logger.info(f"--- Procesando Set: {set_code} ---")
    
    # 1. Descargar archivo del set
    set_url = SET_BASE_URL.format(set_code=set_code)
    raw_set_file = os.path.join(RAW_DATA_DIR, f"{set_code}.json.gz")
    
    try:
        set_json = download_json_gz(set_url, raw_set_file)
    except Exception as e:
        logger.error(f"No se pudo descargar la información para el set '{set_code}': {e}")
        return

    data = set_json.get("data", {})
    cards_list = data.get("cards", [])
    set_name = data.get("name", set_code)
    set_span_attribute("set.name", set_name)
    set_span_attribute("set.cards_in_json", len(cards_list))
    logger.info(f"Set '{set_name}' ({set_code}): {len(cards_list)} cartas encontradas.")

    if not cards_list:
        logger.warning(f"El set '{set_code}' no contiene cartas. Saltando.")
        return

    # 2. Extraer precios para este set primero
    set_uuids = {c.get("uuid") for c in cards_list if c.get("uuid")}
    all_prices, latest_prices = extract_price_records(set_uuids, all_prices_data, set_code)
    logger.info(f"Set {set_code}: {len(all_prices)} puntos históricos de precios, {len(latest_prices)} precios actuales.")

    # Mapear precios más recientes por card_uuid
    latest_prices_by_uuid: Dict[str, List[Dict[str, Any]]] = {}
    for p in latest_prices:
        latest_prices_by_uuid.setdefault(p["card_uuid"], []).append(p)

    # 3. Parsear y consolidar metadatos de cartas con su último precio (sin duplicar cartas)
    with trace_span("spark.parse_card_metadata", {"set_code": set_code, "cards.count": len(cards_list)}):
        cleaned_cards = []
        for c in cards_list:
            uuid = c.get("uuid")
            if not uuid:
                continue
                
            identifiers = c.get("identifiers", {}) or {}
            finishes = c.get("finishes", []) or []
            finishes_str = ",".join(finishes) if isinstance(finishes, list) else str(finishes)
            
            availability = c.get("availability", []) or []
            availability_str = ",".join(availability) if isinstance(availability, list) else str(availability)

            # Obtener último precio consolidado para esta carta
            card_prices_summary = get_card_latest_prices(uuid, latest_prices_by_uuid.get(uuid, []))

            cleaned_cards.append({
                "uuid": uuid,
                "set_code": set_code,
                "name": c.get("name") or "Unknown Card",
                "collector_number": str(c.get("number", "")),
                "rarity": c.get("rarity"),
                "mana_cost": c.get("manaCost"),
                "mana_value": float(c.get("manaValue", 0.0) or 0.0),
                "type_line": c.get("type"),
                "scryfall_id": identifiers.get("scryfallId"),
                "tcgplayer_product_id": str(identifiers.get("tcgplayerProductId", "") or ""),
                "finishes": finishes_str,
                "artist": c.get("artist"),
                "availability": availability_str,
                "current_price_usd": card_prices_summary["current_price_usd"],
                "current_price_eur": card_prices_summary["current_price_eur"],
                "current_price_foil": card_prices_summary["current_price_foil"],
                "current_price_date": card_prices_summary["current_price_date"],
                "current_price_provider": card_prices_summary["current_price_provider"],
            })

    # 4. Procesamiento con PySpark y guardado en Parquet (1 archivo Parquet por set, 1 fila por carta sin duplicados)
    with trace_span("spark.create_cards_dataframe", {"set_code": set_code, "cards.count": len(cleaned_cards)}):
        from pyspark.sql.types import (
            StructType, StructField, StringType, DoubleType, DateType
        )
        from pyspark.sql import functions as F

        card_schema = StructType([
            StructField("uuid", StringType(), False),
            StructField("set_code", StringType(), False),
            StructField("name", StringType(), False),
            StructField("collector_number", StringType(), True),
            StructField("rarity", StringType(), True),
            StructField("mana_cost", StringType(), True),
            StructField("mana_value", DoubleType(), True),
            StructField("type_line", StringType(), True),
            StructField("scryfall_id", StringType(), True),
            StructField("tcgplayer_product_id", StringType(), True),
            StructField("finishes", StringType(), True),
            StructField("artist", StringType(), True),
            StructField("availability", StringType(), True),
            StructField("current_price_usd", DoubleType(), True),
            StructField("current_price_eur", DoubleType(), True),
            StructField("current_price_foil", DoubleType(), True),
            StructField("current_price_date", DateType(), True),
            StructField("current_price_provider", StringType(), True),
        ])
        
        df_cards = spark.createDataFrame(cleaned_cards, schema=card_schema)
        df_cards = df_cards.withColumn("processed_at", F.current_timestamp())

    # Escribir 1 archivo Parquet por cada set con las cartas y su precio actual
    lake_set_parquet = os.path.join(LAKE_DATA_DIR, "cards_prices", f"{set_code}.parquet")
    logger.info(f"Guardando Parquet de cartas del set '{set_code}' ({len(cleaned_cards)} cartas únicas) en: {lake_set_parquet}")
    write_spark_df_parquet(df_cards, lake_set_parquet, coalesce_one=True)
    logger.info(f"-> Parquet de cartas de {set_code} generado exitosamente.")

    # Guardar histórico de precios en Parquet en carpeta dedicada si hay datos
    if all_prices:
        with trace_span("spark.create_price_history_dataframe", {"set_code": set_code, "prices.count": len(all_prices)}):
            price_schema = StructType([
                StructField("card_uuid", StringType(), False),
                StructField("set_code", StringType(), False),
                StructField("provider", StringType(), False),
                StructField("game_format", StringType(), False),
                StructField("price_type", StringType(), False),
                StructField("finish", StringType(), False),
                StructField("currency", StringType(), False),
                StructField("price_date", DateType(), False),
                StructField("price", DoubleType(), False)
            ])
            df_prices = spark.createDataFrame(all_prices, schema=price_schema)
            lake_hist_parquet = os.path.join(LAKE_DATA_DIR, "price_history", f"{set_code}.parquet")
            write_spark_df_parquet(df_prices, lake_hist_parquet, coalesce_one=True)
            logger.info(f"-> Parquet histórico de precios de {set_code} guardado en: {lake_hist_parquet}")

    # 5. Cargar en Base de Datos PostgreSQL
    with trace_span("database.upsert_cards_data", {"set_code": set_code, "cards.count": len(cleaned_cards)}):
        # 5.1 Insert/Upsert Cards (Actualiza los metadatos y el último precio sin duplicar registros)
        cards_tuples = [
            (
                c["uuid"], c["set_code"], c["name"], c["collector_number"],
                c["rarity"], c["mana_cost"], c["mana_value"], c["type_line"],
                c["scryfall_id"], c["tcgplayer_product_id"], c["finishes"],
                c["artist"], c["availability"],
                c["current_price_usd"], c["current_price_eur"], c["current_price_foil"],
                c["current_price_date"], c["current_price_provider"]
            )
            for c in cleaned_cards
        ]
        
        upsert_cards_sql = """
        INSERT INTO cards (
            uuid, set_code, name, collector_number, rarity,
            mana_cost, mana_value, type_line, scryfall_id,
            tcgplayer_product_id, finishes, artist, availability,
            current_price_usd, current_price_eur, current_price_foil,
            current_price_date, current_price_provider
        ) VALUES %s
        ON CONFLICT (uuid) DO UPDATE SET
            name = EXCLUDED.name,
            collector_number = EXCLUDED.collector_number,
            rarity = EXCLUDED.rarity,
            mana_cost = EXCLUDED.mana_cost,
            mana_value = EXCLUDED.mana_value,
            type_line = EXCLUDED.type_line,
            scryfall_id = EXCLUDED.scryfall_id,
            tcgplayer_product_id = EXCLUDED.tcgplayer_product_id,
            finishes = EXCLUDED.finishes,
            artist = EXCLUDED.artist,
            availability = EXCLUDED.availability,
            current_price_usd = EXCLUDED.current_price_usd,
            current_price_eur = EXCLUDED.current_price_eur,
            current_price_foil = EXCLUDED.current_price_foil,
            current_price_date = EXCLUDED.current_price_date,
            current_price_provider = EXCLUDED.current_price_provider,
            updated_at = CURRENT_TIMESTAMP;
        """
        upsert_records_sql(conn, upsert_cards_sql, cards_tuples)
        logger.info(f"-> {len(cards_tuples)} cartas insertadas/actualizadas (Upsert con último precio) en tabla 'cards'.")

    # 5.2 Insert/Upsert Current Prices
    if latest_prices:
        with trace_span("database.upsert_current_prices", {"set_code": set_code, "prices.count": len(latest_prices)}):
            current_price_tuples = [
                (
                    p["card_uuid"], p["set_code"], p["provider"], p["game_format"],
                    p["price_type"], p["finish"], p["currency"], p["price"], p["price_date"]
                )
                for p in latest_prices
            ]
            
            upsert_current_prices_sql = """
            INSERT INTO card_current_prices (
                card_uuid, set_code, provider, game_format, price_type,
                finish, currency, price, price_date
            ) VALUES %s
            ON CONFLICT (card_uuid, provider, game_format, price_type, finish, currency) DO UPDATE SET
                price = EXCLUDED.price,
                price_date = EXCLUDED.price_date,
                updated_at = CURRENT_TIMESTAMP;
            """
            upsert_records_sql(conn, upsert_current_prices_sql, current_price_tuples)
            logger.info(f"-> {len(current_price_tuples)} registros en 'card_current_prices'.")

    # 5.3 Insert/Upsert Price History
    if all_prices:
        with trace_span("database.upsert_price_history", {"set_code": set_code, "prices.count": len(all_prices)}):
            history_price_tuples = [
                (
                    p["card_uuid"], p["set_code"], p["provider"], p["game_format"],
                    p["price_type"], p["finish"], p["currency"], p["price_date"], p["price"]
                )
                for p in all_prices
            ]
            
            upsert_history_sql = """
            INSERT INTO card_price_history (
                card_uuid, set_code, provider, game_format, price_type,
                finish, currency, price_date, price
            ) VALUES %s
            ON CONFLICT (card_uuid, provider, game_format, price_type, finish, currency, price_date) DO UPDATE SET
                price = EXCLUDED.price;
            """
            upsert_records_sql(conn, upsert_history_sql, history_price_tuples)
            logger.info(f"-> {len(history_price_tuples)} registros en 'card_price_history'.")


@trace_function("spark.pipeline.process_cards_and_prices", log_jaeger_link=True)
def run_process_cards_and_prices(set_codes: List[str], load_full_history: bool = False):
    trace_id = get_current_trace_id()
    if trace_id:
        logger.info(f"🔗 Jaeger Trace disponible: {get_jaeger_trace_url(trace_id)}")

    logger.info(f"=== INICIANDO PIPELINE DE CARTAS Y PRECIOS PARA SETS: {set_codes} ===")
    set_span_attribute("pipeline.sets", ",".join(set_codes))
    set_span_attribute("pipeline.load_full_history", load_full_history)
    set_span_attribute("pipeline.sets_count", len(set_codes))
    
    if not set_codes:
        logger.warning("No se especificaron códigos de sets a procesar.")
        return

    # 1. Descargar precios globales (AllPricesToday o AllPrices)
    prices_url = PRICES_HISTORY_URL if load_full_history else PRICES_TODAY_URL
    raw_prices_file = os.path.join(
        RAW_DATA_DIR, 
        "AllPrices.json.gz" if load_full_history else "AllPricesToday.json.gz"
    )
    
    logger.info(f"Descargando archivo de precios desde: {prices_url}")
    prices_raw = download_json_gz(prices_url, raw_prices_file)
    all_prices_data = prices_raw.get("data", {})
    set_span_attribute("prices.total_cards_quoted", len(all_prices_data))
    logger.info(f"Archivo de precios cargado con {len(all_prices_data)} cartas cotizadas.")

    # 2. Inicializar Spark y PostgreSQL
    spark = get_spark_session("MTG_Cards_Pricing_Ingestion")
    conn = get_db_connection()

    try:
        for code in set_codes:
            if code and code.strip():
                process_single_set(spark, conn, code.strip(), all_prices_data)
    finally:
        conn.close()
        spark.stop()

    logger.info("=== PIPELINE DE CARTAS Y PRECIOS FINALIZADO EXITOSAMENTE ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingesta de Cartas y Precios MTG por Set")
    parser.add_argument(
        "--sets", 
        type=str, 
        required=True, 
        help="Lista de códigos de sets separados por coma (ej. 'MH3,FDN,BLB,LEA')"
    )
    parser.add_argument(
        "--history", 
        action="store_true", 
        help="Cargar histórico completo de 90 días (AllPrices.json.gz) en vez de solo hoy"
    )
    args = parser.parse_args()
    
    sets_list = [s.strip() for s in args.sets.split(",") if s.strip()]
    run_process_cards_and_prices(sets_list, load_full_history=args.history)
