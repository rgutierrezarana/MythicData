import { Component, Show } from 'solid-js';
import { CardSummary } from '../types/card';
import { ManaSymbol } from './ManaSymbol';

interface CardItemProps {
  card: CardSummary;
  onHoverStart: (card: CardSummary, e: MouseEvent) => void;
  onHoverEnd: () => void;
  onClick: (card: CardSummary) => void;
}

export const CardItem: Component<CardItemProps> = (props) => {
  const getRarityClass = (rarity?: string) => {
    const r = (rarity || '').toLowerCase();
    if (r === 'mythic') return 'rarity-mythic';
    if (r === 'rare') return 'rarity-rare';
    if (r === 'uncommon') return 'rarity-uncommon';
    return 'rarity-common';
  };

  const getLowestPrice = () => {
    const p = props.card.current_price_usd;
    if (p !== null && p !== undefined) {
      return `$${p.toFixed(2)}`;
    }
    const eur = props.card.current_price_eur;
    if (eur !== null && eur !== undefined) {
      return `€${eur.toFixed(2)}`;
    }
    return 'Sin cotización';
  };

  const isFoil = () => {
    return props.card.current_price_foil !== null && props.card.current_price_foil !== undefined;
  };

  return (
    <div
      class="animate-fade-in card-grid-item"
      onClick={() => props.onClick(props.card)}
      onMouseEnter={(e) => props.onHoverStart(props.card, e)}
      onMouseLeave={props.onHoverEnd}
      style={{
        background: 'var(--m3-surface-container)',
        'border-radius': '16px',
        border: '1px solid var(--m3-outline-variant)',
        overflow: 'hidden',
        cursor: 'pointer',
        display: 'flex',
        'flex-direction': 'column',
        position: 'relative',
        'box-shadow': 'var(--shadow-1)'
      }}
    >
      {/* Contenedor de Imagen de la Carta */}
      <div
        style={{
          width: '100%',
          'aspect-ratio': '5 / 7',
          background: 'var(--m3-surface-container-lowest)',
          position: 'relative',
          overflow: 'hidden',
          display: 'flex',
          'align-items': 'center',
          'justify-content': 'center'
        }}
      >
        <Show
          when={props.card.image_url}
          fallback={
            <div
              style={{
                display: 'flex',
                'flex-direction': 'column',
                'align-items': 'center',
                gap: '8px',
                color: 'var(--m3-outline)',
                padding: '16px',
                'text-align': 'center'
              }}
            >
              <span class="material-symbols-outlined" style={{ 'font-size': '42px' }}>
                style
              </span>
              <span style={{ 'font-size': '0.75rem', 'font-weight': 600 }}>{props.card.name}</span>
            </div>
          }
        >
          <img
            src={props.card.image_url}
            alt={props.card.name}
            style={{
              width: '100%',
              height: '100%',
              'object-fit': 'cover',
              transition: 'transform 0.3s ease'
            }}
            loading="lazy"
          />
        </Show>

        {/* Badge Flotante Superior: Set + Rareza */}
        <div
          style={{
            position: 'absolute',
            top: '8px',
            left: '8px',
            right: '8px',
            display: 'flex',
            'justify-content': 'space-between',
            'align-items': 'center',
            'pointer-events': 'none'
          }}
        >
          <span
            style={{
              background: 'rgba(20, 18, 24, 0.85)',
              color: '#ffffff',
              padding: '2px 8px',
              'border-radius': '6px',
              'font-size': '0.6875rem',
              'font-weight': 700,
              'backdrop-filter': 'blur(6px)',
              border: '1px solid rgba(255,255,255,0.15)'
            }}
          >
            {props.card.set_code} #{props.card.collector_number || ''}
          </span>

          <span
            class={`rarity-badge ${getRarityClass(props.card.rarity)}`}
            style={{ 'font-size': '0.6875rem', padding: '1px 6px' }}
          >
            {props.card.rarity?.[0] || 'C'}
          </span>
        </div>

        {/* Badge Flotante Inferior: Precio */}
        <div
          style={{
            position: 'absolute',
            bottom: '8px',
            right: '8px',
            display: 'flex',
            gap: '4px',
            'align-items': 'center',
            'pointer-events': 'none'
          }}
        >
          <span
            style={{
              background: props.card.current_price_usd ? '#059669' : 'rgba(33, 31, 38, 0.88)',
              color: '#ffffff',
              padding: '3px 8px',
              'border-radius': '8px',
              'font-size': '0.75rem',
              'font-weight': 700,
              'box-shadow': '0 2px 4px rgba(0,0,0,0.5)',
              border: '1px solid rgba(255,255,255,0.2)'
            }}
          >
            {getLowestPrice()}
          </span>

          {isFoil() && (
            <span
              style={{
                background: 'linear-gradient(135deg, #3b82f6, #8b5cf6)',
                color: '#ffffff',
                padding: '3px 6px',
                'border-radius': '8px',
                'font-size': '0.625rem',
                'font-weight': 800,
                'box-shadow': '0 2px 4px rgba(0,0,0,0.5)',
                'text-transform': 'uppercase'
              }}
              title={`Foil: $${props.card.current_price_foil?.toFixed(2)}`}
            >
              Foil
            </span>
          )}
        </div>
      </div>

      {/* Contenido Inferior: Nombre y Tipo */}
      <div style={{ padding: '12px 14px', display: 'flex', 'flex-direction': 'column', gap: '6px' }}>
        <div style={{ display: 'flex', 'align-items': 'flex-start', 'justify-content': 'space-between', gap: '6px' }}>
          <h3
            style={{
              'font-size': '0.875rem',
              'font-weight': 700,
              color: 'var(--m3-on-surface)',
              'text-overflow': 'ellipsis',
              overflow: 'hidden',
              'white-space': 'nowrap',
              flex: 1
            }}
            title={props.card.name}
          >
            {props.card.name}
          </h3>
          <Show when={props.card.mana_cost}>
            <ManaSymbol cost={props.card.mana_cost} size="sm" />
          </Show>
        </div>

        <div style={{ display: 'flex', 'align-items': 'center', 'justify-content': 'space-between' }}>
          <span
            style={{
              'font-size': '0.75rem',
              color: 'var(--m3-on-surface-variant)',
              'text-overflow': 'ellipsis',
              overflow: 'hidden',
              'white-space': 'nowrap',
              maxWidth: '180px'
            }}
          >
            {props.card.type_line || 'Magic Card'}
          </span>
          <span style={{ 'font-size': '0.6875rem', color: 'var(--m3-outline)' }}>
            CMC {props.card.mana_value || 0}
          </span>
        </div>
      </div>
    </div>
  );
};
