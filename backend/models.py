from datetime import datetime, date
from sqlalchemy import (
    Column,
    String,
    Integer,
    Numeric,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Text,
    BigInteger,
    UniqueConstraint
)
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


class SetModel(Base):
    __tablename__ = "sets"

    code = Column(String(10), primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    release_date = Column(Date, nullable=True, index=True)
    base_set_size = Column(Integer, nullable=True)
    total_set_size = Column(Integer, nullable=True)
    set_type = Column(String(50), nullable=True, index=True)
    block = Column(String(100), nullable=True)
    keyrune_code = Column(String(50), nullable=True)
    is_online_only = Column(Boolean, default=False)
    is_foil_only = Column(Boolean, default=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relación con cartas
    cards = relationship("CardModel", back_populates="set_rel", cascade="all, delete-orphan")


class CardModel(Base):
    __tablename__ = "cards"

    uuid = Column(String(64), primary_key=True, index=True)
    set_code = Column(String(10), ForeignKey("sets.code", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False, index=True)
    collector_number = Column(String(50), nullable=True)
    rarity = Column(String(50), nullable=True, index=True)
    mana_cost = Column(String(100), nullable=True)
    mana_value = Column(Numeric(10, 2), nullable=True, index=True)
    type_line = Column(String(255), nullable=True, index=True)
    oracle_text = Column(Text, nullable=True)
    colors = Column(String(50), nullable=True)
    color_identity = Column(String(50), nullable=True)
    power = Column(String(20), nullable=True)
    toughness = Column(String(20), nullable=True)
    loyalty = Column(String(20), nullable=True)
    scryfall_id = Column(String(64), nullable=True, index=True)
    tcgplayer_product_id = Column(String(64), nullable=True, index=True)
    finishes = Column(String(100), nullable=True)
    artist = Column(String(255), nullable=True)
    availability = Column(String(100), nullable=True)
    
    # Snapshot de precios actuales calculados
    current_price_usd = Column(Numeric(12, 4), nullable=True, index=True)
    current_price_eur = Column(Numeric(12, 4), nullable=True)
    current_price_foil = Column(Numeric(12, 4), nullable=True)
    current_price_date = Column(Date, nullable=True, index=True)
    current_price_provider = Column(String(50), nullable=True)
    is_streaming_enabled = Column(Boolean, default=False, index=True)
    streaming_enabled_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relaciones
    set_rel = relationship("SetModel", back_populates="cards")
    current_prices = relationship("CardCurrentPriceModel", back_populates="card_rel", cascade="all, delete-orphan")
    price_history = relationship("CardPriceHistoryModel", back_populates="card_rel", cascade="all, delete-orphan")


class CardCurrentPriceModel(Base):
    __tablename__ = "card_current_prices"

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    card_uuid = Column(String(64), ForeignKey("cards.uuid", ondelete="CASCADE"), nullable=False, index=True)
    set_code = Column(String(10), nullable=False, index=True)
    provider = Column(String(50), nullable=False, index=True)
    game_format = Column(String(20), nullable=False)
    price_type = Column(String(20), nullable=False)
    finish = Column(String(20), nullable=False)
    currency = Column(String(10), nullable=False)
    price = Column(Numeric(12, 4), nullable=False)
    price_date = Column(Date, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("card_uuid", "provider", "game_format", "price_type", "finish", "currency", name="uq_card_current_price"),
    )

    card_rel = relationship("CardModel", back_populates="current_prices")


class CardPriceHistoryModel(Base):
    __tablename__ = "card_price_history"

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    card_uuid = Column(String(64), ForeignKey("cards.uuid", ondelete="CASCADE"), nullable=False, index=True)
    set_code = Column(String(10), nullable=False, index=True)
    provider = Column(String(50), nullable=False, index=True)
    game_format = Column(String(20), nullable=False)
    price_type = Column(String(20), nullable=False)
    finish = Column(String(20), nullable=False)
    currency = Column(String(10), nullable=False)
    price_date = Column(Date, nullable=False, index=True)
    price = Column(Numeric(12, 4), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("card_uuid", "provider", "game_format", "price_type", "finish", "currency", "price_date", name="uq_card_price_history"),
    )

    card_rel = relationship("CardModel", back_populates="price_history")
