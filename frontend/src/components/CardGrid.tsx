import { Component, For, Show } from 'solid-js';
import { CardSummary, PaginatedResponse } from '../types/card';
import { CardItem } from './CardItem';

interface CardGridProps {
  data?: PaginatedResponse<CardSummary>;
  loading: boolean;
  onHoverStart: (card: CardSummary, e: MouseEvent) => void;
  onHoverEnd: () => void;
  onCardClick: (card: CardSummary) => void;
  onPageChange: (newPage: number) => void;
  onResetFilters: () => void;
}

export const CardGrid: Component<CardGridProps> = (props) => {
  const items = () => props.data?.items || [];
  const total = () => props.data?.total || 0;
  const page = () => props.data?.page || 1;
  const totalPages = () => props.data?.total_pages || 1;
  const pageSize = () => props.data?.page_size || 24;

  const startRecord = () => (total() === 0 ? 0 : (page() - 1) * pageSize() + 1);
  const endRecord = () => Math.min(page() * pageSize(), total());

  return (
    <div style={{ flex: 1, display: 'flex', 'flex-direction': 'column', padding: '20px 24px', gap: '20px' }}>
      {/* Barra de Estadísticas y Resultados */}
      <div
        style={{
          display: 'flex',
          'align-items': 'center',
          'justify-content': 'space-between',
          'flex-wrap': 'wrap',
          gap: '12px'
        }}
      >
        <div>
          <h2 style={{ 'font-size': '1.25rem', 'font-weight': 700, color: 'var(--m3-on-surface)' }}>
            Catálogo de Cartas
          </h2>
          <span style={{ 'font-size': '0.8125rem', color: 'var(--m3-on-surface-variant)' }}>
            Mostrando {startRecord()} - {endRecord()} de {total().toLocaleString()} cartas encontradas
          </span>
        </div>

        {/* Paginación Rápida Superior */}
        <Show when={totalPages() > 1}>
          <div style={{ display: 'flex', 'align-items': 'center', gap: '6px' }}>
            <button
              class="m3-btn-icon"
              disabled={page() <= 1}
              onClick={() => props.onPageChange(page() - 1)}
              style={{ opacity: page() <= 1 ? 0.4 : 1, cursor: page() <= 1 ? 'not-allowed' : 'pointer' }}
              title="Página Anterior"
            >
              <span class="material-symbols-outlined">chevron_left</span>
            </button>

            <span style={{ 'font-size': '0.8125rem', 'font-weight': 600, padding: '0 8px' }}>
              Pág. {page()} de {totalPages()}
            </span>

            <button
              class="m3-btn-icon"
              disabled={page() >= totalPages()}
              onClick={() => props.onPageChange(page() + 1)}
              style={{ opacity: page() >= totalPages() ? 0.4 : 1, cursor: page() >= totalPages() ? 'not-allowed' : 'pointer' }}
              title="Página Siguiente"
            >
              <span class="material-symbols-outlined">chevron_right</span>
            </button>
          </div>
        </Show>
      </div>

      {/* Grid de Cartas o Skeletons */}
      <Show
        when={!props.loading}
        fallback={
          <div
            style={{
              display: 'grid',
              'grid-template-columns': 'repeat(auto-fill, minmax(200px, 1fr))',
              gap: '20px'
            }}
          >
            <For each={Array.from({ length: 12 })}>
              {() => (
                <div style={{ display: 'flex', 'flex-direction': 'column', gap: '10px' }}>
                  <div class="skeleton" style={{ width: '100%', 'aspect-ratio': '5 / 7', 'border-radius': '16px' }} />
                  <div class="skeleton" style={{ width: '70%', height: '18px', 'border-radius': '6px' }} />
                  <div class="skeleton" style={{ width: '40%', height: '14px', 'border-radius': '6px' }} />
                </div>
              )}
            </For>
          </div>
        }
      >
        <Show
          when={items().length > 0}
          fallback={
            <div
              style={{
                display: 'flex',
                'flex-direction': 'column',
                'align-items': 'center',
                'justify-content': 'center',
                padding: '80px 20px',
                'text-align': 'center',
                gap: '16px',
                background: 'var(--m3-surface-container-low)',
                'border-radius': '24px',
                border: '1px dashed var(--m3-outline)'
              }}
            >
              <div
                style={{
                  width: '64px',
                  height: '64px',
                  'border-radius': '50%',
                  background: 'var(--m3-surface-container-high)',
                  display: 'flex',
                  'align-items': 'center',
                  'justify-content': 'center',
                  color: 'var(--m3-outline)'
                }}
              >
                <span class="material-symbols-outlined" style={{ 'font-size': '36px' }}>
                  search_off
                </span>
              </div>
              <h3 style={{ 'font-size': '1.25rem', 'font-weight': 700 }}>No se encontraron cartas</h3>
              <p style={{ 'font-size': '0.875rem', color: 'var(--m3-on-surface-variant)', 'max-width': '400px' }}>
                No hay resultados que coincidan con la búsqueda o combinación de filtros actual. Intenta ajustar los criterios.
              </p>
              <button class="m3-btn m3-btn-filled" onClick={props.onResetFilters}>
                <span class="material-symbols-outlined" style={{ 'font-size': '18px' }}>
                  restart_alt
                </span>
                Restablecer todos los filtros
              </button>
            </div>
          }
        >
          <div
            style={{
              display: 'grid',
              'grid-template-columns': 'repeat(auto-fill, minmax(200px, 1fr))',
              gap: '20px'
            }}
          >
            <For each={items()}>
              {(card) => (
                <CardItem
                  card={card}
                  onHoverStart={props.onHoverStart}
                  onHoverEnd={props.onHoverEnd}
                  onClick={props.onCardClick}
                />
              )}
            </For>
          </div>
        </Show>
      </Show>

      {/* Barra de Paginación Inferior Completa */}
      <Show when={totalPages() > 1}>
        <div
          style={{
            display: 'flex',
            'align-items': 'center',
            'justify-content': 'center',
            gap: '8px',
            'padding-top': '24px',
            'border-top': '1px solid var(--m3-outline-variant)'
          }}
        >
          <button
            class="m3-btn m3-btn-tonal"
            disabled={page() <= 1}
            onClick={() => props.onPageChange(page() - 1)}
            style={{ opacity: page() <= 1 ? 0.4 : 1, cursor: page() <= 1 ? 'not-allowed' : 'pointer', height: '36px' }}
          >
            <span class="material-symbols-outlined" style={{ 'font-size': '18px' }}>arrow_back</span>
            Anterior
          </button>

          <div style={{ display: 'flex', 'align-items': 'center', gap: '4px', 'margin': '0 8px' }}>
            <span style={{ 'font-size': '0.875rem', 'font-weight': 600 }}>
              Página {page()} de {totalPages()}
            </span>
          </div>

          <button
            class="m3-btn m3-btn-filled"
            disabled={page() >= totalPages()}
            onClick={() => props.onPageChange(page() + 1)}
            style={{ opacity: page() >= totalPages() ? 0.4 : 1, cursor: page() >= totalPages() ? 'not-allowed' : 'pointer', height: '36px' }}
          >
            Siguiente
            <span class="material-symbols-outlined" style={{ 'font-size': '18px' }}>arrow_forward</span>
          </button>
        </div>
      </Show>
    </div>
  );
};
