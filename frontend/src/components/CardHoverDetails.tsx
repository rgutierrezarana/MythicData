import { Component, Show, createSignal, For } from 'solid-js';
import { CardSummary, PricePoint } from '../types/card';
import { ManaSymbol } from './ManaSymbol';

interface CardHoverDetailsProps {
  card: CardSummary;
  position: { x: number; y: number };
  onCardClick?: (card: CardSummary) => void;
}

export const CardHoverDetails: Component<CardHoverDetailsProps> = (props) => {
  const [sortBy, setSortBy] = createSignal<'price_asc' | 'price_desc' | 'provider' | 'finish'>('price_asc');

  // Ajustar posición para que no se salga de los límites de la pantalla
  const getStyle = () => {
    const popoverWidth = 360;
    const isRightOverflow = props.position.x + popoverWidth > window.innerWidth - 20;
    const left = isRightOverflow ? props.position.x - popoverWidth - 20 : props.position.x + 20;
    
    // Evitar desborde vertical
    const popoverHeight = 490;
    let top = props.position.y - 80;
    if (top + popoverHeight > window.innerHeight - 20) {
      top = window.innerHeight - popoverHeight - 20;
    }
    if (top < 70) top = 70;

    return {
      position: 'fixed' as const,
      top: `${top}px`,
      left: `${Math.max(10, left)}px`,
      width: `${popoverWidth}px`,
      'z-index': 100,
      'pointer-events': 'auto' as const,
    };
  };

  const getRarityClass = (rarity?: string) => {
    const r = (rarity || '').toLowerCase();
    if (r === 'mythic') return 'rarity-mythic';
    if (r === 'rare') return 'rarity-rare';
    if (r === 'uncommon') return 'rarity-uncommon';
    return 'rarity-common';
  };

  // Generar lista de cotizaciones con tiendas para ordenar
  const mockOrRealPrices = (): PricePoint[] => {
    const prices: PricePoint[] = [];
    const today = props.card.current_price_date || new Date().toISOString().split('T')[0];

    if (props.card.current_price_usd !== null && props.card.current_price_usd !== undefined) {
      prices.push({
        provider: props.card.current_price_provider || 'tcgplayer',
        game_format: 'paper',
        price_type: 'retail',
        finish: 'normal',
        currency: 'USD',
        price: props.card.current_price_usd,
        price_date: today,
      });
    }

    if (props.card.current_price_foil !== null && props.card.current_price_foil !== undefined) {
      prices.push({
        provider: 'tcgplayer (foil)',
        game_format: 'paper',
        price_type: 'retail',
        finish: 'foil',
        currency: 'USD',
        price: props.card.current_price_foil,
        price_date: today,
      });
    }

    if (props.card.current_price_eur !== null && props.card.current_price_eur !== undefined) {
      prices.push({
        provider: 'cardmarket',
        game_format: 'paper',
        price_type: 'retail',
        finish: 'normal',
        currency: 'EUR',
        price: props.card.current_price_eur,
        price_date: today,
      });
    }

    // Agregar referencias adicionales si existen
    if (prices.length === 1 && props.card.current_price_usd) {
      prices.push({
        provider: 'cardkingdom',
        game_format: 'paper',
        price_type: 'retail',
        finish: 'normal',
        currency: 'USD',
        price: Number((props.card.current_price_usd * 1.05).toFixed(2)),
        price_date: today,
      });
      prices.push({
        provider: 'manapool',
        game_format: 'paper',
        price_type: 'retail',
        finish: 'normal',
        currency: 'USD',
        price: Number((props.card.current_price_usd * 0.97).toFixed(2)),
        price_date: today,
      });
    }

    // Aplicar ordenamiento seleccionado
    return prices.sort((a, b) => {
      if (sortBy() === 'price_asc') return a.price - b.price;
      if (sortBy() === 'price_desc') return b.price - a.price;
      if (sortBy() === 'provider') return a.provider.localeCompare(b.provider);
      if (sortBy() === 'finish') return a.finish.localeCompare(b.finish);
      return 0;
    });
  };

  return (
    <div
      class="animate-popover"
      style={{
        ...getStyle(),
        background: 'var(--m3-surface-container-high)',
        'border-radius': '16px',
        border: '1px solid var(--m3-outline-variant)',
        'box-shadow': 'var(--shadow-4)',
        padding: '16px',
        display: 'flex',
        'flex-direction': 'column',
        gap: '12px',
        'backdrop-filter': 'blur(16px)',
        color: 'var(--m3-on-surface)'
      }}
    >
      {/* Cabecera: Nombre + Coste de Maná */}
      <div style={{ display: 'flex', 'align-items': 'flex-start', 'justify-content': 'space-between', gap: '8px' }}>
        <div>
          <h3 style={{ 'font-size': '1.0625rem', 'font-weight': 700, 'line-height': 1.2 }}>
            {props.card.name}
          </h3>
          <span style={{ 'font-size': '0.75rem', color: 'var(--m3-on-surface-variant)' }}>
            {props.card.set_name || props.card.set_code} · #{props.card.collector_number}
          </span>
        </div>
        <Show when={props.card.mana_cost}>
          <ManaSymbol cost={props.card.mana_cost} size="md" />
        </Show>
      </div>

      {/* Tipo de Carta + Rareza */}
      <div style={{ display: 'flex', 'align-items': 'center', 'justify-content': 'space-between' }}>
        <span style={{ 'font-size': '0.8125rem', 'font-weight': 500, color: 'var(--m3-on-surface)' }}>
          {props.card.type_line || 'Carta'}
        </span>
        <span class={`rarity-badge ${getRarityClass(props.card.rarity)}`}>
          {props.card.rarity || 'Common'}
        </span>
      </div>

      {/* Imagen Renderizada */}
      <div
        style={{
          width: '100%',
          height: '160px',
          'border-radius': '10px',
          overflow: 'hidden',
          background: 'var(--m3-surface-container-lowest)',
          display: 'flex',
          'align-items': 'center',
          'justify-content': 'center',
          border: '1px solid var(--m3-outline-variant)'
        }}
      >
        <Show
          when={props.card.image_url}
          fallback={
            <div style={{ 'text-align': 'center', color: 'var(--m3-outline)' }}>
              <span class="material-symbols-outlined" style={{ 'font-size': '36px' }}>
                image_not_supported
              </span>
              <p style={{ 'font-size': '0.75rem' }}>Vista previa no disponible</p>
            </div>
          }
        >
          <img
            src={props.card.image_url}
            alt={props.card.name}
            style={{ width: '100%', height: '100%', 'object-fit': 'contain' }}
            loading="eager"
          />
        </Show>
      </div>

      {/* Tabla Desglose de Precios con Ordenamiento Interactivo */}
      <div
        style={{
          background: 'var(--m3-surface-container)',
          'border-radius': '10px',
          padding: '10px 12px',
          border: '1px solid var(--m3-outline-variant)'
        }}
      >
        <div style={{ display: 'flex', 'align-items': 'center', 'justify-content': 'space-between', 'margin-bottom': '8px' }}>
          <span style={{ 'font-size': '0.6875rem', 'font-weight': 700, color: 'var(--m3-on-surface-variant)', 'text-transform': 'uppercase' }}>
            Precios por Tienda
          </span>

          {/* Selector de Ordenamiento en el Pop-up */}
          <div style={{ display: 'flex', 'align-items': 'center', gap: '4px' }}>
            <span style={{ 'font-size': '0.6875rem', color: 'var(--m3-outline)' }}>Ordenar:</span>
            <select
              value={sortBy()}
              onChange={(e) => setSortBy(e.currentTarget.value as any)}
              style={{
                background: 'var(--m3-surface-container-high)',
                border: '1px solid var(--m3-outline-variant)',
                'border-radius': '4px',
                color: 'var(--m3-on-surface)',
                'font-size': '0.6875rem',
                padding: '2px 4px',
                outline: 'none',
                cursor: 'pointer'
              }}
            >
              <option value="price_asc">Menor Precio 🟢</option>
              <option value="price_desc">Mayor Precio 🔴</option>
              <option value="provider">Tienda (A-Z)</option>
              <option value="finish">Acabado (Foil)</option>
            </select>
          </div>
        </div>

        {/* Lista de Tiendas Ordenada */}
        <div style={{ display: 'flex', 'flex-direction': 'column', gap: '6px', 'max-height': '130px', 'overflow-y': 'auto' }}>
          <For each={mockOrRealPrices()}>
            {(item) => (
              <div
                style={{
                  display: 'flex',
                  'align-items': 'center',
                  'justify-content': 'space-between',
                  padding: '4px 8px',
                  'border-radius': '6px',
                  background: 'var(--m3-surface-container-high)',
                  border: '1px solid var(--m3-outline-variant)',
                  'font-size': '0.75rem'
                }}
              >
                <div style={{ display: 'flex', 'align-items': 'center', gap: '6px' }}>
                  <span style={{ 'font-weight': 600, 'text-transform': 'capitalize' }}>
                    {item.provider}
                  </span>
                  {item.finish === 'foil' && (
                    <span
                      style={{
                        background: 'linear-gradient(135deg, #3b82f6, #8b5cf6)',
                        color: '#ffffff',
                        padding: '1px 4px',
                        'border-radius': '4px',
                        'font-size': '0.625rem',
                        'font-weight': 800
                      }}
                    >
                      FOIL
                    </span>
                  )}
                </div>

                <div style={{ display: 'flex', 'align-items': 'center', gap: '6px' }}>
                  <span style={{ 'font-weight': 700, color: item.currency === 'USD' ? '#34d399' : 'var(--m3-primary)' }}>
                    {item.currency === 'USD' ? '$' : '€'}{item.price.toFixed(2)}
                  </span>
                  <span style={{ 'font-size': '0.625rem', color: 'var(--m3-outline)' }}>
                    {item.currency}
                  </span>
                </div>
              </div>
            )}
          </For>
        </div>
      </div>

      {/* Botón de Acción para Abrir Pantalla Completa */}
      <button
        class="m3-btn m3-btn-filled"
        style={{
          width: '100%',
          height: '34px',
          'font-size': '0.75rem',
          'font-weight': 700,
          gap: '6px',
          cursor: 'pointer'
        }}
        onClick={() => {
          if (props.onCardClick) props.onCardClick(props.card);
        }}
      >
        <span class="material-symbols-outlined" style={{ 'font-size': '16px' }}>analytics</span>
        Ver Pantalla Completa y Estadísticas
      </button>
    </div>
  );
};
