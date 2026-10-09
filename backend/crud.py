import math
from datetime import datetime, timedelta, date
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy import func, or_, and_, desc, asc
from sqlalchemy.orm import Session, joinedload

from backend.models import CardModel, SetModel, CardCurrentPriceModel, CardPriceHistoryModel
from backend.schemas import (
    CardSummary,
    CardDetail,
    SetSummary,
    PricePoint,
    PriceHistoryItem,
    PriceStats,
    CardPriceHistoryResponse,
    FilterMetadata,
    PaginatedResponse
)


def get_scryfall_image_urls(scryfall_id: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """Genera URLs seguras para imágenes de Scryfall (versión normal y grande)."""
    if not scryfall_id or len(scryfall_id) < 5:
        return None, None
    normal_url = f"https://api.scryfall.com/cards/{scryfall_id}?format=image&version=normal"
    large_url = f"https://api.scryfall.com/cards/{scryfall_id}?format=image&version=large"
    return normal_url, large_url


def get_cards_paginated(
    db: Session,
    q: Optional[str] = None,
    oracle_text: Optional[str] = None,
    colors: Optional[List[str]] = None,
    card_type: Optional[str] = None,
    rarity: Optional[str] = None,
    mana_value_min: Optional[float] = None,
    mana_value_max: Optional[float] = None,
    set_code: Optional[str] = None,
    has_price: Optional[bool] = None,
    price_min: Optional[float] = None,
    price_max: Optional[float] = None,
    sort_by: str = "name",
    order: str = "asc",
    page: int = 1,
    page_size: int = 24
) -> PaginatedResponse[CardSummary]:
    """
    Consulta cartas aplicando filtros dinámicos, búsqueda por texto, ordenamiento y paginación.
    """
    query = db.query(CardModel).join(SetModel, CardModel.set_code == SetModel.code)

    # 1. Filtro por búsqueda de texto (Nombre)
    if q and q.strip():
        search_term = f"%{q.strip()}%"
        query = query.filter(
            or_(
                CardModel.name.ilike(search_term),
                CardModel.type_line.ilike(search_term),
                CardModel.oracle_text.ilike(search_term) if hasattr(CardModel, "oracle_text") else False
            )
        )

    # 2. Filtro por Oracle Text
    if oracle_text and oracle_text.strip() and hasattr(CardModel, "oracle_text"):
        query = query.filter(CardModel.oracle_text.ilike(f"%{oracle_text.strip()}%"))

    # 3. Filtro por Set
    if set_code and set_code.strip() and set_code.strip().upper() != "ALL":
        query = query.filter(CardModel.set_code == set_code.strip().upper())

    # 4. Filtro por Tipo de Carta
    if card_type and card_type.strip() and card_type.strip().lower() != "all":
        query = query.filter(CardModel.type_line.ilike(f"%{card_type.strip()}%"))

    # 5. Filtro por Rareza
    if rarity and rarity.strip() and rarity.strip().lower() != "all":
        query = query.filter(func.lower(CardModel.rarity) == rarity.strip().lower())

    # 6. Filtro por Colores (basado en mana_cost o columna colors)
    if colors and len(colors) > 0:
        color_filters = []
        for c in colors:
            c_clean = c.strip().upper()
            if c_clean == "C":  # Incoloro
                color_filters.append(
                    or_(
                        CardModel.mana_cost.is_(None),
                        and_(
                            ~CardModel.mana_cost.ilike("%W%"),
                            ~CardModel.mana_cost.ilike("%U%"),
                            ~CardModel.mana_cost.ilike("%B%"),
                            ~CardModel.mana_cost.ilike("%R%"),
                            ~CardModel.mana_cost.ilike("%G%")
                        )
                    )
                )
            else:
                color_filters.append(CardModel.mana_cost.ilike(f"%{c_clean}%"))
        
        if color_filters:
            query = query.filter(or_(*color_filters))

    # 7. Filtro por Rango de Coste de Maná Convertido (CMC / Mana Value)
    if mana_value_min is not None:
        query = query.filter(CardModel.mana_value >= mana_value_min)
    if mana_value_max is not None:
        query = query.filter(CardModel.mana_value <= mana_value_max)

    # 8. Filtro por Disponibilidad de Precio
    if has_price is True:
        query = query.filter(
            or_(
                CardModel.current_price_usd.isnot(None),
                CardModel.current_price_eur.isnot(None),
                CardModel.current_price_foil.isnot(None)
            )
        )

    # 9. Filtro por Rango de Precios
    if price_min is not None:
        query = query.filter(
            or_(
                CardModel.current_price_usd >= price_min,
                CardModel.current_price_eur >= price_min
            )
        )
    if price_max is not None:
        query = query.filter(
            or_(
                and_(CardModel.current_price_usd.isnot(None), CardModel.current_price_usd <= price_max),
                and_(CardModel.current_price_eur.isnot(None), CardModel.current_price_eur <= price_max)
            )
        )

    # Total de registros coincidentes
    total = query.count()

    # 10. Ordenamiento
    is_desc = order.lower() == "desc"
    sort_key = sort_by.lower()

    if sort_key in ("price", "current_price_usd", "price_usd"):
        order_col = CardModel.current_price_usd
    elif sort_key in ("mana_value", "cmc"):
        order_col = CardModel.mana_value
    elif sort_key in ("release_date", "date"):
        order_col = SetModel.release_date
    elif sort_key in ("collector_number", "number"):
        order_col = CardModel.collector_number
    else:
        order_col = CardModel.name

    if is_desc:
        query = query.order_by(order_col.desc().nullslast(), CardModel.name.asc())
    else:
        query = query.order_by(order_col.asc().nullslast(), CardModel.name.asc())

    # 11. Paginación
    page = max(1, page)
    page_size = max(1, min(100, page_size))
    offset = (page - 1) * page_size
    total_pages = math.ceil(total / page_size) if total > 0 else 1

    cards_rows = query.options(joinedload(CardModel.set_rel)).offset(offset).limit(page_size).all()

    items: List[CardSummary] = []
    for c in cards_rows:
        img_norm, img_large = get_scryfall_image_urls(c.scryfall_id)
        set_name = c.set_rel.name if c.set_rel else c.set_code

        items.append(
            CardSummary(
                uuid=c.uuid,
                set_code=c.set_code,
                set_name=set_name,
                name=c.name,
                collector_number=c.collector_number,
                rarity=c.rarity,
                mana_cost=c.mana_cost,
                mana_value=float(c.mana_value) if c.mana_value is not None else 0.0,
                type_line=c.type_line,
                scryfall_id=c.scryfall_id,
                image_url=img_norm,
                image_url_large=img_large,
                current_price_usd=float(c.current_price_usd) if c.current_price_usd is not None else None,
                current_price_eur=float(c.current_price_eur) if c.current_price_eur is not None else None,
                current_price_foil=float(c.current_price_foil) if c.current_price_foil is not None else None,
                current_price_date=c.current_price_date,
                current_price_provider=c.current_price_provider
            )
        )

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


def get_card_detail_by_uuid(db: Session, uuid: str) -> Optional[CardDetail]:
    """Obtiene el detalle completo de una carta por su UUID."""
    card = db.query(CardModel).options(
        joinedload(CardModel.set_rel),
        joinedload(CardModel.current_prices)
    ).filter(CardModel.uuid == uuid).first()

    if not card:
        return None

    img_norm, img_large = get_scryfall_image_urls(card.scryfall_id)
    set_name = card.set_rel.name if card.set_rel else card.set_code

    # Formatear lista de precios actuales ordenada por precio ascendente
    prices_list: List[PricePoint] = []
    if card.current_prices:
        sorted_prices = sorted(card.current_prices, key=lambda x: (float(x.price) if x.price is not None else 999999))
        for p in sorted_prices:
            prices_list.append(
                PricePoint(
                    provider=p.provider,
                    game_format=p.game_format,
                    price_type=p.price_type,
                    finish=p.finish,
                    currency=p.currency,
                    price=float(p.price),
                    price_date=p.price_date
                )
            )

    # Consultar historial de precios completo con estadísticas de cambio
    history_resp = get_card_price_history_filtered(db, uuid=uuid)

    # Información del set
    set_info = None
    if card.set_rel:
        set_info = SetSummary(
            code=card.set_rel.code,
            name=card.set_rel.name,
            release_date=card.set_rel.release_date,
            total_set_size=card.set_rel.total_set_size or 0,
            set_type=card.set_rel.set_type,
            keyrune_code=card.set_rel.keyrune_code,
            is_online_only=bool(card.set_rel.is_online_only),
            is_foil_only=bool(card.set_rel.is_foil_only),
            card_count=len(card.set_rel.cards) if card.set_rel.cards else 0
        )

    return CardDetail(
        uuid=card.uuid,
        set_code=card.set_code,
        set_name=set_name,
        name=card.name,
        collector_number=card.collector_number,
        rarity=card.rarity,
        mana_cost=card.mana_cost,
        mana_value=float(card.mana_value) if card.mana_value is not None else 0.0,
        type_line=card.type_line,
        oracle_text=card.oracle_text if hasattr(card, "oracle_text") else None,
        colors=card.colors if hasattr(card, "colors") else None,
        color_identity=card.color_identity if hasattr(card, "color_identity") else None,
        power=card.power if hasattr(card, "power") else None,
        toughness=card.toughness if hasattr(card, "toughness") else None,
        loyalty=card.loyalty if hasattr(card, "loyalty") else None,
        scryfall_id=card.scryfall_id,
        tcgplayer_product_id=card.tcgplayer_product_id,
        finishes=card.finishes,
        artist=card.artist,
        availability=card.availability,
        image_url=img_norm,
        image_url_large=img_large,
        current_price_usd=float(card.current_price_usd) if card.current_price_usd is not None else None,
        current_price_eur=float(card.current_price_eur) if card.current_price_eur is not None else None,
        current_price_foil=float(card.current_price_foil) if card.current_price_foil is not None else None,
        current_price_date=card.current_price_date,
        current_price_provider=card.current_price_provider,
        prices=prices_list,
        recent_history=history_resp.history,
        price_stats=history_resp.stats,
        set_info=set_info
    )


def get_card_price_history_filtered(
    db: Session,
    uuid: str,
    provider: Optional[str] = None,
    game_format: Optional[str] = None,
    price_type: Optional[str] = None,
    finish: Optional[str] = None,
    currency: Optional[str] = None,
    days: Optional[int] = None
) -> CardPriceHistoryResponse:
    """
    Obtiene la serie temporal de precios y estadísticas de cambio (variación absoluta y porcentual)
    para una carta, filtrando dinámicamente por tienda, acabado, formato y ventana de días.
    """
    card = db.query(CardModel).filter(CardModel.uuid == uuid).first()
    if not card:
        return CardPriceHistoryResponse(
            card_uuid=uuid,
            card_name="Unknown",
            set_code="",
            stats=PriceStats(),
            history=[],
            available_filters={"providers": [], "finishes": [], "currencies": [], "price_types": []}
        )

    # 1. Extraer filtros disponibles únicos para esta carta
    all_raw_history = db.query(
        CardPriceHistoryModel.provider,
        CardPriceHistoryModel.finish,
        CardPriceHistoryModel.currency,
        CardPriceHistoryModel.price_type,
        CardPriceHistoryModel.game_format
    ).filter(CardPriceHistoryModel.card_uuid == uuid).distinct().all()

    unique_providers = sorted(list({r.provider for r in all_raw_history if r.provider}))
    unique_finishes = sorted(list({r.finish for r in all_raw_history if r.finish}))
    unique_currencies = sorted(list({r.currency for r in all_raw_history if r.currency}))
    unique_price_types = sorted(list({r.price_type for r in all_raw_history if r.price_type}))

    # 2. Construir consulta con filtros dinámicos
    q = db.query(CardPriceHistoryModel).filter(CardPriceHistoryModel.card_uuid == uuid)

    if provider and provider.strip().lower() != "all":
        q = q.filter(func.lower(CardPriceHistoryModel.provider) == provider.strip().lower())
    if finish and finish.strip().lower() != "all":
        q = q.filter(func.lower(CardPriceHistoryModel.finish) == finish.strip().lower())
    if currency and currency.strip().upper() != "ALL":
        q = q.filter(func.upper(CardPriceHistoryModel.currency) == currency.strip().upper())
    if price_type and price_type.strip().lower() != "all":
        q = q.filter(func.lower(CardPriceHistoryModel.price_type) == price_type.strip().lower())
    if game_format and game_format.strip().lower() != "all":
        q = q.filter(func.lower(CardPriceHistoryModel.game_format) == game_format.strip().lower())
    if days and days > 0:
        cutoff_date = date.today() - timedelta(days=days)
        q = q.filter(CardPriceHistoryModel.price_date >= cutoff_date)

    # Ordenar cronológicamente para calcular variaciones día a día
    records = q.order_by(CardPriceHistoryModel.price_date.asc(), CardPriceHistoryModel.provider.asc()).all()

    # 3. Calcular variaciones históricas y estadísticas de cambio
    history_items: List[PriceHistoryItem] = []
    prices_by_series: Dict[Tuple[str, str, str, str], float] = {}

    all_prices_values = []
    latest_price = None
    prev_price_val = None

    for r in records:
        price_val = float(r.price)
        all_prices_values.append(price_val)
        
        series_key = (r.provider, r.finish, r.currency, r.price_type)
        prev_p = prices_by_series.get(series_key)
        
        diff = None
        pct = None
        if prev_p is not None and prev_p > 0:
            diff = round(price_val - prev_p, 4)
            pct = round(((price_val - prev_p) / prev_p) * 100.0, 2)
            prev_price_val = prev_p
        
        prices_by_series[series_key] = price_val
        latest_price = price_val

        history_items.append(
            PriceHistoryItem(
                provider=r.provider,
                game_format=r.game_format,
                price_type=r.price_type,
                finish=r.finish,
                currency=r.currency,
                price_date=r.price_date,
                price=price_val,
                previous_price=prev_p,
                price_diff=diff,
                pct_change=pct
            )
        )

    # 4. Calcular métricas estadísticas agregadas
    stats = PriceStats()
    if all_prices_values:
        stats.total_points = len(all_prices_values)
        stats.current_price = latest_price
        stats.previous_price = prev_price_val
        stats.min_price = min(all_prices_values)
        stats.max_price = max(all_prices_values)
        stats.avg_price = round(sum(all_prices_values) / len(all_prices_values), 2)
        
        if prev_price_val is not None and prev_price_val > 0 and latest_price is not None:
            stats.price_diff = round(latest_price - prev_price_val, 4)
            stats.pct_change = round(((latest_price - prev_price_val) / prev_price_val) * 100.0, 2)
            if stats.price_diff > 0.01:
                stats.trend = "up"
            elif stats.price_diff < -0.01:
                stats.trend = "down"
            else:
                stats.trend = "stable"

    return CardPriceHistoryResponse(
        card_uuid=card.uuid,
        card_name=card.name,
        set_code=card.set_code,
        stats=stats,
        history=history_items,
        available_filters={
            "providers": unique_providers,
            "finishes": unique_finishes,
            "currencies": unique_currencies,
            "price_types": unique_price_types
        }
    )


def get_filter_metadata(db: Session) -> FilterMetadata:
    """Retorna metadatos agregados para alimentar los selectores y filtros del frontend."""
    # 1. Sets disponibles con conteo de cartas
    sets_query = db.query(
        SetModel.code,
        SetModel.name,
        SetModel.release_date,
        SetModel.total_set_size,
        SetModel.set_type,
        SetModel.keyrune_code,
        SetModel.is_online_only,
        SetModel.is_foil_only,
        func.count(CardModel.uuid).label("card_count")
    ).outerjoin(CardModel, SetModel.code == CardModel.set_code)\
     .group_by(SetModel.code)\
     .order_by(SetModel.release_date.desc().nullslast(), SetModel.name.asc())\
     .all()

    sets_list: List[SetSummary] = []
    for s in sets_query:
        sets_list.append(
            SetSummary(
                code=s.code,
                name=s.name,
                release_date=s.release_date,
                total_set_size=s.total_set_size or 0,
                set_type=s.set_type,
                keyrune_code=s.keyrune_code,
                is_online_only=bool(s.is_online_only),
                is_foil_only=bool(s.is_foil_only),
                card_count=s.card_count or 0
            )
        )

    # 2. Tipos de Cartas principales
    types_list = [
        "Creature",
        "Instant",
        "Sorcery",
        "Enchantment",
        "Artifact",
        "Land",
        "Planeswalker",
        "Battle"
    ]

    # 3. Rarezas
    rarities_list = ["Common", "Uncommon", "Rare", "Mythic", "Special"]

    # 4. Colores MTG con nombres y símbolos
    colors_list = [
        {"code": "W", "name": "White (Blanco)", "symbol": "{W}"},
        {"code": "U", "name": "Blue (Azul)", "symbol": "{U}"},
        {"code": "B", "name": "Black (Negro)", "symbol": "{B}"},
        {"code": "R", "name": "Red (Rojo)", "symbol": "{R}"},
        {"code": "G", "name": "Green (Verde)", "symbol": "{G}"},
        {"code": "C", "name": "Colorless (Incoloro)", "symbol": "{C}"},
    ]

    # 5. Estadísticas de Precios
    min_price = db.query(func.min(CardModel.current_price_usd)).filter(CardModel.current_price_usd > 0).scalar()
    max_price = db.query(func.max(CardModel.current_price_usd)).scalar()
    avg_price = db.query(func.avg(CardModel.current_price_usd)).scalar()
    total_cards = db.query(func.count(CardModel.uuid)).scalar() or 0

    price_stats = {
        "min_usd": float(min_price) if min_price is not None else 0.0,
        "max_usd": float(max_price) if max_price is not None else 100.0,
        "avg_usd": float(avg_price) if avg_price is not None else 1.0,
    }

    return FilterMetadata(
        sets=sets_list,
        types=types_list,
        rarities=rarities_list,
        colors=colors_list,
        price_stats=price_stats,
        total_cards_count=total_cards
    )
