export interface PricePoint {
  provider: string;
  game_format: string;
  price_type: string;
  finish: string;
  currency: string;
  price: number;
  price_date: string;
}

export interface PriceHistoryItem {
  provider: string;
  game_format: string;
  price_type: string;
  finish: string;
  currency: string;
  price_date: string;
  price: number;
  previous_price?: number;
  price_diff?: number;
  pct_change?: number;
}

export interface PriceStats {
  current_price?: number;
  previous_price?: number;
  price_diff?: number;
  pct_change?: number;
  min_price?: number;
  max_price?: number;
  avg_price?: number;
  trend: 'up' | 'down' | 'stable';
  total_points: number;
}

export interface CardPriceHistoryResponse {
  card_uuid: string;
  card_name: string;
  set_code: string;
  stats: PriceStats;
  history: PriceHistoryItem[];
  available_filters: {
    providers: string[];
    finishes: string[];
    currencies: string[];
    price_types: string[];
  };
}

export interface SetSummary {
  code: string;
  name: string;
  release_date?: string;
  total_set_size?: number;
  set_type?: string;
  keyrune_code?: string;
  is_online_only?: boolean;
  is_foil_only?: boolean;
  card_count?: number;
}

export interface CardSummary {
  uuid: string;
  set_code: string;
  set_name?: string;
  name: string;
  collector_number?: string;
  rarity?: string;
  mana_cost?: string;
  mana_value?: number;
  type_line?: string;
  scryfall_id?: string;
  image_url?: string;
  image_url_large?: string;
  current_price_usd?: number;
  current_price_eur?: number;
  current_price_foil?: number;
  current_price_date?: string;
  current_price_provider?: string;
}

export interface CardPricePrediction {
  card_uuid: string;
  current_price?: number;
  predicted_next_price?: number;
  expected_change_pct?: number;
  direction?: 'UP' | 'DOWN' | 'STABLE' | string;
  confidence_score?: number;
  model_name?: string;
  features_used?: string;
  predicted_at?: string;
}

export interface CardDetail extends CardSummary {
  oracle_text?: string;
  colors?: string;
  color_identity?: string;
  power?: string;
  toughness?: string;
  loyalty?: string;
  tcgplayer_product_id?: string;
  finishes?: string;
  artist?: string;
  availability?: string;
  prices: PricePoint[];
  recent_history: PriceHistoryItem[];
  price_stats?: PriceStats;
  set_info?: SetSummary;
  prediction?: CardPricePrediction;
}

export interface FilterColor {
  code: string;
  name: string;
  symbol: string;
}

export interface FilterMetadata {
  sets: SetSummary[];
  types: string[];
  rarities: string[];
  colors: FilterColor[];
  price_stats: {
    min_usd?: number;
    max_usd?: number;
    avg_usd?: number;
  };
  total_cards_count: number;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface CardFilterParams {
  q?: string;
  oracle_text?: string;
  colors?: string[];
  card_type?: string;
  rarity?: string;
  mana_value_min?: number;
  mana_value_max?: number;
  set_code?: string;
  has_price?: boolean;
  price_min?: number;
  price_max?: number;
  sort_by?: string;
  order?: 'asc' | 'desc';
  page?: number;
  page_size?: number;
}

export interface PriceHistoryFilterParams {
  provider?: string;
  game_format?: string;
  price_type?: string;
  finish?: string;
  currency?: string;
  days?: number;
}
