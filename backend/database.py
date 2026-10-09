import os
import glob
import logging
from typing import Generator
import pandas as pd
from sqlalchemy import create_engine, text, func, inspect
from sqlalchemy.orm import sessionmaker, Session

from backend.config import settings
from backend.models import Base, SetModel, CardModel, CardCurrentPriceModel, CardPriceHistoryModel

logger = logging.getLogger("MTGBackendDB")

# Determinar motor de base de datos
engine = None
is_sqlite = False

try:
    # Intentar conexión a PostgreSQL con timeout corto
    pg_engine = create_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        connect_args={"connect_timeout": 3}
    )
    with pg_engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    engine = pg_engine
    logger.info(f"Conectado exitosamente a PostgreSQL: {settings.POSTGRES_DB}")
except Exception as pg_err:
    logger.warning(f"No se pudo conectar a PostgreSQL ({pg_err}). Usando base de datos SQLite local: {settings.SQLITE_DB_PATH}")
    os.makedirs(os.path.dirname(settings.SQLITE_DB_PATH), exist_ok=True)
    sqlite_url = f"sqlite:///{settings.SQLITE_DB_PATH}"
    engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})
    is_sqlite = True

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """Dependency para inyección de sesiones de base de datos en endpoints FastAPI."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def auto_seed_from_parquet(db: Session):
    """
    Si la base de datos no contiene cartas, importa automáticamente los datos
    desde los archivos Parquet del Data Lake (data/lake/sets y data/lake/cards_prices).
    """
    card_count = db.query(func.count(CardModel.uuid)).scalar() or 0
    if card_count > 0:
        logger.info(f"Base de datos ya contiene {card_count} cartas. No se requiere auto-seeding.")
        return

    logger.info("Base de datos vacía detectada. Iniciando auto-seeding desde Data Lake Parquet...")
    
    # 1. Cargar Sets
    sets_parquet = os.path.join(settings.LAKE_DIR, "sets", "sets.parquet")
    if os.path.exists(sets_parquet):
        try:
            df_sets = pd.read_parquet(sets_parquet)
            for _, row in df_sets.iterrows():
                code = str(row.get("code") or "").strip().upper()
                if not code:
                    continue
                
                existing = db.query(SetModel).filter(SetModel.code == code).first()
                if not existing:
                    release_date = row.get("release_date")
                    if pd.isna(release_date) or release_date is None:
                        rel_date = None
                    else:
                        rel_date = pd.to_datetime(release_date).date() if not hasattr(release_date, "strftime") else release_date

                    s = SetModel(
                        code=code,
                        name=str(row.get("name") or code),
                        release_date=rel_date,
                        base_set_size=int(row.get("base_set_size", 0) or 0) if not pd.isna(row.get("base_set_size")) else 0,
                        total_set_size=int(row.get("total_set_size", 0) or 0) if not pd.isna(row.get("total_set_size")) else 0,
                        set_type=str(row.get("set_type") or "") if not pd.isna(row.get("set_type")) else None,
                        block=str(row.get("block") or "") if not pd.isna(row.get("block")) else None,
                        keyrune_code=str(row.get("keyrune_code") or "") if not pd.isna(row.get("keyrune_code")) else None,
                        is_online_only=bool(row.get("is_online_only", False)),
                        is_foil_only=bool(row.get("is_foil_only", False))
                    )
                    db.add(s)
            db.commit()
            logger.info(f"Sets cargados exitosamente desde {sets_parquet}")
        except Exception as e:
            db.rollback()
            logger.error(f"Error cargando sets desde Parquet: {e}")

    # 2. Cargar Cartas de cada Parquet en data/lake/cards_prices/*.parquet
    cards_parquet_pattern = os.path.join(settings.LAKE_DIR, "cards_prices", "*.parquet")
    card_files = glob.glob(cards_parquet_pattern)
    
    total_cards_imported = 0
    for card_file in card_files:
        try:
            df_cards = pd.read_parquet(card_file)
            for _, row in df_cards.iterrows():
                uuid = str(row.get("uuid") or "").strip()
                if not uuid:
                    continue
                
                set_code = str(row.get("set_code") or "").strip().upper()
                # Asegurar que el set exista
                set_obj = db.query(SetModel).filter(SetModel.code == set_code).first()
                if not set_obj:
                    set_obj = SetModel(code=set_code, name=set_code)
                    db.add(set_obj)
                    db.flush()

                existing_card = db.query(CardModel).filter(CardModel.uuid == uuid).first()
                if not existing_card:
                    cur_date = row.get("current_price_date")
                    if pd.isna(cur_date) or cur_date is None:
                        p_date = None
                    else:
                        p_date = pd.to_datetime(cur_date).date() if not hasattr(cur_date, "strftime") else cur_date

                    mana_v = row.get("mana_value")
                    mana_val = float(mana_v) if not pd.isna(mana_v) and mana_v is not None else 0.0

                    c = CardModel(
                        uuid=uuid,
                        set_code=set_code,
                        name=str(row.get("name") or "Unknown"),
                        collector_number=str(row.get("collector_number") or "") if not pd.isna(row.get("collector_number")) else None,
                        rarity=str(row.get("rarity") or "") if not pd.isna(row.get("rarity")) else None,
                        mana_cost=str(row.get("mana_cost") or "") if not pd.isna(row.get("mana_cost")) else None,
                        mana_value=mana_val,
                        type_line=str(row.get("type_line") or "") if not pd.isna(row.get("type_line")) else None,
                        scryfall_id=str(row.get("scryfall_id") or "") if not pd.isna(row.get("scryfall_id")) else None,
                        tcgplayer_product_id=str(row.get("tcgplayer_product_id") or "") if not pd.isna(row.get("tcgplayer_product_id")) else None,
                        finishes=str(row.get("finishes") or "") if not pd.isna(row.get("finishes")) else None,
                        artist=str(row.get("artist") or "") if not pd.isna(row.get("artist")) else None,
                        availability=str(row.get("availability") or "") if not pd.isna(row.get("availability")) else None,
                        current_price_usd=float(row.get("current_price_usd")) if not pd.isna(row.get("current_price_usd")) and row.get("current_price_usd") is not None else None,
                        current_price_eur=float(row.get("current_price_eur")) if not pd.isna(row.get("current_price_eur")) and row.get("current_price_eur") is not None else None,
                        current_price_foil=float(row.get("current_price_foil")) if not pd.isna(row.get("current_price_foil")) and row.get("current_price_foil") is not None else None,
                        current_price_date=p_date,
                        current_price_provider=str(row.get("current_price_provider") or "") if not pd.isna(row.get("current_price_provider")) else None
                    )
                    db.add(c)
                    total_cards_imported += 1

            db.commit()
            logger.info(f"Cartas del set importadas desde {card_file}")
        except Exception as e:
            db.rollback()
            logger.error(f"Error importando cartas de {card_file}: {e}")

    logger.info(f"Auto-seeding completado: {total_cards_imported} cartas cargadas en base de datos.")


def init_db():
    """Crea todas las tablas si no existen e inicializa datos si es necesario."""
    # Migraciones seguras para PostgreSQL si la tabla ya existía
    if not is_sqlite:
        with engine.connect() as conn:
            migration_statements = [
                "ALTER TABLE cards ADD COLUMN IF NOT EXISTS oracle_text TEXT;",
                "ALTER TABLE cards ADD COLUMN IF NOT EXISTS colors VARCHAR(50);",
                "ALTER TABLE cards ADD COLUMN IF NOT EXISTS color_identity VARCHAR(50);",
                "ALTER TABLE cards ADD COLUMN IF NOT EXISTS power VARCHAR(20);",
                "ALTER TABLE cards ADD COLUMN IF NOT EXISTS toughness VARCHAR(20);",
                "ALTER TABLE cards ADD COLUMN IF NOT EXISTS loyalty VARCHAR(20);",
                "ALTER TABLE cards ADD COLUMN IF NOT EXISTS current_price_usd NUMERIC(12,4);",
                "ALTER TABLE cards ADD COLUMN IF NOT EXISTS current_price_eur NUMERIC(12,4);",
                "ALTER TABLE cards ADD COLUMN IF NOT EXISTS current_price_foil NUMERIC(12,4);",
                "ALTER TABLE cards ADD COLUMN IF NOT EXISTS current_price_date DATE;",
                "ALTER TABLE cards ADD COLUMN IF NOT EXISTS current_price_provider VARCHAR(50);"
            ]
            for stmt in migration_statements:
                try:
                    conn.execute(text(stmt))
                    if hasattr(conn, "commit"):
                        conn.commit()
                except Exception:
                    pass

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        auto_seed_from_parquet(db)
    finally:
        db.close()
