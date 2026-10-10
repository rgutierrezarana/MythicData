import { Component, createResource, Show, For } from 'solid-js';
import { CardSummary } from '../types/card';
import { fetchCardDetail } from '../services/api';
import { ManaSymbol } from './ManaSymbol';

interface CardDetailModalProps {
  cardSummary: CardSummary | null;
  onClose: () => void;
}

export const CardDetailModal: Component<CardDetailModalProps> = (props) => {
  const [detail] = createResource(
    () => props.cardSummary?.uuid,
    (uuid) => fetchCardDetail(uuid)
  );

  const getRarityClass = (rarity?: string) => {
    const r = (rarity || '').toLowerCase();
    if (r === 'mythic') return 'rarity-mythic';
    if (r === 'rare') return 'rarity-rare';
    if (r === 'uncommon') return 'rarity-uncommon';
    return 'rarity-common';
  };

  return (
    <Show when={props.cardSummary}>
      <div
        style={{
          position: 'fixed',
          inset: 0,
          'z-index': 110,
          background: 'rgba(0, 0, 0, 0.75)',
          'backdrop-filter': 'blur(8px)',
          display: 'flex',
          'align-items': 'center',
          'justify-content': 'center',
          padding: '16px'
        }}
        onClick={(e) => {
          if (e.target === e.currentTarget) props.onClose();
        }}
      >
        <div
          class="animate-popover"
          style={{
            background: 'var(--m3-surface-container)',
            'border-radius': '24px',
            border: '1px solid var(--m3-outline-variant)',
            'box-shadow': 'var(--shadow-5)',
            width: '100%',
            'max-width': '920px',
            'max-height': '90vh',
            overflow: 'hidden',
            display: 'flex',
            'flex-direction': 'column',
            color: 'var(--m3-on-surface)'
          }}
        >
          {/* Cabecera del Modal */}
          <div
            style={{
              padding: '16px 24px',
              'border-bottom': '1px solid var(--m3-outline-variant)',
              display: 'flex',
              'align-items': 'center',
              'justify-content': 'space-between',
              background: 'var(--m3-surface-container-high)'
            }}
          >
            <div style={{ display: 'flex', 'align-items': 'center', gap: '12px' }}>
              <span class="material-symbols-outlined" style={{ color: 'var(--m3-primary)' }}>
                style
              </span>
              <div>
                <h2 style={{ 'font-size': '1.25rem', 'font-weight': 700, 'line-height': 1.2 }}>
                  {props.cardSummary?.name}
                </h2>
                <span style={{ 'font-size': '0.75rem', color: 'var(--m3-on-surface-variant)' }}>
                  UUID: {props.cardSummary?.uuid}
                </span>
              </div>
            </div>

            <button class="m3-btn-icon" onClick={props.onClose} title="Cerrar ventana">
              <span class="material-symbols-outlined">close</span>
            </button>
          </div>

          {/* Cuerpo del Modal con Scroll */}
          <div style={{ padding: '24px', 'overflow-y': 'auto', flex: 1 }}>
            <Show
              when={!detail.loading}
              fallback={
                <div style={{ display: 'flex', 'flex-direction': 'column', 'align-items': 'center', padding: '60px', gap: '16px' }}>
                  <div class="skeleton" style={{ width: '48px', height: '48px', 'border-radius': '50%' }}></div>
                  <p style={{ color: 'var(--m3-on-surface-variant)' }}>Cargando datos completos de la carta y cotizaciones...</p>
                </div>
              }
            >
              <div style={{ display: 'grid', 'grid-template-columns': 'minmax(260px, 320px) 1fr', gap: '28px' }}>
                {/* Columna Izquierda: Imagen Grande + Enlaces */}
                <div style={{ display: 'flex', 'flex-direction': 'column', gap: '16px' }}>
                  <div
                    style={{
                      width: '100%',
                      'border-radius': '16px',
                      overflow: 'hidden',
                      background: 'var(--m3-surface-container-lowest)',
                      'box-shadow': 'var(--shadow-3)',
                      border: '1px solid var(--m3-outline-variant)'
                    }}
                  >
                    <img
                      src={detail()?.image_url_large || detail()?.image_url || ''}
                      alt={detail()?.name}
                      style={{ width: '100%', height: 'auto', display: 'block' }}
                    />
                  </div>

                  {/* Acciones Externas */}
                  <div style={{ display: 'flex', gap: '8px' }}>
                    <Show when={detail()?.scryfall_id}>
                      <a
                        href={`https://scryfall.com/card/${detail()?.set_code?.toLowerCase()}/${detail()?.collector_number}`}
                        target="_blank"
                        rel="noreferrer"
                        class="m3-btn m3-btn-tonal"
                        style={{ flex: 1, 'text-decoration': 'none', 'font-size': '0.75rem', height: '36px' }}
                      >
                        <span class="material-symbols-outlined" style={{ 'font-size': '16px' }}>open_in_new</span>
                        Scryfall
                      </a>
                    </Show>

                    <Show when={detail()?.tcgplayer_product_id}>
                      <a
                        href={`https://www.tcgplayer.com/product/${detail()?.tcgplayer_product_id}`}
                        target="_blank"
                        rel="noreferrer"
                        class="m3-btn m3-btn-filled"
                        style={{ flex: 1, 'text-decoration': 'none', 'font-size': '0.75rem', height: '36px' }}
                      >
                        <span class="material-symbols-outlined" style={{ 'font-size': '16px' }}>shopping_cart</span>
                        TCGPlayer
                      </a>
                    </Show>
                  </div>
                </div>

                {/* Columna Derecha: Metadatos + Precios + Historial */}
                <div style={{ display: 'flex', 'flex-direction': 'column', gap: '20px' }}>
                  {/* Fila Principal: Nombre, Coste, Tipo, Rareza */}
                  <div style={{ display: 'flex', 'flex-direction': 'column', gap: '8px' }}>
                    <div style={{ display: 'flex', 'align-items': 'center', 'justify-content': 'space-between' }}>
                      <span style={{ 'font-size': '1.125rem', 'font-weight': 700 }}>
                        {detail()?.type_line}
                      </span>
                      <Show when={detail()?.mana_cost}>
                        <ManaSymbol cost={detail()?.mana_cost} size="lg" />
                      </Show>
                    </div>

                    <div style={{ display: 'flex', 'align-items': 'center', gap: '10px', 'flex-wrap': 'wrap' }}>
                      <span class={`rarity-badge ${getRarityClass(detail()?.rarity)}`}>
                        {detail()?.rarity || 'Common'}
                      </span>
                      <span style={{ 'font-size': '0.8125rem', color: 'var(--m3-on-surface-variant)' }}>
                        CMC: {detail()?.mana_value}
                      </span>
                      <Show when={detail()?.artist}>
                        <span style={{ 'font-size': '0.8125rem', color: 'var(--m3-on-surface-variant)' }}>
                          🎨 Ilustrado por {detail()?.artist}
                        </span>
                      </Show>
                    </div>
                  </div>

                  {/* Texto de Reglas (Oracle Text) */}
                  <Show when={detail()?.oracle_text}>
                    <div
                      style={{
                        background: 'var(--m3-surface-container-high)',
                        'border-radius': '12px',
                        padding: '14px 16px',
                        border: '1px solid var(--m3-outline-variant)',
                        'font-size': '0.875rem',
                        'line-height': 1.5,
                        'white-space': 'pre-line'
                      }}
                    >
                      {detail()?.oracle_text}
                    </div>
                  </Show>

                  {/* Información de Edición */}
                  <div
                    style={{
                      background: 'var(--m3-surface-container-low)',
                      'border-radius': '12px',
                      padding: '12px 16px',
                      border: '1px solid var(--m3-outline-variant)',
                      display: 'grid',
                      'grid-template-columns': 'repeat(auto-fit, minmax(130px, 1fr))',
                      gap: '10px'
                    }}
                  >
                    <div>
                      <span style={{ 'font-size': '0.6875rem', color: 'var(--m3-on-surface-variant)' }}>Edición / Set</span>
                      <p style={{ 'font-size': '0.8125rem', 'font-weight': 600 }}>{detail()?.set_name} ({detail()?.set_code})</p>
                    </div>
                    <div>
                      <span style={{ 'font-size': '0.6875rem', color: 'var(--m3-on-surface-variant)' }}>Número de Carta</span>
                      <p style={{ 'font-size': '0.8125rem', 'font-weight': 600 }}>#{detail()?.collector_number || 'N/D'}</p>
                    </div>
                    <div>
                      <span style={{ 'font-size': '0.6875rem', color: 'var(--m3-on-surface-variant)' }}>Lanzamiento</span>
                      <p style={{ 'font-size': '0.8125rem', 'font-weight': 600 }}>{detail()?.set_info?.release_date || 'N/D'}</p>
                    </div>
                    <div>
                      <span style={{ 'font-size': '0.6875rem', color: 'var(--m3-on-surface-variant)' }}>Disponibilidad</span>
                      <p style={{ 'font-size': '0.8125rem', 'font-weight': 600 }}>{detail()?.availability || 'Paper'}</p>
                    </div>
                  </div>

                  {/* Proyección Predictiva con Machine Learning (GBTRegressor) */}
                  <Show when={detail()?.prediction}>
                    {(pred) => {
                      const isUp = pred().direction === 'UP';
                      const isDown = pred().direction === 'DOWN';
                      const trendColor = isUp ? '#10b981' : isDown ? '#ef4444' : '#a855f7';
                      const trendBg = isUp ? 'rgba(16, 185, 129, 0.12)' : isDown ? 'rgba(239, 68, 68, 0.12)' : 'rgba(168, 85, 247, 0.12)';
                      const trendIcon = isUp ? 'trending_up' : isDown ? 'trending_down' : 'trending_flat';
                      const changeSign = (pred().expected_change_pct || 0) > 0 ? '+' : '';

                      return (
                        <div
                          style={{
                            background: 'linear-gradient(135deg, rgba(168, 85, 247, 0.1) 0%, rgba(59, 130, 246, 0.05) 100%)',
                            'border-radius': '16px',
                            border: '1px solid rgba(168, 85, 247, 0.35)',
                            padding: '16px',
                            display: 'flex',
                            'flex-direction': 'column',
                            gap: '12px',
                            'box-shadow': '0 4px 20px rgba(0, 0, 0, 0.18)',
                          }}
                        >
                          {/* Cabecera del Modelo ML */}
                          <div style={{ display: 'flex', 'align-items': 'center', 'justify-content': 'space-between', 'flex-wrap': 'wrap', gap: '8px' }}>
                            <div style={{ display: 'flex', 'align-items': 'center', gap: '8px' }}>
                              <span
                                class="material-symbols-outlined"
                                style={{
                                  background: 'linear-gradient(135deg, #a855f7, #6366f1)',
                                  color: '#fff',
                                  padding: '6px',
                                  'border-radius': '8px',
                                  'font-size': '20px',
                                }}
                              >
                                psychology
                              </span>
                              <div>
                                <div style={{ 'font-size': '0.9375rem', 'font-weight': 800, color: 'var(--m3-on-surface)' }}>
                                  Pronóstico de Próximo Precio (Spark MLlib)
                                </div>
                                <div style={{ 'font-size': '0.6875rem', color: 'var(--m3-on-surface-variant)' }}>
                                  Modelo Gradient Boosted Trees: {pred().model_name}
                                </div>
                              </div>
                            </div>

                            <span
                              style={{
                                background: 'rgba(168, 85, 247, 0.15)',
                                color: '#c084fc',
                                border: '1px solid rgba(168, 85, 247, 0.3)',
                                padding: '3px 8px',
                                'border-radius': '8px',
                                'font-size': '0.6875rem',
                                'font-weight': 700,
                                display: 'flex',
                                'align-items': 'center',
                                gap: '4px',
                              }}
                            >
                              <span class="material-symbols-outlined" style={{ 'font-size': '14px' }}>verified</span>
                              {pred().confidence_score}% Confianza R²
                            </span>
                          </div>

                          {/* Comparativa de Precio Actual vs Predicho */}
                          <div
                            style={{
                              display: 'grid',
                              'grid-template-columns': 'repeat(auto-fit, minmax(130px, 1fr))',
                              gap: '12px',
                              background: 'var(--m3-surface-container)',
                              padding: '12px 14px',
                              'border-radius': '12px',
                              border: '1px solid var(--m3-outline-variant)',
                            }}
                          >
                            <div>
                              <div style={{ 'font-size': '0.6875rem', color: 'var(--m3-on-surface-variant)' }}>Precio Actual de Mercado</div>
                              <div style={{ 'font-size': '1.125rem', 'font-weight': 800, color: 'var(--m3-on-surface)' }}>
                                ${pred().current_price?.toFixed(2) || '0.00'} USD
                              </div>
                            </div>

                            <div>
                              <div style={{ 'font-size': '0.6875rem', color: '#c084fc', 'font-weight': 600 }}>Próximo Precio Estimado (t+1)</div>
                              <div style={{ 'font-size': '1.25rem', 'font-weight': 900, color: '#38bdf8' }}>
                                ${pred().predicted_next_price?.toFixed(2) || '0.00'} USD
                              </div>
                            </div>

                            <div style={{ display: 'flex', 'flex-direction': 'column', 'justify-content': 'center' }}>
                              <div style={{ 'font-size': '0.6875rem', color: 'var(--m3-on-surface-variant)' }}>Tendencia Estimada</div>
                              <div
                                style={{
                                  display: 'inline-flex',
                                  'align-items': 'center',
                                  gap: '4px',
                                  background: trendBg,
                                  color: trendColor,
                                  padding: '4px 8px',
                                  'border-radius': '8px',
                                  'font-size': '0.8125rem',
                                  'font-weight': 800,
                                  width: 'fit-content',
                                  'margin-top': '2px',
                                }}
                              >
                                <span class="material-symbols-outlined" style={{ 'font-size': '16px' }}>{trendIcon}</span>
                                {changeSign}{pred().expected_change_pct}% ({pred().direction})
                              </div>
                            </div>
                          </div>

                          {/* Explicación de Variables de Entrada */}
                          <div style={{ 'font-size': '0.6875rem', color: 'var(--m3-outline)', display: 'flex', 'align-items': 'center', gap: '4px' }}>
                            <span class="material-symbols-outlined" style={{ 'font-size': '14px' }}>info</span>
                            Entrenado con lags temporales (t-1, t-3, t-7), medias móviles (7d/14d), momentum y volatilidad histórica.
                          </div>
                        </div>
                      );
                    }}
                  </Show>

                  {/* Tabla de Cotizaciones de Precios Actuales */}
                  <div>
                    <h3 style={{ 'font-size': '0.9375rem', 'font-weight': 700, 'margin-bottom': '10px', display: 'flex', 'align-items': 'center', gap: '6px' }}>
                      <span class="material-symbols-outlined" style={{ 'font-size': '18px', color: 'var(--m3-gold)' }}>
                        payments
                      </span>
                      Precios Actuales Multitienda
                    </h3>

                    <div
                      style={{
                        'border-radius': '12px',
                        overflow: 'hidden',
                        border: '1px solid var(--m3-outline-variant)',
                        background: 'var(--m3-surface-container)'
                      }}
                    >
                      <table style={{ width: '100%', 'border-collapse': 'collapse', 'font-size': '0.8125rem' }}>
                        <thead>
                          <tr style={{ background: 'var(--m3-surface-container-high)', 'text-align': 'left' }}>
                            <th style={{ padding: '8px 12px' }}>Tienda / Proveedor</th>
                            <th style={{ padding: '8px 12px' }}>Acabado</th>
                            <th style={{ padding: '8px 12px' }}>Canal</th>
                            <th style={{ padding: '8px 12px' }}>Precio</th>
                            <th style={{ padding: '8px 12px' }}>Fecha</th>
                          </tr>
                        </thead>
                        <tbody>
                          <Show
                            when={detail()?.prices && detail()!.prices.length > 0}
                            fallback={
                              <tr>
                                <td colspan="5" style={{ padding: '16px', 'text-align': 'center', color: 'var(--m3-outline)' }}>
                                  No hay cotizaciones individuales adicionales registradas para esta carta.
                                </td>
                              </tr>
                            }
                          >
                            <For each={detail()?.prices}>
                              {(p) => (
                                <tr style={{ 'border-top': '1px solid var(--m3-outline-variant)' }}>
                                  <td style={{ padding: '8px 12px', 'font-weight': 600, 'text-transform': 'capitalize' }}>
                                    {p.provider}
                                  </td>
                                  <td style={{ padding: '8px 12px', 'text-transform': 'capitalize' }}>
                                    <span style={{ color: p.finish === 'foil' ? '#60a5fa' : 'inherit' }}>
                                      {p.finish}
                                    </span>
                                  </td>
                                  <td style={{ padding: '8px 12px', 'text-transform': 'capitalize' }}>
                                    {p.price_type}
                                  </td>
                                  <td style={{ padding: '8px 12px', 'font-weight': 700, color: '#34d399' }}>
                                    {p.currency === 'USD' ? '$' : '€'}{p.price.toFixed(2)} {p.currency}
                                  </td>
                                  <td style={{ padding: '8px 12px', color: 'var(--m3-on-surface-variant)' }}>
                                    {p.price_date}
                                  </td>
                                </tr>
                              )}
                            </For>
                          </Show>
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              </div>
            </Show>
          </div>
        </div>
      </div>
    </Show>
  );
};
