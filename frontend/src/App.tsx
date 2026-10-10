import { Component, createSignal, createResource, createEffect, onMount, onCleanup, Show } from 'solid-js';
import { CardFilterParams, CardSummary } from './types/card';
import { fetchCards, fetchFilterMetadata } from './services/api';
import { TopAppBar } from './components/TopAppBar';
import { FilterSidebar } from './components/FilterSidebar';
import { CardGrid } from './components/CardGrid';
import { CardHoverDetails } from './components/CardHoverDetails';
import { CardDetailScreen } from './components/CardDetailScreen';
import { CardDetailModal } from './components/CardDetailModal';
import { IngestionScreen } from './components/IngestionScreen';

export const App: Component = () => {
  // Estado de Navegación y Pantalla Activa
  const [activeCardUuid, setActiveCardUuid] = createSignal<string | null>(null);
  const [currentView, setCurrentView] = createSignal<'catalog' | 'ingestion'>('catalog');

  // Estado de Filtros y Búsqueda del Catálogo
  const [filters, setFilters] = createSignal<CardFilterParams>({
    q: '',
    set_code: 'ALL',
    card_type: 'All',
    rarity: 'All',
    colors: [],
    sort_by: 'name',
    order: 'asc',
    page: 1,
    page_size: 24,
  });

  // Estado de Interfaz
  const [isSidebarOpen, setIsSidebarOpen] = createSignal(true);
  const [theme, setTheme] = createSignal<'dark' | 'light'>('dark');
  
  // Estado de Hover y Modal Rápido
  const [hoveredCard, setHoveredCard] = createSignal<{
    card: CardSummary;
    position: {
      x: number;
      y: number;
      rect?: {
        left: number;
        right: number;
        top: number;
        bottom: number;
        width: number;
        height: number;
      };
    };
  } | null>(null);

  let hideHoverTimer: ReturnType<typeof setTimeout> | null = null;
  const [selectedModalCard, setSelectedModalCard] = createSignal<CardSummary | null>(null);

  // Carga de Metadatos de Filtros
  // Importante: envolver en arrow fn. Solid llama fetcher(source, info) y si se pasa
  // la función directamente, `info` termina como `signal` de fetch y lanza TypeError.
  const [metadata] = createResource(() => fetchFilterMetadata());

  // Carga de Cartas con Parámetros Reactivos
  const [cardsData] = createResource(
    () => ({ ...filters() }),
    (currentFilters) => fetchCards(currentFilters)
  );

  // Sincronización con Hash URL (#/card/:uuid, #/ingestion, #/)
  const syncHashWithState = () => {
    const rawHash = window.location.hash || '';
    const cleanHash = rawHash.replace(/^#\/?/, '');
    if (cleanHash === 'ingestion') {
      setActiveCardUuid(null);
      setCurrentView('ingestion');
      return;
    }
    if (cleanHash.startsWith('card/')) {
      const uuid = cleanHash.replace('card/', '').split('?')[0].split('/')[0].trim();
      if (uuid) {
        setActiveCardUuid(uuid);
        setCurrentView('catalog');
        return;
      }
    }
    setActiveCardUuid(null);
    setCurrentView('catalog');
  };

  onMount(() => {
    syncHashWithState();
    window.addEventListener('hashchange', syncHashWithState);
    window.addEventListener('popstate', syncHashWithState);
  });

  onCleanup(() => {
    if (hideHoverTimer) clearTimeout(hideHoverTimer);
    window.removeEventListener('hashchange', syncHashWithState);
    window.removeEventListener('popstate', syncHashWithState);
  });

  // Manejo de Tema (Dark / Light)
  createEffect(() => {
    document.documentElement.setAttribute('data-theme', theme());
  });

  const handleFilterChange = (partial: Partial<CardFilterParams>) => {
    setFilters((prev) => ({ ...prev, ...partial }));
  };

  const handleResetFilters = () => {
    setFilters({
      q: '',
      set_code: 'ALL',
      card_type: 'All',
      rarity: 'All',
      colors: [],
      mana_value_min: undefined,
      mana_value_max: undefined,
      has_price: false,
      price_min: undefined,
      price_max: undefined,
      sort_by: 'name',
      order: 'asc',
      page: 1,
      page_size: 24,
    });
  };

  const handleHoverStart = (card: CardSummary, e: MouseEvent) => {
    if (hideHoverTimer) {
      clearTimeout(hideHoverTimer);
      hideHoverTimer = null;
    }

    if (hoveredCard()?.card.uuid === card.uuid) {
      return;
    }

    const target = e.currentTarget as HTMLElement | null;
    const rect = target?.getBoundingClientRect?.();

    setHoveredCard({
      card,
      position: {
        x: e.clientX,
        y: e.clientY,
        rect: rect
          ? {
              left: rect.left,
              right: rect.right,
              top: rect.top,
              bottom: rect.bottom,
              width: rect.width,
              height: rect.height,
            }
          : undefined,
      },
    });
  };

  const handleHoverEnd = () => {
    if (hideHoverTimer) {
      clearTimeout(hideHoverTimer);
    }
    hideHoverTimer = setTimeout(() => {
      setHoveredCard(null);
      hideHoverTimer = null;
    }, 280);
  };

  const handlePopoverMouseEnter = () => {
    if (hideHoverTimer) {
      clearTimeout(hideHoverTimer);
      hideHoverTimer = null;
    }
  };

  const handlePopoverMouseLeave = () => {
    if (hideHoverTimer) {
      clearTimeout(hideHoverTimer);
    }
    hideHoverTimer = setTimeout(() => {
      setHoveredCard(null);
      hideHoverTimer = null;
    }, 280);
  };

  const toggleTheme = () => {
    setTheme((prev) => (prev === 'dark' ? 'light' : 'dark'));
  };

  // Abrir la pantalla completa de detalle y estadísticas de una carta
  const handleOpenCardDetail = (card: CardSummary | { uuid: string }) => {
    if (hideHoverTimer) {
      clearTimeout(hideHoverTimer);
      hideHoverTimer = null;
    }
    setHoveredCard(null);
    setActiveCardUuid(card.uuid);
    window.location.hash = `#/card/${card.uuid}`;
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleNavigateToIngestion = () => {
    setActiveCardUuid(null);
    setCurrentView('ingestion');
    window.location.hash = '#/ingestion';
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleBackToCatalog = () => {
    setActiveCardUuid(null);
    setCurrentView('catalog');
    if (window.location.hash) {
      window.location.hash = '';
      if (window.history.replaceState) {
        window.history.replaceState(null, '', window.location.pathname + window.location.search);
      }
    }
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  return (
    <div style={{ minHeight: '100vh', display: 'flex', 'flex-direction': 'column', background: 'var(--m3-surface)' }}>
      <Show
        when={activeCardUuid()}
        fallback={
          <Show
            when={currentView() === 'ingestion'}
            fallback={
              <>
                {/* 1. Top App Bar M3 */}
                <TopAppBar
                  searchTerm={filters().q || ''}
                  onSearchChange={(q) => handleFilterChange({ q, page: 1 })}
                  totalCards={cardsData()?.total || metadata()?.total_cards_count || 0}
                  onToggleSidebar={() => setIsSidebarOpen((prev) => !prev)}
                  isSidebarOpen={isSidebarOpen()}
                  theme={theme()}
                  onToggleTheme={toggleTheme}
                  currentView={currentView()}
                  onNavigateToIngestion={handleNavigateToIngestion}
                  onNavigateToCatalog={handleBackToCatalog}
                />

                {/* 2. Contenedor Principal: Sidebar + Grid */}
                <div style={{ display: 'flex', flex: 1, position: 'relative' }}>
                  <FilterSidebar
                    filters={filters()}
                    onFilterChange={handleFilterChange}
                    onResetFilters={handleResetFilters}
                    metadata={metadata()}
                    isOpen={isSidebarOpen()}
                  />

                  <main style={{ flex: 1, minWidth: 0, overflowX: 'hidden' }}>
                    <CardGrid
                      data={cardsData()}
                      loading={cardsData.loading}
                      onHoverStart={handleHoverStart}
                      onHoverEnd={handleHoverEnd}
                      onCardClick={handleOpenCardDetail}
                      onPageChange={(page) => handleFilterChange({ page })}
                      onResetFilters={handleResetFilters}
                    />
                  </main>
                </div>

                {/* 3. Popover Flotante de Hover con Ordenamiento de Precios por Tienda */}
                <Show when={hoveredCard()}>
                  {(hover) => (
                    <CardHoverDetails
                      card={hover().card}
                      position={hover().position}
                      onCardClick={handleOpenCardDetail}
                      onMouseEnter={handlePopoverMouseEnter}
                      onMouseLeave={handlePopoverMouseLeave}
                    />
                  )}
                </Show>

                {/* 4. Modal de Detalle Rápido */}
                <CardDetailModal
                  cardSummary={selectedModalCard()}
                  onClose={() => setSelectedModalCard(null)}
                />
              </>
            }
          >
            <IngestionScreen onBackToCatalog={handleBackToCatalog} />
          </Show>
        }
      >
        <CardDetailScreen
          uuid={activeCardUuid()!}
          onBack={handleBackToCatalog}
        />
      </Show>
    </div>
  );
};
