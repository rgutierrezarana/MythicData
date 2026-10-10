import { Component, createSignal, createResource, Show, For, createMemo } from 'solid-js';
import { CardDetail, CardPriceHistoryResponse, PriceHistoryFilterParams, PriceHistoryItem } from '../types/card';
import { fetchCardDetail, fetchCardPriceHistory } from '../services/api';
import { ManaSymbol } from './ManaSymbol';

interface CardDetailScreenProps {
  uuid: string;
  onBack: () => void;
}

export const CardDetailScreen: Component<CardDetailScreenProps> = (props) => {
  // 1. Estado de Filtros para Estadísticas de Precios
  const [selectedProvider, setSelectedProvider] = createSignal<string>('all');
  const [selectedFinish, setSelectedFinish] = createSignal<string>('all');
  const [selectedFormat, setSelectedFormat] = createSignal<string>('all');
  const [selectedPriceType, setSelectedPriceType] = createSignal<string>('all');
  const [selectedCurrency, setSelectedCurrency] = createSignal<string>('USD');
  const [selectedDays, setSelectedDays] = createSignal<number>(30); // 7, 30, 90, 180, 0 (todos)

  // Estado para ordenamiento de tabla de historial
  const [tableSort, setTableSort] = createSignal<'date_desc' | 'date_asc' | 'price_desc' | 'price_asc' | 'diff_desc'>('date_desc');
  // Estado para tooltip interactivo del gráfico SVG
  const [hoveredPoint, setHoveredPoint] = createSignal<{ item: PriceHistoryItem; x: number; y: number } | null>(null);

  // Estado para controles de tamaño de gráfica (Ejes X / Y) y Zoom interactivo
  const [chartWidth, setChartWidth] = createSignal<number>(840);
  const [chartHeight, setChartHeight] = createSignal<number>(300);
  const [zoomLevel, setZoomLevel] = createSignal<number>(1);
  const [panPosition, setPanPosition] = createSignal<number>(0);
  const [showPointValues, setShowPointValues] = createSignal<boolean>(false);

  // 2. Recursos Asíncronos
  const [cardDetail] = createResource(
    () => props.uuid,
    (uuid) => {
      if (!uuid) return Promise.resolve(null as any);
      return fetchCardDetail(uuid);
    }
  );

  const filterParams = createMemo<PriceHistoryFilterParams>(() => ({
    provider: selectedProvider(),
    finish: selectedFinish(),
    game_format: selectedFormat(),
    price_type: selectedPriceType(),
    currency: selectedCurrency(),
    days: selectedDays() > 0 ? selectedDays() : undefined,
  }));

  const [priceHistoryData, { refetch: refetchHistory }] = createResource(
    () => (props.uuid ? { uuid: props.uuid, params: filterParams() } : null),
    (source) => {
      if (!source || !source.uuid) return Promise.resolve(null as any);
      return fetchCardPriceHistory(source.uuid, source.params);
    }
  );

  const getRarityClass = (rarity?: string) => {
    const r = (rarity || '').toLowerCase();
    if (r === 'mythic') return 'rarity-mythic';
    if (r === 'rare') return 'rarity-rare';
    if (r === 'uncommon') return 'rarity-uncommon';
    return 'rarity-common';
  };

  // 3. Preparación de datos ordenados para la tabla
  const sortedHistoryTable = createMemo(() => {
    const raw = priceHistoryData()?.history || [];
    const list = [...raw];
    const sortMode = tableSort();

    return list.sort((a, b) => {
      if (sortMode === 'date_desc') return b.price_date.localeCompare(a.price_date);
      if (sortMode === 'date_asc') return a.price_date.localeCompare(b.price_date);
      if (sortMode === 'price_desc') return b.price - a.price;
      if (sortMode === 'price_asc') return a.price - b.price;
      if (sortMode === 'diff_desc') {
        const diffA = a.price_diff ?? 0;
        const diffB = b.price_diff ?? 0;
        return Math.abs(diffB) - Math.abs(diffA);
      }
      return 0;
    });
  });

  // 4. Cálculos para el Gráfico SVG con Soporte Dinámico de Dimensiones, Zoom y Reajuste de Escala
  const chartData = createMemo(() => {
    const rawHistory = priceHistoryData()?.history || [];
    if (rawHistory.length === 0) return null;

    const curr = selectedCurrency() === 'EUR' ? '€' : '$';
    const totalPoints = rawHistory.length;
    const zoom = zoomLevel();
    const pan = panPosition();

    // 1. Filtrar puntos visibles según el Zoom y Pan
    let history: PriceHistoryItem[] = [];
    let startIndex = 0;
    let endIndex = totalPoints;

    if (zoom <= 1 || totalPoints <= 2) {
      history = rawHistory;
    } else {
      const visibleCount = Math.max(2, Math.round(totalPoints / zoom));
      const maxStartIndex = Math.max(0, totalPoints - visibleCount);
      startIndex = Math.round((pan / 100) * maxStartIndex);
      endIndex = Math.min(totalPoints, startIndex + visibleCount);
      history = rawHistory.slice(startIndex, endIndex);
    }

    if (history.length === 0) return null;

    // 2. Dimensiones y paddings
    const width = chartWidth();
    const height = chartHeight();
    const padding = { top: 32, right: 36, bottom: 44, left: 66 };
    const innerWidth = Math.max(100, width - padding.left - padding.right);
    const innerHeight = Math.max(60, height - padding.top - padding.bottom);

    // 3. Reajuste de escala Y dinámico basado EXCLUSIVAMENTE en los puntos visibles
    const visiblePrices = history.map((h) => h.price);
    const rawMin = Math.min(...visiblePrices);
    const rawMax = Math.max(...visiblePrices);

    let minP = rawMin;
    let maxP = rawMax;

    if (rawMax === rawMin) {
      minP = Math.max(0, rawMin * 0.9);
      maxP = rawMax === 0 ? 1 : rawMax * 1.1;
    } else {
      const margin = (rawMax - rawMin) * 0.08;
      minP = Math.max(0, rawMin - margin);
      maxP = rawMax + margin;
    }

    const rangeP = maxP - minP || 1;

    // 4. Calcular coordenadas de puntos (X, Y)
    const points = history.map((item, index) => {
      const x = padding.left + (index / Math.max(1, history.length - 1)) * innerWidth;
      const y = padding.top + innerHeight - ((item.price - minP) / rangeP) * innerHeight;
      return { x, y, item, index: startIndex + index };
    });

    // 5. SVG Path de la línea de precios
    const pathD = points.reduce((acc, pt, idx) => {
      return idx === 0 ? `M ${pt.x},${pt.y}` : `${acc} L ${pt.x},${pt.y}`;
    }, '');

    // 6. SVG Path del área sombreada con degradado
    const areaD = `${pathD} L ${points[points.length - 1].x},${padding.top + innerHeight} L ${points[0].x},${padding.top + innerHeight} Z`;

    // 7. Niveles de precio Y recalculados dinámicamente
    const yLevels = [
      { price: maxP, y: padding.top },
      { price: minP + rangeP * 0.75, y: padding.top + innerHeight * 0.25 },
      { price: minP + rangeP * 0.50, y: padding.top + innerHeight * 0.50 },
      { price: minP + rangeP * 0.25, y: padding.top + innerHeight * 0.75 },
      { price: minP, y: padding.top + innerHeight },
    ];

    // 8. Fechas para el eje X
    const firstDate = history[0]?.price_date;
    const lastDate = history[history.length - 1]?.price_date;
    const midDate = history[Math.floor(history.length / 2)]?.price_date;

    return {
      width,
      height,
      padding,
      innerWidth,
      innerHeight,
      minP,
      maxP,
      rawMin,
      rawMax,
      curr,
      totalPoints,
      visibleCount: history.length,
      startIndex,
      endIndex,
      points,
      pathD,
      areaD,
      yLevels,
      firstDate,
      lastDate,
      midDate,
    };
  });

  return (
    <div
      class="animate-fade-in"
      style={{
        minHeight: '100vh',
        background: 'var(--m3-surface)',
        color: 'var(--m3-on-surface)',
        display: 'flex',
        'flex-direction': 'column',
      }}
    >
      {/* 1. Barra Superior de Navegación y Volver */}
      <header
        style={{
          background: 'var(--m3-surface-container)',
          'border-bottom': '1px solid var(--m3-outline-variant)',
          padding: '12px 24px',
          display: 'flex',
          'align-items': 'center',
          'justify-content': 'space-between',
          position: 'sticky',
          top: 0,
          'z-index': 40,
          'backdrop-filter': 'blur(12px)',
        }}
      >
        <div style={{ display: 'flex', 'align-items': 'center', gap: '16px' }}>
          <button
            type="button"
            class="m3-btn m3-btn-tonal"
            onClick={() => props.onBack()}
            style={{ height: '38px', padding: '0 16px', gap: '6px', cursor: 'pointer' }}
          >
            <span class="material-symbols-outlined" style={{ 'font-size': '20px' }}>
              arrow_back
            </span>
            <span>Volver al Catálogo</span>
          </button>

          <nav aria-label="Breadcrumbs" style={{ display: 'flex', 'align-items': 'center', gap: '8px', 'font-size': '0.875rem' }}>
            <button
              type="button"
              onClick={() => props.onBack()}
              style={{
                background: 'transparent',
                border: 'none',
                padding: '4px 6px',
                'border-radius': '6px',
                color: 'var(--m3-on-surface-variant)',
                cursor: 'pointer',
                'font-size': '0.875rem',
                'font-family': 'inherit',
                'font-weight': 500,
                display: 'inline-flex',
                'align-items': 'center',
                transition: 'all 0.2s ease',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.color = 'var(--m3-primary)';
                e.currentTarget.style.background = 'rgba(208, 188, 255, 0.1)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.color = 'var(--m3-on-surface-variant)';
                e.currentTarget.style.background = 'transparent';
              }}
              title="Volver al Catálogo principal"
            >
              Catálogo
            </button>
            <span style={{ color: 'var(--m3-outline)' }}>/</span>
            <span style={{ color: 'var(--m3-on-surface-variant)' }}>
              {cardDetail()?.set_name || cardDetail()?.set_code || 'Set'}
            </span>
            <span style={{ color: 'var(--m3-outline)' }}>/</span>
            <span style={{ 'font-weight': 700, color: 'var(--m3-primary)' }}>
              {cardDetail()?.name || 'Cargando carta...'}
            </span>
          </nav>
        </div>

        {/* Enlaces Rápidos Externos */}
        <div style={{ display: 'flex', 'align-items': 'center', gap: '8px' }}>
          <Show when={cardDetail()?.scryfall_id}>
            <a
              href={`https://scryfall.com/card/${cardDetail()?.set_code?.toLowerCase()}/${cardDetail()?.collector_number}`}
              target="_blank"
              rel="noreferrer"
              class="m3-btn m3-btn-outlined"
              style={{ height: '34px', padding: '0 12px', 'font-size': '0.75rem', gap: '4px', 'text-decoration': 'none' }}
            >
              <span class="material-symbols-outlined" style={{ 'font-size': '16px' }}>open_in_new</span>
              Scryfall
            </a>
          </Show>
          <Show when={cardDetail()?.tcgplayer_product_id}>
            <a
              href={`https://www.tcgplayer.com/product/${cardDetail()?.tcgplayer_product_id}`}
              target="_blank"
              rel="noreferrer"
              class="m3-btn m3-btn-filled"
              style={{ height: '34px', padding: '0 12px', 'font-size': '0.75rem', gap: '4px', 'text-decoration': 'none' }}
            >
              <span class="material-symbols-outlined" style={{ 'font-size': '16px' }}>shopping_bag</span>
              TCGPlayer
            </a>
          </Show>
        </div>
      </header>

      {/* 2. Contenido Principal */}
      <main style={{ flex: 1, padding: '24px', 'max-width': '1440px', margin: '0 auto', width: '100%' }}>
        <Show
          when={!cardDetail.loading && cardDetail()}
          fallback={
            <div style={{ display: 'flex', 'flex-direction': 'column', 'align-items': 'center', 'justify-content': 'center', padding: '80px', gap: '20px' }}>
              <div class="skeleton" style={{ width: '64px', height: '64px', 'border-radius': '50%' }}></div>
              <p style={{ color: 'var(--m3-on-surface-variant)', 'font-size': '1.125rem' }}>
                Cargando información y series históricas de la carta...
              </p>
            </div>
          }
        >
          <div
            style={{
              display: 'grid',
              'grid-template-columns': 'minmax(300px, 380px) 1fr',
              gap: '32px',
              'align-items': 'start',
            }}
          >
            {/* =========================================================================
                COLUMNA IZQUIERDA: Carta, Ilustración, Specs, Oracle Text
                ========================================================================= */}
            <section style={{ display: 'flex', 'flex-direction': 'column', gap: '20px' }}>
              {/* Contenedor de Imagen con Efecto Elevado */}
              <div
                style={{
                  background: 'var(--m3-surface-container)',
                  'border-radius': '20px',
                  border: '1px solid var(--m3-outline-variant)',
                  padding: '12px',
                  'box-shadow': 'var(--shadow-3)',
                  display: 'flex',
                  'flex-direction': 'column',
                  'align-items': 'center',
                }}
              >
                <div
                  style={{
                    width: '100%',
                    'aspect-ratio': '5 / 7',
                    'border-radius': '14px',
                    overflow: 'hidden',
                    background: 'var(--m3-surface-container-lowest)',
                    border: '1px solid var(--m3-outline-variant)',
                    display: 'flex',
                    'align-items': 'center',
                    'justify-content': 'center',
                  }}
                >
                  <Show
                    when={cardDetail()?.image_url_large || cardDetail()?.image_url}
                    fallback={
                      <div style={{ 'text-align': 'center', color: 'var(--m3-outline)', padding: '24px' }}>
                        <span class="material-symbols-outlined" style={{ 'font-size': '54px' }}>image_not_supported</span>
                        <p style={{ 'font-size': '0.875rem', 'margin-top': '8px' }}>Imagen no disponible</p>
                      </div>
                    }
                  >
                    <img
                      src={cardDetail()?.image_url_large || cardDetail()?.image_url}
                      alt={cardDetail()?.name}
                      style={{ width: '100%', height: '100%', 'object-fit': 'contain' }}
                    />
                  </Show>
                </div>
              </div>

              {/* Tarjeta de Especificaciones de la Carta */}
              <div
                style={{
                  background: 'var(--m3-surface-container)',
                  'border-radius': '16px',
                  border: '1px solid var(--m3-outline-variant)',
                  padding: '18px',
                  display: 'flex',
                  'flex-direction': 'column',
                  gap: '14px',
                }}
              >
                <div style={{ display: 'flex', 'align-items': 'center', 'justify-content': 'space-between' }}>
                  <span class={`rarity-badge ${getRarityClass(cardDetail()?.rarity)}`}>
                    {cardDetail()?.rarity || 'Common'}
                  </span>
                  <span style={{ 'font-size': '0.8125rem', color: 'var(--m3-on-surface-variant)' }}>
                    CMC: <strong>{cardDetail()?.mana_value ?? 0}</strong>
                  </span>
                </div>

                <Show when={cardDetail()?.oracle_text}>
                  <div
                    style={{
                      background: 'var(--m3-surface-container-high)',
                      'border-radius': '10px',
                      padding: '12px 14px',
                      border: '1px solid var(--m3-outline-variant)',
                      'font-size': '0.875rem',
                      'line-height': 1.5,
                      'white-space': 'pre-line',
                    }}
                  >
                    {cardDetail()?.oracle_text}
                  </div>
                </Show>

                {/* Grid de Metadatos */}
                <div
                  style={{
                    display: 'grid',
                    'grid-template-columns': '1fr 1fr',
                    gap: '10px',
                    'font-size': '0.8125rem',
                  }}
                >
                  <div style={{ background: 'var(--m3-surface-container-low)', padding: '8px 10px', 'border-radius': '8px' }}>
                    <span style={{ color: 'var(--m3-on-surface-variant)', 'font-size': '0.6875rem', display: 'block' }}>Set</span>
                    <strong>{cardDetail()?.set_name} ({cardDetail()?.set_code})</strong>
                  </div>
                  <div style={{ background: 'var(--m3-surface-container-low)', padding: '8px 10px', 'border-radius': '8px' }}>
                    <span style={{ color: 'var(--m3-on-surface-variant)', 'font-size': '0.6875rem', display: 'block' }}>Coleccionista</span>
                    <strong>#{cardDetail()?.collector_number || 'N/D'}</strong>
                  </div>
                  <div style={{ background: 'var(--m3-surface-container-low)', padding: '8px 10px', 'border-radius': '8px' }}>
                    <span style={{ color: 'var(--m3-on-surface-variant)', 'font-size': '0.6875rem', display: 'block' }}>Ilustrador</span>
                    <strong>{cardDetail()?.artist || 'N/D'}</strong>
                  </div>
                  <div style={{ background: 'var(--m3-surface-container-low)', padding: '8px 10px', 'border-radius': '8px' }}>
                    <span style={{ color: 'var(--m3-on-surface-variant)', 'font-size': '0.6875rem', display: 'block' }}>Acabados</span>
                    <strong>{cardDetail()?.finishes || 'Normal / Foil'}</strong>
                  </div>
                </div>
              </div>
            </section>

            {/* =========================================================================
                COLUMNA DERECHA: Estadísticas de Precios, Filtros Dinámicos, Gráficas y Tabla
                ========================================================================= */}
            <section style={{ display: 'flex', 'flex-direction': 'column', gap: '24px' }}>
              {/* Encabezado del Detalle: Nombre + Coste */}
              <div
                style={{
                  background: 'var(--m3-surface-container)',
                  'border-radius': '20px',
                  border: '1px solid var(--m3-outline-variant)',
                  padding: '20px 24px',
                  display: 'flex',
                  'align-items': 'center',
                  'justify-content': 'space-between',
                  'flex-wrap': 'wrap',
                  gap: '16px',
                }}
              >
                <div>
                  <h1 style={{ 'font-size': '1.75rem', 'font-weight': 800, 'letter-spacing': '-0.5px' }}>
                    {cardDetail()?.name}
                  </h1>
                  <p style={{ 'font-size': '0.9375rem', color: 'var(--m3-on-surface-variant)', 'margin-top': '4px' }}>
                    {cardDetail()?.type_line}
                  </p>
                </div>

                <Show when={cardDetail()?.mana_cost}>
                  <div style={{ display: 'flex', 'align-items': 'center', gap: '6px' }}>
                    <ManaSymbol cost={cardDetail()!.mana_cost!} size="lg" />
                  </div>
                </Show>
              </div>

              {/* =====================================================================
                  BARRA DE FILTROS DINÁMICOS PARA ESTADÍSTICAS DE PRECIO
                  ===================================================================== */}
              <div
                style={{
                  background: 'var(--m3-surface-container-high)',
                  'border-radius': '16px',
                  border: '1px solid var(--m3-outline-variant)',
                  padding: '16px 20px',
                  display: 'flex',
                  'flex-direction': 'column',
                  gap: '14px',
                }}
              >
                <div style={{ display: 'flex', 'align-items': 'center', 'justify-content': 'space-between' }}>
                  <div style={{ display: 'flex', 'align-items': 'center', gap: '8px' }}>
                    <span class="material-symbols-outlined" style={{ color: 'var(--m3-primary)', 'font-size': '20px' }}>
                      tune
                    </span>
                    <span style={{ 'font-weight': 700, 'font-size': '0.9375rem' }}>
                      Filtros de Análisis de Precios
                    </span>
                  </div>

                  <button
                    class="m3-btn m3-btn-tonal"
                    style={{ height: '30px', padding: '0 10px', 'font-size': '0.75rem' }}
                    onClick={() => {
                      setSelectedProvider('all');
                      setSelectedFinish('all');
                      setSelectedFormat('all');
                      setSelectedPriceType('all');
                      setSelectedCurrency('USD');
                      setSelectedDays(30);
                    }}
                  >
                    Restablecer Filtros
                  </button>
                </div>

                {/* Controles de Filtros: Tienda, Acabado, Formato, Moneda, Rango de Días */}
                <div
                  style={{
                    display: 'grid',
                    'grid-template-columns': 'repeat(auto-fit, minmax(140px, 1fr))',
                    gap: '12px',
                  }}
                >
                  {/* 1. Filtro por Tienda / Proveedor */}
                  <div style={{ display: 'flex', 'flex-direction': 'column', gap: '4px' }}>
                    <label style={{ 'font-size': '0.6875rem', 'font-weight': 600, color: 'var(--m3-on-surface-variant)', 'text-transform': 'uppercase' }}>
                      Tienda / Proveedor
                    </label>
                    <select
                      value={selectedProvider()}
                      onChange={(e) => setSelectedProvider(e.currentTarget.value)}
                      style={{
                        height: '36px',
                        background: 'var(--m3-surface-container-lowest)',
                        border: '1px solid var(--m3-outline-variant)',
                        'border-radius': '8px',
                        color: 'var(--m3-on-surface)',
                        padding: '0 8px',
                        'font-size': '0.8125rem',
                        outline: 'none',
                        cursor: 'pointer',
                      }}
                    >
                      <option value="all">Todas las Tiendas</option>
                      <For each={priceHistoryData()?.available_filters?.providers || ['tcgplayer', 'cardmarket', 'cardkingdom', 'manapool', 'cardhoarder']}>
                        {(prov) => <option value={prov}>{prov.toUpperCase()}</option>}
                      </For>
                    </select>
                  </div>

                  {/* 2. Filtro por Acabado (Foil / Normal) */}
                  <div style={{ display: 'flex', 'flex-direction': 'column', gap: '4px' }}>
                    <label style={{ 'font-size': '0.6875rem', 'font-weight': 600, color: 'var(--m3-on-surface-variant)', 'text-transform': 'uppercase' }}>
                      Acabado / Foil
                    </label>
                    <select
                      value={selectedFinish()}
                      onChange={(e) => setSelectedFinish(e.currentTarget.value)}
                      style={{
                        height: '36px',
                        background: 'var(--m3-surface-container-lowest)',
                        border: '1px solid var(--m3-outline-variant)',
                        'border-radius': '8px',
                        color: 'var(--m3-on-surface)',
                        padding: '0 8px',
                        'font-size': '0.8125rem',
                        outline: 'none',
                        cursor: 'pointer',
                      }}
                    >
                      <option value="all">Todos los Acabados</option>
                      <option value="normal">Normal (Non-foil)</option>
                      <option value="foil">Foil ✨</option>
                      <option value="etched">Etched Foil</option>
                    </select>
                  </div>

                  {/* 3. Filtro por Formato / Versión */}
                  <div style={{ display: 'flex', 'flex-direction': 'column', gap: '4px' }}>
                    <label style={{ 'font-size': '0.6875rem', 'font-weight': 600, color: 'var(--m3-on-surface-variant)', 'text-transform': 'uppercase' }}>
                      Versión / Canal
                    </label>
                    <select
                      value={selectedPriceType()}
                      onChange={(e) => setSelectedPriceType(e.currentTarget.value)}
                      style={{
                        height: '36px',
                        background: 'var(--m3-surface-container-lowest)',
                        border: '1px solid var(--m3-outline-variant)',
                        'border-radius': '8px',
                        color: 'var(--m3-on-surface)',
                        padding: '0 8px',
                        'font-size': '0.8125rem',
                        outline: 'none',
                        cursor: 'pointer',
                      }}
                    >
                      <option value="all">Todos los Canales</option>
                      <option value="retail">Retail (Venta)</option>
                      <option value="buylist">Buylist (Compra)</option>
                    </select>
                  </div>

                  {/* 4. Filtro por Moneda */}
                  <div style={{ display: 'flex', 'flex-direction': 'column', gap: '4px' }}>
                    <label style={{ 'font-size': '0.6875rem', 'font-weight': 600, color: 'var(--m3-on-surface-variant)', 'text-transform': 'uppercase' }}>
                      Moneda
                    </label>
                    <select
                      value={selectedCurrency()}
                      onChange={(e) => setSelectedCurrency(e.currentTarget.value)}
                      style={{
                        height: '36px',
                        background: 'var(--m3-surface-container-lowest)',
                        border: '1px solid var(--m3-outline-variant)',
                        'border-radius': '8px',
                        color: 'var(--m3-on-surface)',
                        padding: '0 8px',
                        'font-size': '0.8125rem',
                        outline: 'none',
                        cursor: 'pointer',
                      }}
                    >
                      <option value="USD">USD ($ Dólar)</option>
                      <option value="EUR">EUR (€ Euro)</option>
                      <option value="ALL">Todas las Monedas</option>
                    </select>
                  </div>

                  {/* 5. Selector de Rango Temporal */}
                  <div style={{ display: 'flex', 'flex-direction': 'column', gap: '4px', 'grid-column': 'span 2' }}>
                    <label style={{ 'font-size': '0.6875rem', 'font-weight': 600, color: 'var(--m3-on-surface-variant)', 'text-transform': 'uppercase' }}>
                      Ventana Temporal
                    </label>
                    <div style={{ display: 'flex', gap: '6px', 'flex-wrap': 'wrap' }}>
                      <For each={[
                        { label: '7 Días', days: 7 },
                        { label: '30 Días', days: 30 },
                        { label: '90 Días', days: 90 },
                        { label: '180 Días', days: 180 },
                        { label: 'Histórico Completo', days: 0 },
                      ]}>
                        {(btn) => (
                          <button
                            class={`m3-chip ${selectedDays() === btn.days ? 'active' : ''}`}
                            onClick={() => setSelectedDays(btn.days)}
                            style={{ height: '32px', 'font-size': '0.75rem' }}
                          >
                            {btn.label}
                          </button>
                        )}
                      </For>
                    </div>
                  </div>
                </div>
              </div>

              {/* =====================================================================
                  MACHINE LEARNING FORECAST (GBTRegressor PySpark MLlib)
                  ===================================================================== */}
              <Show when={cardDetail()?.prediction}>
                {(pred) => {
                  const isUp = pred().direction === 'UP';
                  const isDown = pred().direction === 'DOWN';
                  const trendColor = isUp ? '#10b981' : isDown ? '#ef4444' : '#a855f7';
                  const trendBg = isUp ? 'rgba(16, 185, 129, 0.14)' : isDown ? 'rgba(239, 68, 68, 0.14)' : 'rgba(168, 85, 247, 0.14)';
                  const trendIcon = isUp ? 'trending_up' : isDown ? 'trending_down' : 'trending_flat';
                  const changeSign = (pred().expected_change_pct || 0) > 0 ? '+' : '';

                  return (
                    <div
                      style={{
                        background: 'linear-gradient(135deg, rgba(168, 85, 247, 0.12) 0%, rgba(59, 130, 246, 0.06) 100%)',
                        'border-radius': '20px',
                        border: '1.5px solid rgba(168, 85, 247, 0.4)',
                        padding: '20px 24px',
                        display: 'flex',
                        'flex-direction': 'column',
                        gap: '16px',
                        'box-shadow': '0 8px 32px rgba(0, 0, 0, 0.2)',
                      }}
                    >
                      {/* Cabecera del Modelo ML */}
                      <div style={{ display: 'flex', 'align-items': 'center', 'justify-content': 'space-between', 'flex-wrap': 'wrap', gap: '12px' }}>
                        <div style={{ display: 'flex', 'align-items': 'center', gap: '12px' }}>
                          <span
                            class="material-symbols-outlined"
                            style={{
                              background: 'linear-gradient(135deg, #a855f7, #6366f1)',
                              color: '#fff',
                              padding: '10px',
                              'border-radius': '12px',
                              'font-size': '24px',
                              'box-shadow': '0 4px 12px rgba(168, 85, 247, 0.4)',
                            }}
                          >
                            psychology
                          </span>
                          <div>
                            <div style={{ 'font-size': '1.0625rem', 'font-weight': 800, color: 'var(--m3-on-surface)' }}>
                              Pronóstico de Próximo Precio (Apache Spark MLlib)
                            </div>
                            <div style={{ 'font-size': '0.75rem', color: 'var(--m3-on-surface-variant)', 'margin-top': '2px' }}>
                              Algoritmo: Gradient Boosted Trees ({pred().model_name}) · Serie Temporal con Lags
                            </div>
                          </div>
                        </div>

                        <div style={{ display: 'flex', 'align-items': 'center', gap: '8px' }}>
                          <span
                            style={{
                              background: 'rgba(168, 85, 247, 0.18)',
                              color: '#c084fc',
                              border: '1px solid rgba(168, 85, 247, 0.35)',
                              padding: '4px 10px',
                              'border-radius': '10px',
                              'font-size': '0.75rem',
                              'font-weight': 700,
                              display: 'flex',
                              'align-items': 'center',
                              gap: '6px',
                            }}
                          >
                            <span class="material-symbols-outlined" style={{ 'font-size': '16px' }}>verified</span>
                            {pred().confidence_score}% Precisión (R²)
                          </span>
                        </div>
                      </div>

                      {/* Comparativa de Precio Actual vs Predicho */}
                      <div
                        style={{
                          display: 'grid',
                          'grid-template-columns': 'repeat(auto-fit, minmax(180px, 1fr))',
                          gap: '14px',
                          background: 'var(--m3-surface-container)',
                          padding: '16px 20px',
                          'border-radius': '14px',
                          border: '1px solid var(--m3-outline-variant)',
                        }}
                      >
                        <div>
                          <div style={{ 'font-size': '0.75rem', color: 'var(--m3-on-surface-variant)', 'font-weight': 600 }}>
                            Precio Actual de Referencia
                          </div>
                          <div style={{ 'font-size': '1.375rem', 'font-weight': 800, color: 'var(--m3-on-surface)', 'margin-top': '4px' }}>
                            ${pred().current_price?.toFixed(2) || '0.00'} USD
                          </div>
                          <div style={{ 'font-size': '0.6875rem', color: 'var(--m3-outline)', 'margin-top': '2px' }}>
                            Última cotización en mercado
                          </div>
                        </div>

                        <div>
                          <div style={{ 'font-size': '0.75rem', color: '#c084fc', 'font-weight': 700 }}>
                            Próximo Precio Estimado (t+1)
                          </div>
                          <div style={{ 'font-size': '1.5rem', 'font-weight': 900, color: '#38bdf8', 'margin-top': '4px' }}>
                            ${pred().predicted_next_price?.toFixed(2) || '0.00'} USD
                          </div>
                          <div style={{ 'font-size': '0.6875rem', color: 'var(--m3-outline)', 'margin-top': '2px' }}>
                            Inferencia proyectada de Spark ML
                          </div>
                        </div>

                        <div style={{ display: 'flex', 'flex-direction': 'column', 'justify-content': 'center' }}>
                          <div style={{ 'font-size': '0.75rem', color: 'var(--m3-on-surface-variant)', 'font-weight': 600 }}>
                            Variación Esperada
                          </div>
                          <div
                            style={{
                              display: 'inline-flex',
                              'align-items': 'center',
                              gap: '6px',
                              background: trendBg,
                              color: trendColor,
                              padding: '6px 12px',
                              'border-radius': '10px',
                              'font-size': '0.9375rem',
                              'font-weight': 800,
                              width: 'fit-content',
                              'margin-top': '6px',
                            }}
                          >
                            <span class="material-symbols-outlined" style={{ 'font-size': '18px' }}>{trendIcon}</span>
                            {changeSign}{pred().expected_change_pct}% ({pred().direction === 'UP' ? 'Subida' : pred().direction === 'DOWN' ? 'Bajada' : 'Estable'})
                          </div>
                        </div>
                      </div>

                      {/* Explicación de Variables del Modelo */}
                      <div style={{ 'font-size': '0.75rem', color: 'var(--m3-outline)', display: 'flex', 'align-items': 'center', gap: '6px' }}>
                        <span class="material-symbols-outlined" style={{ 'font-size': '16px', color: '#c084fc' }}>insights</span>
                        Variables analizadas: Lags temporales (t-1, t-3, t-7), medias móviles (7d/14d), volatilidad estocástica, momentum y rareza de carta.
                      </div>
                    </div>
                  );
                }}
              </Show>

              {/* =====================================================================
                  KPI METRICS & STATS CARDS (Material Design 3 Surface Cards)
                  ===================================================================== */}
              <div
                style={{
                  display: 'grid',
                  'grid-template-columns': 'repeat(auto-fit, minmax(160px, 1fr))',
                  gap: '16px',
                }}
              >
                {/* 1. Precio Actual */}
                <div
                  style={{
                    background: 'var(--m3-surface-container)',
                    'border-radius': '16px',
                    border: '1px solid var(--m3-outline-variant)',
                    padding: '16px',
                    display: 'flex',
                    'flex-direction': 'column',
                    gap: '6px',
                  }}
                >
                  <span style={{ 'font-size': '0.75rem', color: 'var(--m3-on-surface-variant)', 'font-weight': 600 }}>
                    Precio Actual
                  </span>
                  <div style={{ display: 'flex', 'align-items': 'baseline', gap: '4px' }}>
                    <span style={{ 'font-size': '1.5rem', 'font-weight': 800, color: '#34d399' }}>
                      {priceHistoryData()?.stats?.current_price !== undefined && priceHistoryData()?.stats?.current_price !== null
                        ? `${selectedCurrency() === 'EUR' ? '€' : '$'}${priceHistoryData()!.stats.current_price!.toFixed(2)}`
                        : 'N/D'}
                    </span>
                  </div>
                  <span style={{ 'font-size': '0.6875rem', color: 'var(--m3-outline)' }}>
                    {priceHistoryData()?.stats?.total_points || 0} registros analizados
                  </span>
                </div>

                {/* 2. Variación de Precio (Absoluta y Porcentual) */}
                <div
                  style={{
                    background: 'var(--m3-surface-container)',
                    'border-radius': '16px',
                    border: '1px solid var(--m3-outline-variant)',
                    padding: '16px',
                    display: 'flex',
                    'flex-direction': 'column',
                    gap: '6px',
                  }}
                >
                  <span style={{ 'font-size': '0.75rem', color: 'var(--m3-on-surface-variant)', 'font-weight': 600 }}>
                    Cambio de Precio
                  </span>
                  <div style={{ display: 'flex', 'align-items': 'center', gap: '6px' }}>
                    <Show
                      when={priceHistoryData()?.stats?.price_diff !== undefined && priceHistoryData()?.stats?.price_diff !== null}
                      fallback={<span style={{ 'font-size': '1.25rem', 'font-weight': 700, color: 'var(--m3-outline)' }}>0.00</span>}
                    >
                      {(() => {
                        const diff = priceHistoryData()!.stats.price_diff!;
                        const pct = priceHistoryData()!.stats.pct_change!;
                        const isUp = diff > 0;
                        const isDown = diff < 0;
                        const color = isUp ? '#34d399' : isDown ? '#f87171' : 'var(--m3-on-surface)';

                        return (
                          <div style={{ display: 'flex', 'align-items': 'center', gap: '6px' }}>
                            <span
                              class="material-symbols-outlined"
                              style={{
                                color,
                                'font-size': '24px',
                                transform: isUp ? 'rotate(0deg)' : isDown ? 'rotate(180deg)' : 'none',
                              }}
                            >
                              {isUp || isDown ? 'trending_up' : 'trending_flat'}
                            </span>
                            <span style={{ 'font-size': '1.25rem', 'font-weight': 800, color }}>
                              {diff > 0 ? `+${diff.toFixed(2)}` : diff.toFixed(2)}
                            </span>
                            <span
                              style={{
                                background: isUp ? 'rgba(52, 211, 153, 0.15)' : isDown ? 'rgba(248, 113, 113, 0.15)' : 'rgba(255,255,255,0.08)',
                                color,
                                padding: '2px 6px',
                                'border-radius': '6px',
                                'font-size': '0.75rem',
                                'font-weight': 700,
                              }}
                            >
                              {pct !== undefined && pct !== null ? (pct > 0 ? `+${pct.toFixed(1)}%` : `${pct.toFixed(1)}%`) : '0%'}
                            </span>
                          </div>
                        );
                      })()}
                    </Show>
                  </div>
                  <span style={{ 'font-size': '0.6875rem', color: 'var(--m3-outline)' }}>
                    vs. precio anterior registrado
                  </span>
                </div>

                {/* 3. Mínimo Histórico */}
                <div
                  style={{
                    background: 'var(--m3-surface-container)',
                    'border-radius': '16px',
                    border: '1px solid var(--m3-outline-variant)',
                    padding: '16px',
                    display: 'flex',
                    'flex-direction': 'column',
                    gap: '6px',
                  }}
                >
                  <span style={{ 'font-size': '0.75rem', color: 'var(--m3-on-surface-variant)', 'font-weight': 600 }}>
                    Mínimo en Período
                  </span>
                  <span style={{ 'font-size': '1.375rem', 'font-weight': 800, color: 'var(--m3-primary)' }}>
                    {priceHistoryData()?.stats?.min_price !== undefined && priceHistoryData()?.stats?.min_price !== null
                      ? `${selectedCurrency() === 'EUR' ? '€' : '$'}${priceHistoryData()!.stats.min_price!.toFixed(2)}`
                      : 'N/D'}
                  </span>
                  <span style={{ 'font-size': '0.6875rem', color: 'var(--m3-outline)' }}>
                    Mejor cotización registrada
                  </span>
                </div>

                {/* 4. Máximo Histórico */}
                <div
                  style={{
                    background: 'var(--m3-surface-container)',
                    'border-radius': '16px',
                    border: '1px solid var(--m3-outline-variant)',
                    padding: '16px',
                    display: 'flex',
                    'flex-direction': 'column',
                    gap: '6px',
                  }}
                >
                  <span style={{ 'font-size': '0.75rem', color: 'var(--m3-on-surface-variant)', 'font-weight': 600 }}>
                    Máximo en Período
                  </span>
                  <span style={{ 'font-size': '1.375rem', 'font-weight': 800, color: 'var(--m3-gold)' }}>
                    {priceHistoryData()?.stats?.max_price !== undefined && priceHistoryData()?.stats?.max_price !== null
                      ? `${selectedCurrency() === 'EUR' ? '€' : '$'}${priceHistoryData()!.stats.max_price!.toFixed(2)}`
                      : 'N/D'}
                  </span>
                  <span style={{ 'font-size': '0.6875rem', color: 'var(--m3-outline)' }}>
                    Pico más alto registrado
                  </span>
                </div>

                {/* 5. Promedio */}
                <div
                  style={{
                    background: 'var(--m3-surface-container)',
                    'border-radius': '16px',
                    border: '1px solid var(--m3-outline-variant)',
                    padding: '16px',
                    display: 'flex',
                    'flex-direction': 'column',
                    gap: '6px',
                  }}
                >
                  <span style={{ 'font-size': '0.75rem', color: 'var(--m3-on-surface-variant)', 'font-weight': 600 }}>
                    Precio Promedio
                  </span>
                  <span style={{ 'font-size': '1.375rem', 'font-weight': 800, color: 'var(--m3-secondary)' }}>
                    {priceHistoryData()?.stats?.avg_price !== undefined && priceHistoryData()?.stats?.avg_price !== null
                      ? `${selectedCurrency() === 'EUR' ? '€' : '$'}${priceHistoryData()!.stats.avg_price!.toFixed(2)}`
                      : 'N/D'}
                  </span>
                  <span style={{ 'font-size': '0.6875rem', color: 'var(--m3-outline)' }}>
                    Media ponderada
                  </span>
                </div>
              </div>

              {/* =====================================================================
                  GRÁFICA INTERACTIVA DE EVOLUCIÓN TEMPORAL DE PRECIOS CON CONTROLES
                  ===================================================================== */}
              <div
                style={{
                  background: 'var(--m3-surface-container)',
                  'border-radius': '20px',
                  border: '1px solid var(--m3-outline-variant)',
                  padding: '20px',
                  display: 'flex',
                  'flex-direction': 'column',
                  gap: '16px',
                  position: 'relative',
                }}
              >
                {/* Cabecera de la Sección de Gráfica */}
                <div style={{ display: 'flex', 'align-items': 'center', 'justify-content': 'space-between', 'flex-wrap': 'wrap', gap: '10px' }}>
                  <div style={{ display: 'flex', 'align-items': 'center', gap: '8px' }}>
                    <span class="material-symbols-outlined" style={{ color: 'var(--m3-primary)', 'font-size': '24px' }}>
                      show_chart
                    </span>
                    <div>
                      <h3 style={{ 'font-size': '1.0625rem', 'font-weight': 700 }}>
                        Evolución Histórica de Precios
                      </h3>
                      <p style={{ 'font-size': '0.75rem', color: 'var(--m3-on-surface-variant)', 'margin-top': '2px' }}>
                        Ajusta las dimensiones de los ejes y el nivel de zoom para analizar rangos específicos con reajuste automático de escala
                      </p>
                    </div>
                  </div>

                  <div style={{ display: 'flex', 'align-items': 'center', gap: '8px' }}>
                    <button
                      type="button"
                      class={`m3-chip ${showPointValues() ? 'active' : ''}`}
                      onClick={() => setShowPointValues((prev) => !prev)}
                      style={{ height: '32px', 'font-size': '0.75rem', cursor: 'pointer', gap: '6px' }}
                      title="Mostrar u ocultar los valores numéricos sobre cada punto"
                    >
                      <span class="material-symbols-outlined" style={{ 'font-size': '16px' }}>
                        {showPointValues() ? 'label' : 'label_off'}
                      </span>
                      {showPointValues() ? 'Valores en Puntos: Activado' : 'Mostrar Valores en Puntos'}
                    </button>

                    <button
                      type="button"
                      class="m3-btn m3-btn-tonal"
                      style={{ height: '32px', padding: '0 12px', 'font-size': '0.75rem', cursor: 'pointer', gap: '4px' }}
                      onClick={() => {
                        setChartWidth(840);
                        setChartHeight(300);
                        setZoomLevel(1);
                        setPanPosition(0);
                        setShowPointValues(false);
                      }}
                      title="Restablecer tamaño y zoom a valores por defecto"
                    >
                      <span class="material-symbols-outlined" style={{ 'font-size': '16px' }}>
                        restart_alt
                      </span>
                      Restablecer
                    </button>
                  </div>
                </div>

                {/* =====================================================================
                    PANEL DE SLIDERS: DIMENSIONES X/Y + ZOOM + PAN
                    ===================================================================== */}
                <div
                  style={{
                    background: 'var(--m3-surface-container-high)',
                    'border-radius': '16px',
                    border: '1px solid var(--m3-outline-variant)',
                    padding: '16px 20px',
                    display: 'flex',
                    'flex-direction': 'column',
                    gap: '14px',
                  }}
                >
                  <div
                    style={{
                      display: 'grid',
                      'grid-template-columns': 'repeat(auto-fit, minmax(210px, 1fr))',
                      gap: '16px',
                    }}
                  >
                    {/* Slider 1: Ancho (Eje X) */}
                    <div style={{ display: 'flex', 'flex-direction': 'column', gap: '6px' }}>
                      <div style={{ display: 'flex', 'justify-content': 'space-between', 'align-items': 'center' }}>
                        <label style={{ 'font-size': '0.75rem', 'font-weight': 600, color: 'var(--m3-on-surface-variant)', display: 'flex', 'align-items': 'center', gap: '4px' }}>
                          <span class="material-symbols-outlined" style={{ 'font-size': '16px', color: 'var(--m3-primary)' }}>
                            width
                          </span>
                          Ancho (Eje X)
                        </label>
                        <span style={{ 'font-size': '0.75rem', 'font-weight': 700, color: 'var(--m3-primary)' }}>
                          {chartWidth()} px
                        </span>
                      </div>
                      <input
                        type="range"
                        min="500"
                        max="1600"
                        step="20"
                        value={chartWidth()}
                        onInput={(e) => setChartWidth(Number(e.currentTarget.value))}
                        style={{
                          width: '100%',
                          'accent-color': 'var(--m3-primary)',
                          cursor: 'pointer',
                        }}
                      />
                      <div style={{ display: 'flex', 'justify-content': 'space-between', 'font-size': '0.6875rem', color: 'var(--m3-outline)' }}>
                        <span>500px</span>
                        <span>1050px</span>
                        <span>1600px</span>
                      </div>
                    </div>

                    {/* Slider 2: Alto (Eje Y) */}
                    <div style={{ display: 'flex', 'flex-direction': 'column', gap: '6px' }}>
                      <div style={{ display: 'flex', 'justify-content': 'space-between', 'align-items': 'center' }}>
                        <label style={{ 'font-size': '0.75rem', 'font-weight': 600, color: 'var(--m3-on-surface-variant)', display: 'flex', 'align-items': 'center', gap: '4px' }}>
                          <span class="material-symbols-outlined" style={{ 'font-size': '16px', color: 'var(--m3-secondary)' }}>
                            height
                          </span>
                          Alto (Eje Y)
                        </label>
                        <span style={{ 'font-size': '0.75rem', 'font-weight': 700, color: 'var(--m3-secondary)' }}>
                          {chartHeight()} px
                        </span>
                      </div>
                      <input
                        type="range"
                        min="180"
                        max="600"
                        step="10"
                        value={chartHeight()}
                        onInput={(e) => setChartHeight(Number(e.currentTarget.value))}
                        style={{
                          width: '100%',
                          'accent-color': 'var(--m3-secondary)',
                          cursor: 'pointer',
                        }}
                      />
                      <div style={{ display: 'flex', 'justify-content': 'space-between', 'font-size': '0.6875rem', color: 'var(--m3-outline)' }}>
                        <span>180px</span>
                        <span>390px</span>
                        <span>600px</span>
                      </div>
                    </div>

                    {/* Slider 3: Zoom Temporal */}
                    <div style={{ display: 'flex', 'flex-direction': 'column', gap: '6px' }}>
                      <div style={{ display: 'flex', 'justify-content': 'space-between', 'align-items': 'center' }}>
                        <label style={{ 'font-size': '0.75rem', 'font-weight': 600, color: 'var(--m3-on-surface-variant)', display: 'flex', 'align-items': 'center', gap: '4px' }}>
                          <span class="material-symbols-outlined" style={{ 'font-size': '16px', color: 'var(--m3-gold)' }}>
                            zoom_in
                          </span>
                          Nivel de Zoom
                        </label>
                        <span style={{ 'font-size': '0.75rem', 'font-weight': 700, color: 'var(--m3-gold)' }}>
                          {zoomLevel().toFixed(1)}x {zoomLevel() > 1 ? `(${chartData()?.visibleCount || 0} pts)` : '(100%)'}
                        </span>
                      </div>
                      <input
                        type="range"
                        min="1"
                        max="6"
                        step="0.2"
                        value={zoomLevel()}
                        onInput={(e) => setZoomLevel(Number(e.currentTarget.value))}
                        style={{
                          width: '100%',
                          'accent-color': 'var(--m3-gold)',
                          cursor: 'pointer',
                        }}
                      />
                      <div style={{ display: 'flex', 'justify-content': 'space-between', 'font-size': '0.6875rem', color: 'var(--m3-outline)' }}>
                        <span>1.0x</span>
                        <span>3.5x</span>
                        <span>6.0x</span>
                      </div>
                    </div>

                    {/* Slider 4: Desplazamiento Temporal (Pan) */}
                    <Show when={zoomLevel() > 1}>
                      <div style={{ display: 'flex', 'flex-direction': 'column', gap: '6px', 'animation': 'fadeIn 0.2s ease' }}>
                        <div style={{ display: 'flex', 'justify-content': 'space-between', 'align-items': 'center' }}>
                          <label style={{ 'font-size': '0.75rem', 'font-weight': 600, color: 'var(--m3-on-surface-variant)', display: 'flex', 'align-items': 'center', gap: '4px' }}>
                            <span class="material-symbols-outlined" style={{ 'font-size': '16px', color: '#34d399' }}>
                              pan_tool_alt
                            </span>
                            Desplazamiento (Pan)
                          </label>
                          <span style={{ 'font-size': '0.75rem', 'font-weight': 700, color: '#34d399' }}>
                            {panPosition()}%
                          </span>
                        </div>
                        <input
                          type="range"
                          min="0"
                          max="100"
                          step="1"
                          value={panPosition()}
                          onInput={(e) => setPanPosition(Number(e.currentTarget.value))}
                          style={{
                            width: '100%',
                            'accent-color': '#34d399',
                            cursor: 'pointer',
                          }}
                        />
                        <div style={{ display: 'flex', 'justify-content': 'space-between', 'font-size': '0.6875rem', color: 'var(--m3-outline)' }}>
                          <span>← Histórico Antiguo</span>
                          <span>Reciente →</span>
                        </div>
                      </div>
                    </Show>
                  </div>

                  {/* Fila de Botones Rápidos de Zoom */}
                  <div style={{ display: 'flex', 'align-items': 'center', gap: '8px', 'flex-wrap': 'wrap', 'padding-top': '4px', 'border-top': '1px solid var(--m3-outline-variant)' }}>
                    <span style={{ 'font-size': '0.75rem', color: 'var(--m3-on-surface-variant)', 'font-weight': 600 }}>
                      Accesos rápidos de Zoom:
                    </span>
                    <For each={[
                      { label: '1.0x (Completo)', zoom: 1 },
                      { label: '1.5x', zoom: 1.5 },
                      { label: '2.5x (Medio)', zoom: 2.5 },
                      { label: '4.0x', zoom: 4.0 },
                      { label: '6.0x (Máximo Detalle)', zoom: 6.0 },
                    ]}>
                      {(btn) => (
                        <button
                          type="button"
                          class={`m3-chip ${zoomLevel() === btn.zoom ? 'active' : ''}`}
                          onClick={() => {
                            setZoomLevel(btn.zoom);
                            if (btn.zoom === 1) setPanPosition(0);
                          }}
                          style={{ height: '28px', 'font-size': '0.75rem', cursor: 'pointer' }}
                        >
                          {btn.label}
                        </button>
                      )}
                    </For>
                  </div>
                </div>

                {/* Banner de Estado de Zoom y Reajuste Dinámico de Escala */}
                <Show when={chartData()}>
                  {(cd) => (
                    <div
                      style={{
                        background: 'var(--m3-surface-container-low)',
                        padding: '10px 14px',
                        'border-radius': '10px',
                        border: '1px solid var(--m3-outline-variant)',
                        display: 'flex',
                        'align-items': 'center',
                        'justify-content': 'space-between',
                        'flex-wrap': 'wrap',
                        gap: '8px',
                        'font-size': '0.75rem',
                      }}
                    >
                      <div style={{ display: 'flex', 'align-items': 'center', gap: '6px' }}>
                        <span class="material-symbols-outlined" style={{ 'font-size': '18px', color: 'var(--m3-primary)' }}>
                          tune
                        </span>
                        <span style={{ color: 'var(--m3-on-surface-variant)' }}>
                          Mostrando <strong>{cd().visibleCount}</strong> de <strong>{cd().totalPoints}</strong> puntos
                          {zoomLevel() > 1 ? ` (Ventana del ${cd().firstDate} al ${cd().lastDate})` : ' (Histórico Completo)'}
                        </span>
                      </div>

                      <div style={{ display: 'flex', 'align-items': 'center', gap: '12px' }}>
                        <span style={{ color: 'var(--m3-on-surface-variant)' }}>
                          Rango reajustado en ventana:
                        </span>
                        <span style={{ 'font-weight': 700, color: '#34d399' }}>
                          Mín: {cd().curr}{cd().rawMin.toFixed(2)}
                        </span>
                        <span style={{ color: 'var(--m3-outline)' }}>—</span>
                        <span style={{ 'font-weight': 700, color: 'var(--m3-gold)' }}>
                          Máx: {cd().curr}{cd().rawMax.toFixed(2)}
                        </span>
                      </div>
                    </div>
                  )}
                </Show>

                {/* Renderizado de Gráfica SVG */}
                <Show
                  when={chartData()}
                  fallback={
                    <div style={{ padding: '60px', 'text-align': 'center', color: 'var(--m3-outline)' }}>
                      <span class="material-symbols-outlined" style={{ 'font-size': '42px', 'margin-bottom': '8px' }}>
                        query_stats
                      </span>
                      <p style={{ 'font-size': '0.875rem' }}>
                        No hay suficientes datos históricos con los filtros seleccionados. Intenta cambiar de tienda o ampliar el rango de días.
                      </p>
                    </div>
                  }
                >
                  {(cd) => (
                    <div
                      style={{
                        width: '100%',
                        'overflow-x': 'auto',
                        position: 'relative',
                        padding: '8px',
                        'border-radius': '14px',
                        background: 'var(--m3-surface-container-lowest)',
                        border: '1px solid var(--m3-outline-variant)',
                      }}
                    >
                      <svg
                        viewBox={`0 0 ${cd().width} ${cd().height}`}
                        style={{
                          width: `${cd().width}px`,
                          'min-width': '100%',
                          height: `${cd().height}px`,
                          display: 'block',
                        }}
                      >
                        <defs>
                          <linearGradient id="priceGradient" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stop-color="var(--m3-primary)" stop-opacity="0.5" />
                            <stop offset="100%" stop-color="var(--m3-primary)" stop-opacity="0.02" />
                          </linearGradient>
                        </defs>

                        {/* Líneas Guía Horizontales Recalculadas Dinámicamente */}
                        <For each={cd().yLevels}>
                          {(lvl, idx) => (
                            <g>
                              <line
                                x1={cd().padding.left}
                                y1={lvl.y}
                                x2={cd().width - cd().padding.right}
                                y2={lvl.y}
                                stroke="var(--m3-outline-variant)"
                                stroke-dasharray={idx() === 0 || idx() === 4 ? 'none' : '3 4'}
                                opacity={idx() === 0 || idx() === 4 ? 0.9 : 0.45}
                              />
                              <text
                                x={cd().padding.left - 10}
                                y={lvl.y + 4}
                                text-anchor="end"
                                fill="var(--m3-outline)"
                                font-size="11"
                                font-family="var(--font-display)"
                                font-weight="600"
                              >
                                {cd().curr}{lvl.price.toFixed(2)}
                              </text>
                            </g>
                          )}
                        </For>

                        {/* Área sombreada bajo la curva */}
                        <path d={cd().areaD} fill="url(#priceGradient)" />

                        {/* Línea principal del precio */}
                        <path
                          d={cd().pathD}
                          fill="none"
                          stroke="var(--m3-primary)"
                          stroke-width="3"
                          stroke-linecap="round"
                          stroke-linejoin="round"
                        />

                        {/* Puntos interactivos con soporte de etiquetas de valor */}
                        <For each={cd().points}>
                          {(pt) => {
                            const isHovered = () => hoveredPoint()?.item === pt.item;
                            const showLabel = () => showPointValues() || zoomLevel() >= 3.0;

                            return (
                              <g>
                                {/* Círculo del Punto de Datos */}
                                <circle
                                  cx={pt.x}
                                  cy={pt.y}
                                  r={isHovered() ? '7' : showLabel() ? '4.5' : '3.5'}
                                  fill={isHovered() ? '#ffffff' : 'var(--m3-primary)'}
                                  stroke="var(--m3-surface)"
                                  stroke-width="2"
                                  style={{ cursor: 'pointer', transition: 'all 0.15s ease' }}
                                  onMouseEnter={() => setHoveredPoint(pt)}
                                  onMouseLeave={() => setHoveredPoint(null)}
                                />

                                {/* Etiqueta de Valor Flotante sobre el Punto */}
                                <Show when={showLabel()}>
                                  <g transform={`translate(${pt.x}, ${pt.y - 12})`} style={{ 'pointer-events': 'none' }}>
                                    <rect
                                      x="-22"
                                      y="-13"
                                      width="44"
                                      height="16"
                                      rx="4"
                                      fill="var(--m3-surface-container-highest)"
                                      stroke="var(--m3-outline-variant)"
                                      stroke-width="0.8"
                                      opacity="0.95"
                                    />
                                    <text
                                      x="0"
                                      y="-1"
                                      text-anchor="middle"
                                      fill="var(--m3-on-surface)"
                                      font-size="9"
                                      font-weight="700"
                                      font-family="var(--font-display)"
                                    >
                                      {cd().curr}{pt.item.price.toFixed(2)}
                                    </text>
                                  </g>
                                </Show>
                              </g>
                            );
                          }}
                        </For>

                        {/* Fechas en el eje X */}
                        <text
                          x={cd().padding.left}
                          y={cd().height - 12}
                          text-anchor="start"
                          fill="var(--m3-outline)"
                          font-size="11"
                          font-family="var(--font-display)"
                          font-weight="500"
                        >
                          {cd().firstDate}
                        </text>
                        <text
                          x={cd().padding.left + cd().innerWidth / 2}
                          y={cd().height - 12}
                          text-anchor="middle"
                          fill="var(--m3-outline)"
                          font-size="11"
                          font-family="var(--font-display)"
                          font-weight="500"
                        >
                          {cd().midDate}
                        </text>
                        <text
                          x={cd().width - cd().padding.right}
                          y={cd().height - 12}
                          text-anchor="end"
                          fill="var(--m3-outline)"
                          font-size="11"
                          font-family="var(--font-display)"
                          font-weight="500"
                        >
                          {cd().lastDate}
                        </text>
                      </svg>

                      {/* Tooltip flotante interactivo de alta precisión */}
                      <Show when={hoveredPoint()}>
                        {(hp) => (
                          <div
                            style={{
                              position: 'absolute',
                              left: `${hp().x}px`,
                              top: `${hp().y}px`,
                              transform: 'translate(-50%, -120%)',
                              background: 'var(--m3-surface-container-highest)',
                              border: '1px solid var(--m3-outline-variant)',
                              'box-shadow': 'var(--shadow-4)',
                              'border-radius': '10px',
                              padding: '10px 14px',
                              'pointer-events': 'none',
                              'z-index': 30,
                              'white-space': 'nowrap',
                              'font-size': '0.8125rem',
                              'backdrop-filter': 'blur(10px)',
                            }}
                          >
                            <div style={{ 'font-weight': 800, 'font-size': '1rem', color: '#34d399', display: 'flex', 'align-items': 'center', gap: '6px' }}>
                              <span>{cd().curr}{hp().item.price.toFixed(2)}</span>
                              <span style={{ 'font-size': '0.6875rem', color: 'var(--m3-outline)', 'font-weight': 500 }}>
                                {hp().item.currency}
                              </span>
                            </div>
                            <div style={{ color: 'var(--m3-on-surface-variant)', 'font-size': '0.75rem', 'margin-top': '4px' }}>
                              📅 {hp().item.price_date} · 🏪 {hp().item.provider.toUpperCase()}
                            </div>
                            <div style={{ color: 'var(--m3-outline)', 'font-size': '0.6875rem' }}>
                              Acabado: {hp().item.finish} · Tipo: {hp().item.price_type}
                            </div>
                            <Show when={hp().item.pct_change !== undefined && hp().item.pct_change !== null}>
                              <div
                                style={{
                                  color: hp().item.pct_change! > 0 ? '#34d399' : hp().item.pct_change! < 0 ? '#f87171' : 'var(--m3-on-surface)',
                                  'font-weight': 700,
                                  'margin-top': '4px',
                                  'font-size': '0.75rem',
                                  display: 'flex',
                                  'align-items': 'center',
                                  gap: '4px',
                                }}
                              >
                                <span class="material-symbols-outlined" style={{ 'font-size': '14px' }}>
                                  {hp().item.pct_change! > 0 ? 'trending_up' : hp().item.pct_change! < 0 ? 'trending_down' : 'trending_flat'}
                                </span>
                                {hp().item.pct_change! > 0 ? `+${hp().item.pct_change}%` : `${hp().item.pct_change}%`}
                                {hp().item.price_diff !== undefined && hp().item.price_diff !== null && (
                                  <span style={{ 'font-weight': 500, color: 'var(--m3-outline)' }}>
                                    ({hp().item.price_diff > 0 ? `+${hp().item.price_diff.toFixed(2)}` : hp().item.price_diff.toFixed(2)})
                                  </span>
                                )}
                              </div>
                            </Show>
                          </div>
                        )}
                      </Show>
                    </div>
                  )}
                </Show>
              </div>

              {/* =====================================================================
                  TABLA DE REGISTROS DÍA A DÍA Y VARIACIONES
                  ===================================================================== */}
              <div
                style={{
                  background: 'var(--m3-surface-container)',
                  'border-radius': '20px',
                  border: '1px solid var(--m3-outline-variant)',
                  padding: '20px',
                  display: 'flex',
                  'flex-direction': 'column',
                  gap: '16px',
                }}
              >
                <div style={{ display: 'flex', 'align-items': 'center', 'justify-content': 'space-between', 'flex-wrap': 'wrap', gap: '10px' }}>
                  <div style={{ display: 'flex', 'align-items': 'center', gap: '8px' }}>
                    <span class="material-symbols-outlined" style={{ color: 'var(--m3-primary)', 'font-size': '22px' }}>
                      history
                    </span>
                    <h3 style={{ 'font-size': '1.0625rem', 'font-weight': 700 }}>
                      Historial Detallado de Cotizaciones y Cambios
                    </h3>
                  </div>

                  {/* Ordenamiento de la tabla */}
                  <div style={{ display: 'flex', 'align-items': 'center', gap: '8px' }}>
                    <span style={{ 'font-size': '0.75rem', color: 'var(--m3-on-surface-variant)' }}>Ordenar por:</span>
                    <select
                      value={tableSort()}
                      onChange={(e) => setTableSort(e.currentTarget.value as any)}
                      style={{
                        height: '32px',
                        background: 'var(--m3-surface-container-high)',
                        border: '1px solid var(--m3-outline-variant)',
                        'border-radius': '6px',
                        color: 'var(--m3-on-surface)',
                        padding: '0 8px',
                        'font-size': '0.75rem',
                        outline: 'none',
                        cursor: 'pointer',
                      }}
                    >
                      <option value="date_desc">Fecha (Más reciente primero)</option>
                      <option value="date_asc">Fecha (Más antigua primero)</option>
                      <option value="price_desc">Precio (Mayor a menor)</option>
                      <option value="price_asc">Precio (Menor a mayor)</option>
                      <option value="diff_desc">Mayor Variación Absoluta</option>
                    </select>
                  </div>
                </div>

                {/* Tabla Renderizada */}
                <div
                  style={{
                    'border-radius': '12px',
                    overflow: 'hidden',
                    border: '1px solid var(--m3-outline-variant)',
                    background: 'var(--m3-surface-container-high)',
                  }}
                >
                  <div style={{ 'overflow-x': 'auto', 'max-height': '380px' }}>
                    <table style={{ width: '100%', 'border-collapse': 'collapse', 'font-size': '0.8125rem' }}>
                      <thead style={{ position: 'sticky', top: 0, background: 'var(--m3-surface-container-highest)', 'z-index': 10 }}>
                        <tr style={{ 'text-align': 'left' }}>
                          <th style={{ padding: '10px 14px' }}>Fecha</th>
                          <th style={{ padding: '10px 14px' }}>Tienda / Proveedor</th>
                          <th style={{ padding: '10px 14px' }}>Acabado</th>
                          <th style={{ padding: '10px 14px' }}>Canal</th>
                          <th style={{ padding: '10px 14px' }}>Precio</th>
                          <th style={{ padding: '10px 14px' }}>Precio Anterior</th>
                          <th style={{ padding: '10px 14px' }}>Diferencia</th>
                          <th style={{ padding: '10px 14px' }}>% Cambio</th>
                        </tr>
                      </thead>
                      <tbody>
                        <Show
                          when={sortedHistoryTable().length > 0}
                          fallback={
                            <tr>
                              <td colspan="8" style={{ padding: '32px', 'text-align': 'center', color: 'var(--m3-outline)' }}>
                                No se encontraron cotizaciones para los filtros seleccionados.
                              </td>
                            </tr>
                          }
                        >
                          <For each={sortedHistoryTable()}>
                            {(item) => {
                              const isPositive = (item.price_diff ?? 0) > 0;
                              const isNegative = (item.price_diff ?? 0) < 0;
                              const diffColor = isPositive ? '#34d399' : isNegative ? '#f87171' : 'var(--m3-outline)';

                              return (
                                <tr style={{ 'border-top': '1px solid var(--m3-outline-variant)' }}>
                                  <td style={{ padding: '10px 14px', 'font-weight': 600 }}>
                                    {item.price_date}
                                  </td>
                                  <td style={{ padding: '10px 14px', 'text-transform': 'capitalize' }}>
                                    <span style={{ 'font-weight': 600 }}>{item.provider}</span>
                                  </td>
                                  <td style={{ padding: '10px 14px' }}>
                                    {item.finish === 'foil' ? (
                                      <span
                                        style={{
                                          background: 'linear-gradient(135deg, #3b82f6, #8b5cf6)',
                                          color: '#ffffff',
                                          padding: '2px 6px',
                                          'border-radius': '4px',
                                          'font-size': '0.6875rem',
                                          'font-weight': 700,
                                        }}
                                      >
                                        FOIL
                                      </span>
                                    ) : (
                                      <span style={{ color: 'var(--m3-on-surface-variant)', 'text-transform': 'capitalize' }}>
                                        {item.finish}
                                      </span>
                                    )}
                                  </td>
                                  <td style={{ padding: '10px 14px', 'text-transform': 'capitalize', color: 'var(--m3-on-surface-variant)' }}>
                                    {item.price_type}
                                  </td>
                                  <td style={{ padding: '10px 14px', 'font-weight': 700, color: '#34d399' }}>
                                    {item.currency === 'EUR' ? '€' : '$'}{item.price.toFixed(2)}
                                  </td>
                                  <td style={{ padding: '10px 14px', color: 'var(--m3-on-surface-variant)' }}>
                                    {item.previous_price !== undefined && item.previous_price !== null
                                      ? `${item.currency === 'EUR' ? '€' : '$'}${item.previous_price.toFixed(2)}`
                                      : '—'}
                                  </td>
                                  <td style={{ padding: '10px 14px', 'font-weight': 700, color: diffColor }}>
                                    {item.price_diff !== undefined && item.price_diff !== null
                                      ? (item.price_diff > 0 ? `+${item.price_diff.toFixed(2)}` : `${item.price_diff.toFixed(2)}`)
                                      : '—'}
                                  </td>
                                  <td style={{ padding: '10px 14px' }}>
                                    {item.pct_change !== undefined && item.pct_change !== null ? (
                                      <span
                                        style={{
                                          background: isPositive
                                            ? 'rgba(52, 211, 153, 0.15)'
                                            : isNegative
                                            ? 'rgba(248, 113, 113, 0.15)'
                                            : 'transparent',
                                          color: diffColor,
                                          padding: '2px 6px',
                                          'border-radius': '4px',
                                          'font-weight': 700,
                                          'font-size': '0.75rem',
                                        }}
                                      >
                                        {item.pct_change > 0 ? `+${item.pct_change.toFixed(1)}%` : `${item.pct_change.toFixed(1)}%`}
                                      </span>
                                    ) : (
                                      <span style={{ color: 'var(--m3-outline)' }}>—</span>
                                    )}
                                  </td>
                                </tr>
                              );
                            }}
                          </For>
                        </Show>
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            </section>
          </div>
        </Show>
      </main>
    </div>
  );
};
