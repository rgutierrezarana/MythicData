import {
  CardSummary,
  CardDetail,
  FilterMetadata,
  PaginatedResponse,
  CardFilterParams,
  CardPriceHistoryResponse,
  PriceHistoryFilterParams
} from '../types/card';

const API_BASE = '/api/v1';

export async function fetchCards(
  params: CardFilterParams,
  signal?: AbortSignal
): Promise<PaginatedResponse<CardSummary>> {
  const query = new URLSearchParams();

  if (params.q) query.set('q', params.q);
  if (params.oracle_text) query.set('oracle_text', params.oracle_text);
  if (params.colors && params.colors.length > 0) query.set('colors', params.colors.join(','));
  if (params.card_type && params.card_type !== 'All') query.set('card_type', params.card_type);
  if (params.rarity && params.rarity !== 'All') query.set('rarity', params.rarity);
  if (params.set_code && params.set_code !== 'ALL') query.set('set_code', params.set_code);
  if (params.mana_value_min !== undefined) query.set('mana_value_min', params.mana_value_min.toString());
  if (params.mana_value_max !== undefined) query.set('mana_value_max', params.mana_value_max.toString());
  if (params.has_price !== undefined && params.has_price !== false) query.set('has_price', 'true');
  if (params.price_min !== undefined) query.set('price_min', params.price_min.toString());
  if (params.price_max !== undefined) query.set('price_max', params.price_max.toString());
  if (params.sort_by) query.set('sort_by', params.sort_by);
  if (params.order) query.set('order', params.order);
  if (params.page) query.set('page', params.page.toString());
  if (params.page_size) query.set('page_size', params.page_size.toString());

  const res = await fetch(`${API_BASE}/cards?${query.toString()}`, { signal });
  if (!res.ok) {
    throw new Error(`Error al consultar cartas (${res.status}): ${res.statusText}`);
  }
  return res.json();
}

export async function fetchCardDetail(
  uuid: string,
  signal?: AbortSignal
): Promise<CardDetail> {
  const res = await fetch(`${API_BASE}/cards/${uuid}`, { signal });
  if (!res.ok) {
    throw new Error(`Error al consultar detalle de carta (${res.status}): ${res.statusText}`);
  }
  return res.json();
}

export async function fetchCardPriceHistory(
  uuid: string,
  params?: PriceHistoryFilterParams,
  signal?: AbortSignal
): Promise<CardPriceHistoryResponse> {
  const query = new URLSearchParams();

  if (params?.provider && params.provider.toLowerCase() !== 'all') {
    query.set('provider', params.provider);
  }
  if (params?.game_format && params.game_format.toLowerCase() !== 'all') {
    query.set('game_format', params.game_format);
  }
  if (params?.price_type && params.price_type.toLowerCase() !== 'all') {
    query.set('price_type', params.price_type);
  }
  if (params?.finish && params.finish.toLowerCase() !== 'all') {
    query.set('finish', params.finish);
  }
  if (params?.currency && params.currency.toUpperCase() !== 'ALL') {
    query.set('currency', params.currency);
  }
  if (params?.days && params.days > 0) {
    query.set('days', params.days.toString());
  }

  const res = await fetch(`${API_BASE}/cards/${uuid}/price-history?${query.toString()}`, { signal });
  if (!res.ok) {
    throw new Error(`Error al consultar historial de precios (${res.status}): ${res.statusText}`);
  }
  return res.json();
}

export async function fetchFilterMetadata(
  signal?: AbortSignal
): Promise<FilterMetadata> {
  const res = await fetch(`${API_BASE}/filters/metadata`, { signal });
  if (!res.ok) {
    throw new Error(`Error al consultar metadatos de filtros (${res.status}): ${res.statusText}`);
  }
  return res.json();
}
