"""
Card Kingdom Price Streamer & Continuous Ingestion Worker.

Este módulo implementa un flujo de streaming y carga continua de precios
desde la API pública v2 de Card Kingdom (https://api.cardkingdom.com/api/v2/pricelist)
para un grupo específico de cartas de Magic: The Gathering.

Características:
1. Filtrado O(1) en memoria por grupo de cartas objetivo (por Scryfall ID, Set Code o Nombres).
2. Detección de variaciones en tiempo real (Delta / Spikes / Spread retail vs buylist).
3. Upsert atómico en PostgreSQL / SQLite (tablas 'card_current_prices', 'card_price_history' y 'cards').
4. Modo Generador (Streaming Event-Driven) y Modo Worker Continuo (Daemon sin UI/Front).
"""

import os
import sys
import time
import json
import logging
import argparse
from datetime import datetime, date
from typing import Dict, List, Optional, Generator, Any, Tuple
import requests
from sqlalchemy import text
from sqlalchemy.orm import Session

# Ajustar PYTHONPATH para permitir ejecución independiente
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    from backend.database import SessionLocal, engine, is_sqlite
    from backend.models import CardModel, CardCurrentPriceModel, CardPriceHistoryModel
except ImportError:
    # Soporte para ejecución en contenedores con diferentes rutas
    from database import SessionLocal, engine, is_sqlite
    from models import CardModel, CardCurrentPriceModel, CardPriceHistoryModel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("CKPriceStreamer")

CARDKINGDOM_PRICELIST_URL = "https://api.cardkingdom.com/api/v2/pricelist"
DEFAULT_USER_AGENT = "MythicData-CardKingdom-Streamer/1.0 (bigdata-mtg-pipeline)"


class CardKingdomPriceStreamer:
    """
    Motor de streaming e ingesta continua para Card Kingdom.
    """

    def __init__(
        self,
        set_code: Optional[str] = None,
        card_names: Optional[List[str]] = None,
        scryfall_ids: Optional[List[str]] = None,
        card_uuids: Optional[List[str]] = None,
        stream_enabled_only: bool = True,
        limit_cards: Optional[int] = None,
        auto_load_from_db: bool = True
    ):
        self.set_code = set_code.upper() if set_code else None
        self.card_names = [n.strip().lower() for n in card_names] if card_names else []
        self.scryfall_ids = set(scryfall_ids) if scryfall_ids else set()
        self.card_uuids = [u.strip() for u in card_uuids if u.strip()] if card_uuids else []
        self.stream_enabled_only = stream_enabled_only
        self.limit_cards = limit_cards
        self.auto_load_from_db = auto_load_from_db

        # Mapeos en memoria para resolución ultrarrápida O(1)
        # scryfall_id -> {uuid, name, set_code, rarity}
        self.target_by_scryfall_id: Dict[str, Dict[str, Any]] = {}
        # name_lower -> list of {uuid, name, set_code, scryfall_id}
        self.target_by_name: Dict[str, List[Dict[str, Any]]] = {}

        # Caché de precios previos para detección de cambios (deltas)
        # (uuid, finish) -> {"price_retail": float, "price_buy": float}
        self.previous_prices_cache: Dict[Tuple[str, str], Dict[str, float]] = {}

        self._load_target_group()

    def _load_target_group(self):
        """
        Carga el catálogo de cartas objetivo desde la base de datos PostgreSQL/SQLite.
        Si no se especifican filtros explícitos, carga únicamente las cartas con is_streaming_enabled = True.
        """
        if not self.auto_load_from_db:
            return

        db: Session = SessionLocal()
        try:
            query = db.query(CardModel.uuid, CardModel.set_code, CardModel.name, CardModel.scryfall_id, CardModel.rarity)

            has_explicit_filter = bool(self.set_code or self.card_names or self.scryfall_ids or self.card_uuids)

            if self.card_uuids:
                query = query.filter(CardModel.uuid.in_(self.card_uuids))

            if self.set_code:
                query = query.filter(CardModel.set_code == self.set_code)
            
            if self.card_names:
                from sqlalchemy import func
                query = query.filter(func.lower(CardModel.name).in_(self.card_names))

            if self.scryfall_ids:
                query = query.filter(CardModel.scryfall_id.in_(list(self.scryfall_ids)))

            # Si no hay filtros explícitos y stream_enabled_only está activo, filtrar por flag
            if not has_explicit_filter and self.stream_enabled_only:
                query = query.filter(CardModel.is_streaming_enabled == True)

            if self.limit_cards:
                query = query.limit(self.limit_cards)

            records = query.all()

            for r in records:
                card_data = {
                    "uuid": r.uuid,
                    "set_code": r.set_code,
                    "name": r.name,
                    "scryfall_id": r.scryfall_id,
                    "rarity": r.rarity,
                }
                if r.scryfall_id:
                    self.target_by_scryfall_id[r.scryfall_id] = card_data

                n_lower = r.name.lower()
                if n_lower not in self.target_by_name:
                    self.target_by_name[n_lower] = []
                self.target_by_name[n_lower].append(card_data)

            logger.info(
                f"Grupo de cartas cargado: {len(records)} cartas objetivo identificadas en la base de datos "
                f"(Filtros: set={self.set_code}, names={len(self.card_names)}, ids={len(self.scryfall_ids)})."
            )

            # Si la DB está vacía y se pasaron nombres manuales, usamos modo autónomo sin DB
            if not records and self.card_names:
                logger.warning("No se encontraron cartas en la base de datos local. Operando en modo standalone por nombre.")
                for name in self.card_names:
                    self.target_by_name[name] = [{"uuid": f"custom_{name}", "set_code": "CUSTOM", "name": name, "scryfall_id": None}]

        except Exception as e:
            logger.error(f"Error cargando cartas objetivo desde la base de datos: {e}")
        finally:
            db.close()

    def fetch_pricelist(self) -> List[Dict[str, Any]]:
        """
        Descarga el catálogo completo de precios de Card Kingdom con compresión gzip.
        Retorna la lista de ítems de cartas.
        """
        logger.info(f"Conectando a Card Kingdom API: {CARDKINGDOM_PRICELIST_URL}...")
        headers = {
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept-Encoding": "gzip, deflate",
            "Accept": "application/json",
        }

        start_time = time.time()
        try:
            response = requests.get(CARDKINGDOM_PRICELIST_URL, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()
            items = data.get("data", [])
            elapsed = time.time() - start_time
            size_mb = len(response.content) / (1024 * 1024)
            logger.info(f"Descarga completada en {elapsed:.2f}s ({len(items):,} artículos analizados, ~{size_mb:.2f} MB recibidos).")
            return items
        except requests.exceptions.RequestException as e:
            logger.error(f"Falla al consultar la API de Card Kingdom: {e}")
            return []

    def stream_price_events(self) -> Generator[Dict[str, Any], None, None]:
        """
        Generador de streaming: procesa los datos de Card Kingdom y emite
        eventos de precio enriquecidos únicamente para el grupo de cartas objetivo.
        """
        items = self.fetch_pricelist()
        if not items:
            return

        now_iso = datetime.utcnow().isoformat()
        current_date_str = date.today().isoformat()
        matched_count = 0

        for item in items:
            ck_scryfall_id = item.get("scryfall_id")
            ck_name = item.get("name", "")
            ck_name_lower = ck_name.lower()
            
            matched_card: Optional[Dict[str, Any]] = None

            # 1. Búsqueda directa O(1) por Scryfall ID
            if ck_scryfall_id and ck_scryfall_id in self.target_by_scryfall_id:
                matched_card = self.target_by_scryfall_id[ck_scryfall_id]
            # 2. Búsqueda por Nombre si no hay Scryfall ID mapeado
            elif ck_name_lower in self.target_by_name:
                matched_card = self.target_by_name[ck_name_lower][0]

            if not matched_card:
                continue

            matched_count += 1
            card_uuid = matched_card["uuid"]
            finish = "foil" if str(item.get("is_foil", "false")).lower() == "true" else "normal"

            # Parseo seguro de precios
            try:
                price_retail = float(item.get("price_retail", 0.0))
            except (ValueError, TypeError):
                price_retail = 0.0

            try:
                price_buy = float(item.get("price_buy", 0.0))
            except (ValueError, TypeError):
                price_buy = 0.0

            # Métricas analíticas del mercado
            spread_pct = round(((price_retail - price_buy) / price_retail * 100), 2) if price_retail > 0 else 0.0
            qty_retail = int(item.get("qty_retail", 0))
            qty_buying = int(item.get("qty_buying", 0))

            # Detección de cambios (Deltas de precio)
            cache_key = (card_uuid, finish)
            old_prices = self.previous_prices_cache.get(cache_key)
            price_delta_retail = round(price_retail - old_prices["price_retail"], 4) if old_prices else 0.0
            price_delta_buy = round(price_buy - old_prices["price_buy"], 4) if old_prices else 0.0

            # Actualizar caché
            self.previous_prices_cache[cache_key] = {
                "price_retail": price_retail,
                "price_buy": price_buy
            }

            event = {
                "event_type": "PRICE_UPDATE",
                "provider": "cardkingdom",
                "card_uuid": card_uuid,
                "scryfall_id": ck_scryfall_id or matched_card.get("scryfall_id"),
                "name": matched_card["name"],
                "set_code": matched_card["set_code"],
                "edition_name": item.get("edition", ""),
                "finish": finish,
                "currency": "USD",
                "game_format": "paper",
                "price_retail": price_retail,
                "price_buy": price_buy,
                "price_delta_retail": price_delta_retail,
                "price_delta_buy": price_delta_buy,
                "spread_pct": spread_pct,
                "qty_retail": qty_retail,
                "qty_buying": qty_buying,
                "condition_values": item.get("condition_values", {}),
                "timestamp": now_iso,
                "price_date": current_date_str,
            }

            yield event

        logger.info(f"Ciclo de streaming finalizado: {matched_count} eventos emitidos para el grupo objetivo.")

    def persist_events_to_db(self, events: List[Dict[str, Any]]) -> int:
        """
        Persiste los eventos en la base de datos (PostgreSQL / SQLite):
        - Actualiza el precio actual en 'cards' (current_price_usd / current_price_foil).
        - Upsert en 'card_current_prices' (retail y buylist).
        - Inserción en histórico 'card_price_history'.
        """
        if not events:
            return 0

        db: Session = SessionLocal()
        persisted = 0
        try:
            today_date = date.today()

            for ev in events:
                card_uuid = ev["card_uuid"]
                if card_uuid.startswith("custom_"):
                    continue

                set_code = ev["set_code"]
                finish = ev["finish"]
                retail_val = ev["price_retail"]
                buy_val = ev["price_buy"]

                # 1. Upsert en card_current_prices para 'retail'
                if retail_val > 0:
                    stmt_curr_retail = text("""
                        INSERT INTO card_current_prices 
                            (card_uuid, set_code, provider, game_format, price_type, finish, currency, price, price_date, updated_at)
                        VALUES 
                            (:card_uuid, :set_code, 'cardkingdom', 'paper', 'retail', :finish, 'USD', :price, :price_date, NOW())
                        ON CONFLICT (card_uuid, provider, game_format, price_type, finish, currency)
                        DO UPDATE SET 
                            price = EXCLUDED.price,
                            price_date = EXCLUDED.price_date,
                            updated_at = NOW();
                    """)
                    db.execute(stmt_curr_retail, {
                        "card_uuid": card_uuid,
                        "set_code": set_code,
                        "finish": finish,
                        "price": retail_val,
                        "price_date": today_date
                    })

                # 2. Upsert en card_current_prices para 'buylist'
                if buy_val > 0:
                    stmt_curr_buy = text("""
                        INSERT INTO card_current_prices 
                            (card_uuid, set_code, provider, game_format, price_type, finish, currency, price, price_date, updated_at)
                        VALUES 
                            (:card_uuid, :set_code, 'cardkingdom', 'paper', 'buylist', :finish, 'USD', :price, :price_date, NOW())
                        ON CONFLICT (card_uuid, provider, game_format, price_type, finish, currency)
                        DO UPDATE SET 
                            price = EXCLUDED.price,
                            price_date = EXCLUDED.price_date,
                            updated_at = NOW();
                    """)
                    db.execute(stmt_curr_buy, {
                        "card_uuid": card_uuid,
                        "set_code": set_code,
                        "finish": finish,
                        "price": buy_val,
                        "price_date": today_date
                    })

                # 3. Insertar registro diario en card_price_history
                if retail_val > 0:
                    stmt_hist = text("""
                        INSERT INTO card_price_history 
                            (card_uuid, set_code, provider, game_format, price_type, finish, currency, price_date, price)
                        VALUES 
                            (:card_uuid, :set_code, 'cardkingdom', 'paper', 'retail', :finish, 'USD', :price_date, :price)
                        ON CONFLICT (card_uuid, provider, game_format, price_type, finish, currency, price_date)
                        DO UPDATE SET price = EXCLUDED.price;
                    """)
                    db.execute(stmt_hist, {
                        "card_uuid": card_uuid,
                        "set_code": set_code,
                        "finish": finish,
                        "price_date": today_date,
                        "price": retail_val
                    })

                # 4. Actualizar tabla principal 'cards'
                if finish == "normal" and retail_val > 0:
                    db.execute(text("""
                        UPDATE cards
                        SET current_price_usd = :price,
                            current_price_date = :price_date,
                            current_price_provider = 'cardkingdom',
                            updated_at = NOW()
                        WHERE uuid = :card_uuid;
                    """), {"price": retail_val, "price_date": today_date, "card_uuid": card_uuid})
                elif finish == "foil" and retail_val > 0:
                    db.execute(text("""
                        UPDATE cards
                        SET current_price_foil = :price,
                            current_price_date = :price_date,
                            current_price_provider = 'cardkingdom',
                            updated_at = NOW()
                        WHERE uuid = :card_uuid;
                    """), {"price": retail_val, "price_date": today_date, "card_uuid": card_uuid})

                persisted += 1

            db.commit()
            logger.info(f"Éxito: {persisted} cartas actualizadas en PostgreSQL (tablas cards, current_prices e histórico).")
        except Exception as e:
            db.rollback()
            logger.error(f"Error guardando eventos de precio en la base de datos: {e}")
        finally:
            db.close()

        return persisted

    def run_continuous_stream(self, interval_seconds: int = 1800, max_iterations: Optional[int] = None):
        """
        Bucle continuo tipo Daemon/Worker que ejecuta la ingesta periódicamente.
        """
        iteration = 0
        logger.info(f"Iniciando Worker Continuo de Card Kingdom. Intervalo: {interval_seconds}s...")

        try:
            while True:
                iteration += 1
                logger.info(f"--- [Ciclo #{iteration}] Ejecutando captura de precios ---")
                start_loop = time.time()

                collected_events = []
                for event in self.stream_price_events():
                    collected_events.append(event)
                    
                    # Log visual si hay movimiento de precios o stock disponible
                    delta_str = ""
                    if event["price_delta_retail"] != 0:
                        emoji = "📈" if event["price_delta_retail"] > 0 else "📉"
                        delta_str = f" {emoji} (Δ {event['price_delta_retail']:+.2f})"

                    logger.info(
                        f"⚡ [{event['set_code']}] {event['name']} ({event['finish']}): "
                        f"Retail: ${event['price_retail']:.2f}{delta_str} | "
                        f"Buylist: ${event['price_buy']:.2f} | Stock: {event['qty_retail']}"
                    )

                # Persistencia en base de datos
                if collected_events:
                    self.persist_events_to_db(collected_events)

                elapsed = time.time() - start_loop
                logger.info(f"Ciclo #{iteration} finalizado en {elapsed:.2f}s.")

                if max_iterations and iteration >= max_iterations:
                    logger.info(f"Límite de iteraciones alcanzado ({max_iterations}). Deteniendo.")
                    break

                sleep_time = max(0, interval_seconds - elapsed)
                logger.info(f"Próxima ejecución en {sleep_time:.1f} segundos. Esperando...\n")
                time.sleep(sleep_time)

        except KeyboardInterrupt:
            logger.info("Detención manual solicitada por el usuario (Ctrl+C). Apagando streamer.")


def enable_streaming_for_cards(
    card_uuids: Optional[List[str]] = None,
    set_code: Optional[str] = None,
    rarities: Optional[List[str]] = None,
    collector_numbers: Optional[List[str]] = None
) -> int:
    """
    Habilita el streaming continuo en PostgreSQL marcando is_streaming_enabled = TRUE.
    Soporta:
      - Lista de UUIDs específicos.
      - Set completo o filtrado por rarezas (mythic, rare) y números de coleccionista.
    """
    db: Session = SessionLocal()
    updated_count = 0
    try:
        if card_uuids:
            clean_uuids = [u.strip() for u in card_uuids if u.strip()]
            if clean_uuids:
                stmt = text("""
                    UPDATE cards
                    SET is_streaming_enabled = TRUE,
                        streaming_enabled_at = NOW(),
                        updated_at = NOW()
                    WHERE uuid IN :uuids;
                """)
                res = db.execute(stmt, {"uuids": tuple(clean_uuids)})
                updated_count += res.rowcount

        if set_code:
            code_clean = set_code.strip().upper()
            conditions = ["set_code = :set_code"]
            params: Dict[str, Any] = {"set_code": code_clean}

            if rarities:
                clean_rarities = tuple(r.strip().lower() for r in rarities if r.strip())
                if clean_rarities:
                    conditions.append("LOWER(rarity) IN :rarities")
                    params["rarities"] = clean_rarities

            if collector_numbers:
                clean_numbers = tuple(str(n).strip() for n in collector_numbers if str(n).strip())
                if clean_numbers:
                    conditions.append("collector_number IN :numbers")
                    params["numbers"] = clean_numbers

            where_clause = " AND ".join(conditions)
            stmt = text(f"""
                UPDATE cards
                SET is_streaming_enabled = TRUE,
                    streaming_enabled_at = NOW(),
                    updated_at = NOW()
                WHERE {where_clause};
            """)
            res = db.execute(stmt, params)
            updated_count += res.rowcount

        db.commit()
        logger.info(f"Habilitado streaming para {updated_count} cartas en PostgreSQL.")
    except Exception as e:
        db.rollback()
        logger.error(f"Error habilitando streaming para cartas: {e}")
        raise
    finally:
        db.close()
    return updated_count


def disable_streaming_for_cards(card_uuids: Optional[List[str]] = None, set_code: Optional[str] = None, disable_all: bool = False) -> int:
    """
    Deshabilita el streaming continuo marcando is_streaming_enabled = FALSE.
    Soporta lista de UUIDs, set completo o todas las cartas activas.
    """
    db: Session = SessionLocal()
    updated_count = 0
    try:
        if disable_all:
            stmt = text("""
                UPDATE cards
                SET is_streaming_enabled = FALSE,
                    updated_at = NOW()
                WHERE is_streaming_enabled = TRUE;
            """)
            res = db.execute(stmt)
            updated_count = res.rowcount
        elif card_uuids:
            clean_uuids = [u.strip() for u in card_uuids if u.strip()]
            if clean_uuids:
                stmt = text("""
                    UPDATE cards
                    SET is_streaming_enabled = FALSE,
                        updated_at = NOW()
                    WHERE uuid IN :uuids;
                """)
                res = db.execute(stmt, {"uuids": tuple(clean_uuids)})
                updated_count += res.rowcount
        elif set_code:
            code_clean = set_code.strip().upper()
            stmt = text("""
                UPDATE cards
                SET is_streaming_enabled = FALSE,
                    updated_at = NOW()
                WHERE set_code = :set_code AND is_streaming_enabled = TRUE;
            """)
            res = db.execute(stmt, {"set_code": code_clean})
            updated_count += res.rowcount

        db.commit()
        logger.info(f"Deshabilitado streaming para {updated_count} cartas en PostgreSQL.")
    except Exception as e:
        db.rollback()
        logger.error(f"Error deshabilitando streaming para cartas: {e}")
        raise
    finally:
        db.close()
    return updated_count


def get_active_streaming_cards() -> List[Dict[str, Any]]:
    """
    Obtiene la lista actual de cartas con streaming habilitado en la base de datos.
    """
    db: Session = SessionLocal()
    try:
        rows = db.execute(text("""
            SELECT uuid, set_code, name, rarity, collector_number, streaming_enabled_at
            FROM cards
            WHERE is_streaming_enabled = TRUE
            ORDER BY set_code ASC, name ASC;
        """)).fetchall()
        return [
            {
                "uuid": r[0],
                "set_code": r[1],
                "name": r[2],
                "rarity": r[3],
                "collector_number": r[4],
                "streaming_enabled_at": str(r[5]) if r[5] else None,
            }
            for r in rows
        ]
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Card Kingdom Price Streaming Worker para MythicData")
    parser.add_argument("--set", type=str, default=None, help="Código del set a monitorear (ej: MH3, OTJ, BLB)")
    parser.add_argument("--names", type=str, default=None, help="Nombres separados por comas (ej: 'The One Ring,Black Lotus')")
    parser.add_argument("--interval", type=int, default=1800, help="Intervalo en segundos entre cada captura (default: 1800 / 30m)")
    parser.add_argument("--limit", type=int, default=None, help="Límite máximo de cartas a cargar en el grupo objetivo")
    parser.add_argument("--oneshot", action="store_true", help="Ejecutar una sola vez y terminar (sin loop continuo)")

    args = parser.parse_args()

    names_list = [n.strip() for n in args.names.split(",")] if args.names else None

    streamer = CardKingdomPriceStreamer(
        set_code=args.set,
        card_names=names_list,
        limit_cards=args.limit
    )

    if args.oneshot:
        events = list(streamer.stream_price_events())
        for ev in events:
            print(f"[{ev['set_code']}] {ev['name']} ({ev['finish']}): ${ev['price_retail']}")
        streamer.persist_events_to_db(events)
    else:
        streamer.run_continuous_stream(interval_seconds=args.interval)


if __name__ == "__main__":
    main()
