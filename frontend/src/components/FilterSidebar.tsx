import { Component, For, Show } from 'solid-js';
import { CardFilterParams, FilterMetadata } from '../types/card';

interface FilterSidebarProps {
  filters: CardFilterParams;
  onFilterChange: (newFilters: Partial<CardFilterParams>) => void;
  onResetFilters: () => void;
  metadata?: FilterMetadata;
  isOpen: boolean;
}

export const FilterSidebar: Component<FilterSidebarProps> = (props) => {
  const manaColors = [
    { code: 'W', label: 'Blanco', symbol: 'W', bg: '#fffbd5', text: '#1e1e1e' },
    { code: 'U', label: 'Azul', symbol: 'U', bg: '#0e68ab', text: '#ffffff' },
    { code: 'B', label: 'Negro', symbol: 'B', bg: '#26211e', text: '#d6d3d1' },
    { code: 'R', label: 'Rojo', symbol: 'R', bg: '#d3202a', text: '#ffffff' },
    { code: 'G', label: 'Verde', symbol: 'G', bg: '#00733e', text: '#ffffff' },
    { code: 'C', label: 'Incoloro', symbol: 'C', bg: '#cbc2be', text: '#292524' },
  ];

  const types = [
    'All',
    'Creature',
    'Instant',
    'Sorcery',
    'Enchantment',
    'Artifact',
    'Land',
    'Planeswalker'
  ];

  const rarities = ['All', 'Common', 'Uncommon', 'Rare', 'Mythic'];

  const toggleColor = (code: string) => {
    const current = props.filters.colors || [];
    let updated: string[];
    if (current.includes(code)) {
      updated = current.filter((c) => c !== code);
    } else {
      updated = [...current, code];
    }
    props.onFilterChange({ colors: updated, page: 1 });
  };

  const isColorSelected = (code: string) => {
    return (props.filters.colors || []).includes(code);
  };

  return (
    <aside
      style={{
        width: props.isOpen ? '300px' : '0px',
        opacity: props.isOpen ? 1 : 0,
        visibility: props.isOpen ? 'visible' : 'hidden',
        transition: 'all 0.25s cubic-bezier(0.4, 0, 0.2, 1)',
        background: 'var(--m3-surface-container-low)',
        'border-right': '1px solid var(--m3-outline-variant)',
        height: 'calc(100vh - 64px)',
        position: 'sticky',
        top: '64px',
        overflow: 'hidden',
        display: 'flex',
        'flex-direction': 'column',
        'z-index': 30,
        'flex-shrink': 0
      }}
    >
      <div
        style={{
          width: '300px',
          padding: '20px 16px',
          overflowY: 'auto',
          height: '100%',
          display: 'flex',
          'flex-direction': 'column',
          gap: '24px'
        }}
      >
        {/* Cabecera del Panel */}
        <div style={{ display: 'flex', 'align-items': 'center', 'justify-content': 'space-between' }}>
          <div style={{ display: 'flex', 'align-items': 'center', gap: '8px' }}>
            <span class="material-symbols-outlined" style={{ color: 'var(--m3-primary)', 'font-size': '20px' }}>
              filter_list
            </span>
            <h2 style={{ 'font-size': '1rem', 'font-weight': 700, color: 'var(--m3-on-surface)' }}>
              Filtros Avanzados
            </h2>
          </div>
          <button
            class="m3-btn-outlined"
            style={{ height: '30px', padding: '0 10px', 'font-size': '0.75rem', 'border-radius': '6px' }}
            onClick={props.onResetFilters}
          >
            Restablecer
          </button>
        </div>

        {/* 1. Selector de Edición / Set */}
        <div>
          <label
            style={{
              'font-size': '0.75rem',
              'font-weight': 700,
              color: 'var(--m3-on-surface-variant)',
              'text-transform': 'uppercase',
              'letter-spacing': '0.5px',
              'margin-bottom': '8px',
              display: 'block'
            }}
          >
            Edición / Set MTG
          </label>
          <select
            value={props.filters.set_code || 'ALL'}
            onChange={(e) => props.onFilterChange({ set_code: e.currentTarget.value, page: 1 })}
            style={{
              width: '100%',
              height: '40px',
              background: 'var(--m3-surface-container)',
              border: '1px solid var(--m3-outline-variant)',
              'border-radius': '8px',
              color: 'var(--m3-on-surface)',
              padding: '0 12px',
              'font-family': 'var(--font-body)',
              'font-size': '0.875rem',
              cursor: 'pointer',
              outline: 'none'
            }}
          >
            <option value="ALL">Todas las Ediciones</option>
            <Show when={props.metadata?.sets}>
              <For each={props.metadata?.sets}>
                {(s) => (
                  <option value={s.code}>
                    {s.code} - {s.name} ({s.card_count || s.total_set_size} cartas)
                  </option>
                )}
              </For>
            </Show>
          </select>
        </div>

        {/* 2. Colores de Maná */}
        <div>
          <label
            style={{
              'font-size': '0.75rem',
              'font-weight': 700,
              color: 'var(--m3-on-surface-variant)',
              'text-transform': 'uppercase',
              'letter-spacing': '0.5px',
              'margin-bottom': '8px',
              display: 'block'
            }}
          >
            Color de Maná
          </label>
          <div style={{ display: 'grid', 'grid-template-columns': 'repeat(3, 1fr)', gap: '6px' }}>
            <For each={manaColors}>
              {(mc) => {
                const active = () => isColorSelected(mc.code);
                return (
                  <button
                    type="button"
                    onClick={() => toggleColor(mc.code)}
                    style={{
                      display: 'flex',
                      'align-items': 'center',
                      gap: '6px',
                      padding: '6px 8px',
                      'border-radius': '8px',
                      border: active() ? '2px solid var(--m3-primary)' : '1px solid var(--m3-outline-variant)',
                      background: active() ? 'var(--m3-secondary-container)' : 'var(--m3-surface-container)',
                      color: active() ? 'var(--m3-on-secondary-container)' : 'var(--m3-on-surface)',
                      cursor: 'pointer',
                      transition: 'all 0.15s ease',
                      'font-size': '0.75rem',
                      'font-weight': 600
                    }}
                  >
                    <span
                      class={`mana-circle mana-${mc.code}`}
                      style={{ width: '18px', height: '18px', 'font-size': '10px' }}
                    >
                      {mc.symbol}
                    </span>
                    <span style={{ 'text-overflow': 'ellipsis', overflow: 'hidden', 'white-space': 'nowrap' }}>
                      {mc.label}
                    </span>
                  </button>
                );
              }}
            </For>
          </div>
        </div>

        {/* 3. Tipo de Carta */}
        <div>
          <label
            style={{
              'font-size': '0.75rem',
              'font-weight': 700,
              color: 'var(--m3-on-surface-variant)',
              'text-transform': 'uppercase',
              'letter-spacing': '0.5px',
              'margin-bottom': '8px',
              display: 'block'
            }}
          >
            Tipo de Carta
          </label>
          <div style={{ display: 'flex', 'flex-wrap': 'wrap', gap: '6px' }}>
            <For each={types}>
              {(t) => {
                const active = () => (props.filters.card_type || 'All').toLowerCase() === t.toLowerCase();
                return (
                  <button
                    type="button"
                    class={`m3-chip ${active() ? 'active' : ''}`}
                    onClick={() => props.onFilterChange({ card_type: t === 'All' ? undefined : t, page: 1 })}
                    style={{ 'font-size': '0.75rem', height: '28px' }}
                  >
                    {t === 'All' ? 'Todos' : t}
                  </button>
                );
              }}
            </For>
          </div>
        </div>

        {/* 4. Rareza */}
        <div>
          <label
            style={{
              'font-size': '0.75rem',
              'font-weight': 700,
              color: 'var(--m3-on-surface-variant)',
              'text-transform': 'uppercase',
              'letter-spacing': '0.5px',
              'margin-bottom': '8px',
              display: 'block'
            }}
          >
            Rareza
          </label>
          <div style={{ display: 'flex', 'flex-wrap': 'wrap', gap: '6px' }}>
            <For each={rarities}>
              {(r) => {
                const active = () => (props.filters.rarity || 'All').toLowerCase() === r.toLowerCase();
                return (
                  <button
                    type="button"
                    class={`m3-chip ${active() ? 'active' : ''}`}
                    onClick={() => props.onFilterChange({ rarity: r === 'All' ? undefined : r, page: 1 })}
                    style={{ 'font-size': '0.75rem', height: '28px' }}
                  >
                    {r === 'All' ? 'Todas' : r}
                  </button>
                );
              }}
            </For>
          </div>
        </div>

        {/* 5. Coste de Maná Convertido (CMC) */}
        <div>
          <label
            style={{
              'font-size': '0.75rem',
              'font-weight': 700,
              color: 'var(--m3-on-surface-variant)',
              'text-transform': 'uppercase',
              'letter-spacing': '0.5px',
              'margin-bottom': '8px',
              display: 'block'
            }}
          >
            Valor de Maná (CMC)
          </label>
          <div style={{ display: 'flex', 'align-items': 'center', gap: '8px' }}>
            <input
              type="number"
              min="0"
              max="20"
              placeholder="Mín"
              value={props.filters.mana_value_min ?? ''}
              onInput={(e) => {
                const v = e.currentTarget.value;
                props.onFilterChange({ mana_value_min: v ? parseFloat(v) : undefined, page: 1 });
              }}
              style={{
                width: '100%',
                height: '36px',
                background: 'var(--m3-surface-container)',
                border: '1px solid var(--m3-outline-variant)',
                'border-radius': '6px',
                color: 'var(--m3-on-surface)',
                padding: '0 8px',
                'font-size': '0.8125rem'
              }}
            />
            <span style={{ color: 'var(--m3-outline)' }}>-</span>
            <input
              type="number"
              min="0"
              max="20"
              placeholder="Máx"
              value={props.filters.mana_value_max ?? ''}
              onInput={(e) => {
                const v = e.currentTarget.value;
                props.onFilterChange({ mana_value_max: v ? parseFloat(v) : undefined, page: 1 });
              }}
              style={{
                width: '100%',
                height: '36px',
                background: 'var(--m3-surface-container)',
                border: '1px solid var(--m3-outline-variant)',
                'border-radius': '6px',
                color: 'var(--m3-on-surface)',
                padding: '0 8px',
                'font-size': '0.8125rem'
              }}
            />
          </div>
        </div>

        {/* 6. Filtros de Precio y Cotización */}
        <div>
          <label
            style={{
              'font-size': '0.75rem',
              'font-weight': 700,
              color: 'var(--m3-on-surface-variant)',
              'text-transform': 'uppercase',
              'letter-spacing': '0.5px',
              'margin-bottom': '8px',
              display: 'block'
            }}
          >
            Precios y Disponibilidad
          </label>

          <label
            style={{
              display: 'flex',
              'align-items': 'center',
              gap: '8px',
              'font-size': '0.8125rem',
              color: 'var(--m3-on-surface)',
              cursor: 'pointer',
              'margin-bottom': '10px'
            }}
          >
            <input
              type="checkbox"
              checked={props.filters.has_price || false}
              onChange={(e) => props.onFilterChange({ has_price: e.currentTarget.checked, page: 1 })}
              style={{ accentColor: 'var(--m3-primary)', width: '16px', height: '16px' }}
            />
            <span>Solo cartas con cotización activa</span>
          </label>

          <div style={{ display: 'flex', 'align-items': 'center', gap: '8px' }}>
            <input
              type="number"
              min="0"
              step="0.1"
              placeholder="Mín $USD"
              value={props.filters.price_min ?? ''}
              onInput={(e) => {
                const v = e.currentTarget.value;
                props.onFilterChange({ price_min: v ? parseFloat(v) : undefined, page: 1 });
              }}
              style={{
                width: '100%',
                height: '36px',
                background: 'var(--m3-surface-container)',
                border: '1px solid var(--m3-outline-variant)',
                'border-radius': '6px',
                color: 'var(--m3-on-surface)',
                padding: '0 8px',
                'font-size': '0.8125rem'
              }}
            />
            <span style={{ color: 'var(--m3-outline)' }}>-</span>
            <input
              type="number"
              min="0"
              step="1"
              placeholder="Máx $USD"
              value={props.filters.price_max ?? ''}
              onInput={(e) => {
                const v = e.currentTarget.value;
                props.onFilterChange({ price_max: v ? parseFloat(v) : undefined, page: 1 });
              }}
              style={{
                width: '100%',
                height: '36px',
                background: 'var(--m3-surface-container)',
                border: '1px solid var(--m3-outline-variant)',
                'border-radius': '6px',
                color: 'var(--m3-on-surface)',
                padding: '0 8px',
                'font-size': '0.8125rem'
              }}
            />
          </div>
        </div>

        {/* 7. Ordenamiento */}
        <div>
          <label
            style={{
              'font-size': '0.75rem',
              'font-weight': 700,
              color: 'var(--m3-on-surface-variant)',
              'text-transform': 'uppercase',
              'letter-spacing': '0.5px',
              'margin-bottom': '8px',
              display: 'block'
            }}
          >
            Ordenar Resultados
          </label>
          <div style={{ display: 'flex', gap: '6px' }}>
            <select
              value={props.filters.sort_by || 'name'}
              onChange={(e) => props.onFilterChange({ sort_by: e.currentTarget.value, page: 1 })}
              style={{
                flex: 1,
                height: '38px',
                background: 'var(--m3-surface-container)',
                border: '1px solid var(--m3-outline-variant)',
                'border-radius': '6px',
                color: 'var(--m3-on-surface)',
                padding: '0 8px',
                'font-size': '0.8125rem'
              }}
            >
              <option value="name">Nombre (Alfabético)</option>
              <option value="price">Precio de Mercado ($USD)</option>
              <option value="mana_value">Coste de Maná (CMC)</option>
              <option value="release_date">Fecha de Edición</option>
              <option value="collector_number">Número de Coleccionista</option>
            </select>
            <button
              type="button"
              class="m3-btn-icon"
              style={{
                border: '1px solid var(--m3-outline-variant)',
                'border-radius': '6px',
                width: '38px',
                height: '38px',
                background: 'var(--m3-surface-container)'
              }}
              onClick={() => {
                const nextOrder = props.filters.order === 'desc' ? 'asc' : 'desc';
                props.onFilterChange({ order: nextOrder, page: 1 });
              }}
              title={props.filters.order === 'desc' ? 'Orden Descendente' : 'Orden Ascendente'}
            >
              <span class="material-symbols-outlined" style={{ 'font-size': '18px' }}>
                {props.filters.order === 'desc' ? 'arrow_downward' : 'arrow_upward'}
              </span>
            </button>
          </div>
        </div>
      </div>
    </aside>
  );
};
