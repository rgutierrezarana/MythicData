from datetime import date, datetime
from typing import List, Optional, Generic, TypeVar, Dict, Any
from pydantic import BaseModel, Field

T = TypeVar("T")


class PricePoint(BaseModel):
    provider: str
    game_format: str
    price_type: str
    finish: str
    currency: str
    price: float
    price_date: date

    class Config:
        from_attributes = True


class PriceHistoryItem(BaseModel):
    provider: str
    game_format: str
    price_type: str
    finish: str
    currency: str
    price_date: date
    price: float
    previous_price: Optional[float] = None
    price_diff: Optional[float] = None
    pct_change: Optional[float] = None

    class Config:
        from_attributes = True


class PriceStats(BaseModel):
    current_price: Optional[float] = None
    previous_price: Optional[float] = None
    price_diff: Optional[float] = None
    pct_change: Optional[float] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    avg_price: Optional[float] = None
    trend: str = "stable"  # "up", "down", "stable"
    total_points: int = 0


class CardPriceHistoryResponse(BaseModel):
    card_uuid: str
    card_name: str
    set_code: str
    stats: PriceStats
    history: List[PriceHistoryItem]
    available_filters: Dict[str, List[str]]


class SetSummary(BaseModel):
    code: str
    name: str
    release_date: Optional[date] = None
    total_set_size: Optional[int] = 0
    set_type: Optional[str] = None
    keyrune_code: Optional[str] = None
    is_online_only: bool = False
    is_foil_only: bool = False
    card_count: Optional[int] = 0

    class Config:
        from_attributes = True


class CardSummary(BaseModel):
    uuid: str
    set_code: str
    set_name: Optional[str] = None
    name: str
    collector_number: Optional[str] = None
    rarity: Optional[str] = None
    mana_cost: Optional[str] = None
    mana_value: Optional[float] = 0.0
    type_line: Optional[str] = None
    scryfall_id: Optional[str] = None
    image_url: Optional[str] = None
    image_url_large: Optional[str] = None
    current_price_usd: Optional[float] = None
    current_price_eur: Optional[float] = None
    current_price_foil: Optional[float] = None
    current_price_date: Optional[date] = None
    current_price_provider: Optional[str] = None

    class Config:
        from_attributes = True


class CardDetail(CardSummary):
    oracle_text: Optional[str] = None
    colors: Optional[str] = None
    color_identity: Optional[str] = None
    power: Optional[str] = None
    toughness: Optional[str] = None
    loyalty: Optional[str] = None
    tcgplayer_product_id: Optional[str] = None
    finishes: Optional[str] = None
    artist: Optional[str] = None
    availability: Optional[str] = None
    prices: List[PricePoint] = Field(default_factory=list)
    recent_history: List[PriceHistoryItem] = Field(default_factory=list)
    price_stats: Optional[PriceStats] = None
    set_info: Optional[SetSummary] = None

    class Config:
        from_attributes = True


class FilterColor(BaseModel):
    code: str
    name: str
    symbol: str


class FilterMetadata(BaseModel):
    sets: List[SetSummary]
    types: List[str]
    rarities: List[str]
    colors: List[Dict[str, str]]
    price_stats: Dict[str, Optional[float]]
    total_cards_count: int


class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    page_size: int
    total_pages: int
