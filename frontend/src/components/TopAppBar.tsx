import { Component, createSignal, onCleanup } from 'solid-js';

interface TopAppBarProps {
  searchTerm: string;
  onSearchChange: (value: string) => void;
  totalCards: number;
  onToggleSidebar: () => void;
  isSidebarOpen: boolean;
  theme: 'dark' | 'light';
  onToggleTheme: () => void;
  currentView?: 'catalog' | 'ingestion';
  onNavigateToIngestion?: () => void;
  onNavigateToCatalog?: () => void;
}

export const TopAppBar: Component<TopAppBarProps> = (props) => {
  let debounceTimer: number | undefined;
  const [localSearch, setLocalSearch] = createSignal(props.searchTerm);

  const handleInput = (e: InputEvent) => {
    const target = e.target as HTMLInputElement;
    setLocalSearch(target.value);

    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = window.setTimeout(() => {
      props.onSearchChange(target.value);
    }, 300);
  };

  const clearSearch = () => {
    setLocalSearch('');
    props.onSearchChange('');
  };

  onCleanup(() => {
    if (debounceTimer) clearTimeout(debounceTimer);
  });

  return (
    <header
      style={{
        background: 'var(--m3-surface-container)',
        'border-bottom': '1px solid var(--m3-outline-variant)',
        position: 'sticky',
        top: 0,
        'z-index': 40,
        height: '64px',
        display: 'flex',
        'align-items': 'center',
        'justify-content': 'space-between',
        padding: '0 16px',
        'backdrop-filter': 'blur(12px)',
        'box-shadow': 'var(--shadow-1)'
      }}
    >
      {/* Lado Izquierdo: Botón Menú + Branding */}
      <div style={{ display: 'flex', 'align-items': 'center', gap: '12px' }}>
        <button
          class="m3-btn-icon"
          onClick={props.onToggleSidebar}
          title={props.isSidebarOpen ? 'Ocultar Filtros' : 'Mostrar Filtros'}
          aria-label="Toggle Filtros"
        >
          <span class="material-symbols-outlined">
            {props.isSidebarOpen ? 'menu_open' : 'tune'}
          </span>
        </button>

        <div style={{ display: 'flex', 'align-items': 'center', gap: '8px' }}>
          <div
            style={{
              width: '36px',
              height: '36px',
              'border-radius': '10px',
              background: 'linear-gradient(135deg, var(--m3-primary), var(--m3-primary-container))',
              display: 'flex',
              'align-items': 'center',
              'justify-content': 'center',
              color: 'var(--m3-on-primary)',
              'box-shadow': 'var(--shadow-1)'
            }}
          >
            <span class="material-symbols-outlined" style={{ 'font-size': '22px' }}>
              auto_awesome
            </span>
          </div>
          <div>
            <h1
              style={{
                'font-size': '1.125rem',
                'font-weight': 700,
                color: 'var(--m3-on-surface)',
                'line-height': 1.1,
                'letter-spacing': '-0.02em'
              }}
            >
              MTG Explorer
            </h1>
            <span
              style={{
                'font-size': '0.6875rem',
                color: 'var(--m3-on-surface-variant)',
                'font-weight': 500,
                'letter-spacing': '0.5px'
              }}
            >
              Market & Cards Platform
            </span>
          </div>
        </div>
      </div>

      {/* Centro: Barra de Búsqueda Reactiva M3 */}
      <div
        style={{
          flex: '1',
          'max-width': '520px',
          margin: '0 16px',
          position: 'relative'
        }}
      >
        <div
          style={{
            display: 'flex',
            'align-items': 'center',
            background: 'var(--m3-surface-container-high)',
            'border-radius': '24px',
            padding: '0 16px',
            height: '44px',
            border: '1px solid var(--m3-outline-variant)',
            transition: 'all 0.2s ease',
            'box-shadow': 'inset 0 1px 2px rgba(0,0,0,0.2)'
          }}
        >
          <span
            class="material-symbols-outlined"
            style={{ color: 'var(--m3-on-surface-variant)', 'margin-right': '8px', 'font-size': '20px' }}
          >
            search
          </span>
          <input
            type="text"
            placeholder="Buscar por nombre, texto o tipo (ej. Ragavan, Instant, Lotus)..."
            value={localSearch()}
            onInput={handleInput}
            style={{
              flex: 1,
              background: 'transparent',
              border: 'none',
              outline: 'none',
              color: 'var(--m3-on-surface)',
              'font-family': 'var(--font-body)',
              'font-size': '0.875rem'
            }}
          />
          {localSearch() && (
            <button
              onClick={clearSearch}
              style={{
                background: 'transparent',
                border: 'none',
                color: 'var(--m3-on-surface-variant)',
                cursor: 'pointer',
                display: 'flex',
                padding: '4px'
              }}
              title="Limpiar búsqueda"
            >
              <span class="material-symbols-outlined" style={{ 'font-size': '18px' }}>
                close
              </span>
            </button>
          )}
        </div>
      </div>

      {/* Lado Derecho: Botón Ingesta + Conteo + Modo Oscuro */}
      <div style={{ display: 'flex', 'align-items': 'center', gap: '8px' }}>
        {/* Botón de Ingesta & ETL */}
        <button
          type="button"
          class={`m3-btn ${props.currentView === 'ingestion' ? 'm3-btn-filled' : 'm3-btn-tonal'}`}
          onClick={() => {
            if (props.currentView === 'ingestion') {
              props.onNavigateToCatalog?.();
            } else {
              props.onNavigateToIngestion?.();
            }
          }}
          style={{ height: '36px', padding: '0 12px', 'font-size': '0.75rem', gap: '6px', cursor: 'pointer', 'font-weight': 700 }}
          title={props.currentView === 'ingestion' ? 'Volver al Catálogo' : 'Abrir Centro de Ingesta & Pipelines ETL'}
        >
          <span class="material-symbols-outlined" style={{ 'font-size': '18px' }}>
            {props.currentView === 'ingestion' ? 'grid_view' : 'sync_saved_locally'}
          </span>
          <span>{props.currentView === 'ingestion' ? 'Catálogo' : 'Ingesta & ETL'}</span>
        </button>

        {/* Conteo de Cartas */}
        <div
          style={{
            background: 'var(--m3-surface-container-high)',
            padding: '4px 10px',
            'border-radius': '12px',
            'font-size': '0.75rem',
            'font-weight': 600,
            color: 'var(--m3-primary)',
            border: '1px solid var(--m3-outline-variant)',
            display: 'flex',
            'align-items': 'center',
            gap: '4px'
          }}
          class="hidden sm:flex"
        >
          <span class="material-symbols-outlined" style={{ 'font-size': '14px' }}>
            database
          </span>
          <span>{props.totalCards.toLocaleString()} Cartas</span>
        </div>

        {/* Enlace rápido a Airflow */}
        <a
          href="http://localhost:8080"
          target="_blank"
          rel="noreferrer"
          class="m3-btn-icon"
          title="Abrir Apache Airflow (localhost:8080)"
          style={{ 'text-decoration': 'none' }}
        >
          <span class="material-symbols-outlined" style={{ 'font-size': '20px', color: '#10b981' }}>
            air
          </span>
        </a>

        {/* Enlace rápido a Jaeger */}
        <a
          href="http://localhost:16686"
          target="_blank"
          rel="noreferrer"
          class="m3-btn-icon"
          title="Abrir Jaeger Tracing (localhost:16686)"
          style={{ 'text-decoration': 'none' }}
        >
          <span class="material-symbols-outlined" style={{ 'font-size': '20px', color: '#a78bfa' }}>
            insights
          </span>
        </a>

        {/* Modo Claro / Oscuro */}
        <button
          class="m3-btn-icon"
          onClick={props.onToggleTheme}
          title={props.theme === 'dark' ? 'Cambiar a Modo Claro' : 'Cambiar a Modo Oscuro'}
        >
          <span class="material-symbols-outlined">
            {props.theme === 'dark' ? 'light_mode' : 'dark_mode'}
          </span>
        </button>
      </div>
    </header>
  );
};
