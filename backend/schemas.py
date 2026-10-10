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


class CardPricePrediction(BaseModel):
    card_uuid: str
    current_price: Optional[float] = None
    predicted_next_price: Optional[float] = None
    expected_change_pct: Optional[float] = None
    direction: Optional[str] = None
    confidence_score: Optional[float] = None
    model_name: str = "GBTRegressor"
    features_used: Optional[str] = None
    predicted_at: Optional[datetime] = None

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
    prediction: Optional[CardPricePrediction] = None

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


# ==============================================================================
# Modelos para Ingesta de Datos, Pipelines Airflow y Trazas Jaeger
# ==============================================================================

class IngestionTriggerRequest(BaseModel):
    dag_id: str = "selected_set_ingestion"
    set_codes: List[str] = Field(default_factory=lambda: ["MH3", "FDN"])
    load_history: bool = False


class IngestionTriggerResponse(BaseModel):
    dag_id: str
    dag_run_id: str
    state: str
    logical_date: Optional[str] = None
    conf: Dict[str, Any] = Field(default_factory=dict)
    message: str
    airflow_url: str


class TaskInstanceItem(BaseModel):
    task_id: str
    state: Optional[str] = None
    duration: Optional[float] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    try_number: int = 1


class IngestionStatusResponse(BaseModel):
    dag_id: str
    dag_run_id: str
    state: str
    progress_percent: int
    current_step: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    execution_date: Optional[str] = None
    conf: Dict[str, Any] = Field(default_factory=dict)
    tasks: List[TaskInstanceItem] = Field(default_factory=list)
    airflow_url: str
    jaeger_url: str
    latest_trace_id: Optional[str] = None


class IngestionLogResponse(BaseModel):
    dag_id: str
    dag_run_id: str
    task_id: str
    log: str
    jaeger_trace_id: Optional[str] = None
    jaeger_trace_url: Optional[str] = None


class IngestionConfigResponse(BaseModel):
    available_dags: List[Dict[str, Any]]
    available_sets: List[Dict[str, str]]
    airflow_connected: bool
    jaeger_connected: bool
    airflow_web_url: str
    jaeger_ui_url: str


class IngestionHistoryItem(BaseModel):
    dag_id: str
    dag_run_id: str
    state: str
    progress_percent: int
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    conf: Dict[str, Any] = Field(default_factory=dict)
    run_type: Optional[str] = None
    airflow_url: str
    jaeger_trace_id: Optional[str] = None
    jaeger_url: Optional[str] = None


class IngestionHistoryResponse(BaseModel):
    runs: List[IngestionHistoryItem]
    total: int


class JaegerTraceSummary(BaseModel):
    trace_id: str
    operation_name: str
    duration_ms: float
    start_time: str
    spans_count: int
    jaeger_url: str


class JaegerTracesResponse(BaseModel):
    traces: List[JaegerTraceSummary]
    total: int
