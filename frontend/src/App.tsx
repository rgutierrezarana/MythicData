import { Component, createSignal, createResource, createEffect, onMount, onCleanup, Show } from 'solid-js';
import { CardFilterParams, CardSummary } from './types/card';
import { fetchCards, fetchFilterMetadata } from './services/api';
import { TopAppBar } from './components/TopAppBar';
import { FilterSidebar } from './components/FilterSidebar';
import { CardGrid } from './components/CardGrid';
import { CardHoverDetails } from './components/CardHoverDetails';
import { CardDetailScreen } from './components/CardDetailScreen';
import { CardDetailModal } from './components/CardDetailModal';

export const App: Component = () => {
  // Estado de Navegación y Pantalla Activa
  const [activeCardUuid, setActiveCardUuid] = createSignal<string | null>(null);

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
  const [hoveredCard, setHoveredCard] = createSignal<{ card: CardSummary; position: { x: number; y: number } } | null>(null);
  const [selectedModalCard, setSelectedModalCard] = createSignal<CardSummary | null>(null);

  // Carga de Metadatos de Filtros
  const [metadata] = createResource(fetchFilterMetadata);

  // Carga de Cartas con Parámetros Reactivos
  const [cardsData] = createResource(
    () => ({ ...filters() }),
    (currentFilters) => fetchCards(currentFilters)
  );

  // Sincronización con Hash URL (#/card/:uuid)
  const syncHashWithState = () => {
    const hash = window.location.hash;
    if (hash.startsWith('#/card/')) {
      const uuid = hash.replace('#/card/', '').trim();
      if (uuid) {
        setActiveCardUuid(uuid);
        return;
      }
    }
    setActiveCardUuid(null);
  };

  onMount(() => {
    syncHashWithState();
    window.addEventListener('hashchange', syncHashWithState);
    window.addEventListener('popstate', syncHashWithState);
  });

  onCleanup(() => {
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
    setHoveredCard({
      card,
      position: { x: e.clientX, y: e.clientY }
    });
  };

  const handleHoverEnd = () => {
    setHoveredCard(null);
  };

  const toggleTheme = () => {
    setTheme((prev) => (prev === 'dark' ? 'light' : 'dark'));
  };

  // Abrir la pantalla completa de detalle y estadísticas de una carta
  const handleOpenCardDetail = (card: CardSummary | { uuid: string }) => {
    setHoveredCard(null);
    setActiveCardUuid(card.uuid);
    window.location.hash = `#/card/${card.uuid}`;
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleBackToCatalog = () => {
    setActiveCardUuid(null);
    if (window.location.hash) {
      history.pushState(null, '', window.location.pathname + window.location.search);
    }
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  return (
    <div style={{ minHeight: '100vh', display: 'flex', 'flex-direction': 'column', background: 'var(--m3-surface)' }}>
      <Show
        when={activeCardUuid()}
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
        {(uuid) => (
          <CardDetailScreen
            uuid={uuid()}
            onBack={handleBackToCatalog}
          />
        )}
      </Show>
    </div>
  );
};
