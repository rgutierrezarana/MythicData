import { Component, createSignal, createResource, For, Show, onMount, onCleanup, createEffect, createMemo } from 'solid-js';
import {
  fetchIngestionConfig,
  triggerIngestion,
  fetchIngestionStatus,
  fetchIngestionLogs,
  fetchIngestionHistory,
  fetchJaegerTraces,
} from '../services/api';
import type {
  IngestionTriggerRequest,
  IngestionStatusResponse,
  IngestionHistoryItem,
  JaegerTraceSummary,
} from '../types/ingestion';

interface IngestionScreenProps {
  onBackToCatalog: () => void;
}

export const IngestionScreen: Component<IngestionScreenProps> = (props) => {
  // Configuración y metadatos
  const [configData, { refetch: refetchConfig }] = createResource(() => fetchIngestionConfig());
  const [historyData, { refetch: refetchHistory }] = createResource(() => fetchIngestionHistory(12));
  const [tracesData, { refetch: refetchTraces }] = createResource(() => fetchJaegerTraces(6));

  // Formulario de Disparo
  const [selectedDag, setSelectedDag] = createSignal<'selected_set_ingestion' | 'all_sets_ingestion' | 'price_prediction_pipeline'>('selected_set_ingestion');
  const [selectedSets, setSelectedSets] = createSignal<string[]>(['MH3', 'FDN', 'BLB']);
  const [loadHistory, setLoadHistory] = createSignal<boolean>(false);
  const [setFilterText, setSetFilterText] = createSignal<string>('');
  const [isSubmitting, setIsSubmitting] = createSignal<boolean>(false);
  const [submitError, setSubmitError] = createSignal<string | null>(null);

  // Monitor en Tiempo Real de la Ejecución Activa
  const [activeDagId, setActiveDagId] = createSignal<string | null>(null);
  const [activeDagRunId, setActiveDagRunId] = createSignal<string | null>(null);
  const [statusData, setStatusData] = createSignal<IngestionStatusResponse | null>(null);
  const [logsText, setLogsText] = createSignal<string>('');
  const [detectedTraceId, setDetectedTraceId] = createSignal<string | null>(null);
  const [autoScrollLogs, setAutoScrollLogs] = createSignal<boolean>(true);

  let logContainerRef: HTMLDivElement | undefined;
  let pollingInterval: any = null;

  // Cargar automáticamente la última ejecución si hay historial
  createEffect(() => {
    const runs = historyData()?.runs;
    if (runs && runs.length > 0 && !activeDagRunId()) {
      const latest = runs[0];
      setActiveDagId(latest.dag_id);
      setActiveDagRunId(latest.dag_run_id);
      loadRunDetails(latest.dag_id, latest.dag_run_id);
    }
  });

  // Polling dinámico de estado y logs
  const pollActiveRun = async () => {
    const dagId = activeDagId();
    const runId = activeDagRunId();
    if (!dagId || !runId) return;

    try {
      const [st, lg] = await Promise.all([
        fetchIngestionStatus(dagId, runId),
        fetchIngestionLogs(dagId, runId),
      ]);

      setStatusData(st);
      if (lg.log) {
        setLogsText(lg.log);
        if (lg.jaeger_trace_id) {
          setDetectedTraceId(lg.jaeger_trace_id);
        }
      }

      if (autoScrollLogs() && logContainerRef) {
        logContainerRef.scrollTop = logContainerRef.scrollHeight;
      }

      // Si terminó con éxito o falló, refrescar historial y trazas
      if (st.state === 'success' || st.state === 'failed') {
        refetchHistory();
        refetchTraces();
        // Disminuir frecuencia o detener si ya no está corriendo
        if (pollingInterval && st.state === 'success') {
          clearInterval(pollingInterval);
          pollingInterval = setInterval(pollActiveRun, 8000);
        }
      }
    } catch (err) {
      console.warn('Error en polling de ingesta:', err);
    }
  };

  const startPolling = () => {
    if (pollingInterval) clearInterval(pollingInterval);
    pollActiveRun();
    pollingInterval = setInterval(pollActiveRun, 2500);
  };

  onMount(() => {
    startPolling();
  });

  onCleanup(() => {
    if (pollingInterval) clearInterval(pollingInterval);
  });

  // Cambiar ejecución observada
  const loadRunDetails = async (dagId: string, runId: string) => {
    setActiveDagId(dagId);
    setActiveDagRunId(runId);
    startPolling();
  };

  // Disparar Ingesta
  const handleTrigger = async () => {
    setIsSubmitting(true);
    setSubmitError(null);

    try {
      const req: IngestionTriggerRequest = {
        dag_id: selectedDag(),
        set_codes: selectedSets(),
        load_history: loadHistory(),
      };

      const res = await triggerIngestion(req);
      setActiveDagId(res.dag_id);
      setActiveDagRunId(res.dag_run_id);
      setLogsText('Iniciando pipeline en Apache Airflow...');
      setStatusData({
        dag_id: res.dag_id,
        dag_run_id: res.dag_run_id,
        state: 'queued',
        progress_percent: 5,
        current_step: 'Pipeline encolado en Apache Airflow. Esperando ejecución de Spark...',
        conf: res.conf,
        tasks: [],
        airflow_url: res.airflow_url,
        jaeger_url: configData()?.jaeger_ui_url || 'http://localhost:16686',
      });

      startPolling();
      refetchHistory();
    } catch (err: any) {
      setSubmitError(err.message || 'Error al iniciar la ingesta en Airflow.');
    } finally {
      setIsSubmitting(false);
    }
  };

  // Manejo de Selección de Sets
  const toggleSet = (code: string) => {
    const upper = code.toUpperCase();
    if (selectedSets().includes(upper)) {
      setSelectedSets(selectedSets().filter((s) => s !== upper));
    } else {
      setSelectedSets([...selectedSets(), upper]);
    }
  };

  const selectTopSets = () => {
    setSelectedSets(['MH3', 'FDN', 'BLB', 'OTJ', 'MKM']);
  };

  const clearSets = () => {
    setSelectedSets([]);
  };

  // Helper para obtener el nombre limpio del set (remueve prefijos tipo "MH3 - ")
  const getCleanSetName = (name?: string, code?: string) => {
    if (!name) return code || '';
    if (!code) return name;
    const regex = new RegExp(`^${code}\\s*-\\s*`, 'i');
    const clean = name.replace(regex, '').trim();
    return clean || name;
  };

  // Diccionario para acceso rápido al nombre limpio de los sets
  const setNamesMap = createMemo(() => {
    const map = new Map<string, string>();
    for (const item of configData()?.available_sets || []) {
      map.set(item.code.toUpperCase(), getCleanSetName(item.name, item.code));
    }
    return map;
  });

  // Filtro de sets disponibles (busca tanto por código como por nombre)
  const filteredSets = () => {
    const list = configData()?.available_sets || [];
    const query = setFilterText().trim().toLowerCase();
    if (!query) return list.slice(0, 80);
    return list
      .filter((s) => {
        const cleanName = getCleanSetName(s.name, s.code).toLowerCase();
        return s.code.toLowerCase().includes(query) || cleanName.includes(query) || s.name.toLowerCase().includes(query);
      })
      .slice(0, 150);
  };

  const getStatusColor = (state?: string) => {
    switch (state?.toLowerCase()) {
      case 'success':
        return '#10b981'; // Verde
      case 'running':
        return '#3b82f6'; // Azul
      case 'failed':
        return '#ef4444'; // Rojo
      case 'queued':
        return '#f59e0b'; // Amarillo
      default:
        return 'var(--m3-outline)';
    }
  };

  const getStatusLabel = (state?: string) => {
    switch (state?.toLowerCase()) {
      case 'success':
        return 'Completado con Éxito';
      case 'running':
        return 'Ejecutando en Apache Spark...';
      case 'failed':
        return 'Fallo en la Ejecución';
      case 'queued':
        return 'En Cola de Airflow';
      default:
        return state || 'Sin Estado';
    }
  };

  return (
    <div style={{ minHeight: '100vh', background: 'var(--m3-surface)', color: 'var(--m3-on-surface)', display: 'flex', 'flex-direction': 'column' }}>
      {/* 1. Header con Navegación y Badges de Conexión */}
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
          'z-index': 30,
          'backdrop-filter': 'blur(12px)',
        }}
      >
        <div style={{ display: 'flex', 'align-items': 'center', gap: '16px' }}>
          <button
            type="button"
            class="m3-btn m3-btn-tonal"
            onClick={props.onBackToCatalog}
            style={{ height: '38px', padding: '0 16px', gap: '6px', cursor: 'pointer' }}
          >
            <span class="material-symbols-outlined" style={{ 'font-size': '20px' }}>
              arrow_back
            </span>
            <span>Volver al Catálogo</span>
          </button>

          <div style={{ display: 'flex', 'align-items': 'center', gap: '8px' }}>
            <span class="material-symbols-outlined" style={{ color: 'var(--m3-primary)', 'font-size': '24px' }}>
              sync_saved_locally
            </span>
            <h2 style={{ 'font-size': '1.125rem', 'font-weight': 700, margin: 0 }}>
              Centro de Ingesta & Pipelines ETL
            </h2>
          </div>
        </div>

        {/* Badges de Conexión Airflow & Jaeger */}
        <div style={{ display: 'flex', 'align-items': 'center', gap: '10px' }}>
          {/* Airflow */}
          <a
            href={configData()?.airflow_web_url || 'http://localhost:8080'}
            target="_blank"
            rel="noreferrer"
            style={{
              display: 'flex',
              'align-items': 'center',
              gap: '6px',
              padding: '6px 12px',
              'border-radius': '8px',
              background: configData()?.airflow_connected ? 'rgba(16, 185, 129, 0.12)' : 'rgba(239, 68, 68, 0.12)',
              border: `1px solid ${configData()?.airflow_connected ? 'rgba(16, 185, 129, 0.3)' : 'rgba(239, 68, 68, 0.3)'}`,
              color: configData()?.airflow_connected ? '#34d399' : '#f87171',
              'text-decoration': 'none',
              'font-size': '0.75rem',
              'font-weight': 600,
            }}
            title="Abrir Apache Airflow Webserver (localhost:8080)"
          >
            <span
              style={{
                width: '8px',
                height: '8px',
                'border-radius': '50%',
                background: configData()?.airflow_connected ? '#10b981' : '#ef4444',
              }}
            />
            <span>Airflow Webserver</span>
            <span class="material-symbols-outlined" style={{ 'font-size': '14px' }}>
              open_in_new
            </span>
          </a>

          {/* Jaeger */}
          <a
            href={configData()?.jaeger_ui_url || 'http://localhost:16686'}
            target="_blank"
            rel="noreferrer"
            style={{
              display: 'flex',
              'align-items': 'center',
              gap: '6px',
              padding: '6px 12px',
              'border-radius': '8px',
              background: configData()?.jaeger_connected ? 'rgba(139, 92, 246, 0.12)' : 'rgba(239, 68, 68, 0.12)',
              border: `1px solid ${configData()?.jaeger_connected ? 'rgba(139, 92, 246, 0.3)' : 'rgba(239, 68, 68, 0.3)'}`,
              color: configData()?.jaeger_connected ? '#a78bfa' : '#f87171',
              'text-decoration': 'none',
              'font-size': '0.75rem',
              'font-weight': 600,
            }}
            title="Abrir Jaeger UI Observability (localhost:16686)"
          >
            <span
              style={{
                width: '8px',
                height: '8px',
                'border-radius': '50%',
                background: configData()?.jaeger_connected ? '#8b5cf6' : '#ef4444',
              }}
            />
            <span>Jaeger Tracing</span>
            <span class="material-symbols-outlined" style={{ 'font-size': '14px' }}>
              open_in_new
            </span>
          </a>
        </div>
      </header>

      {/* 2. Cuerpo Principal */}
      <main style={{ flex: 1, padding: '24px', 'max-width': '1440px', margin: '0 auto', width: '100%', display: 'flex', 'flex-direction': 'column', gap: '24px' }}>
        {/* Banner Informativo */}
        <div
          style={{
            background: 'linear-gradient(135deg, rgba(79, 55, 139, 0.25), rgba(33, 31, 38, 0.6))',
            border: '1px solid var(--m3-primary-container)',
            'border-radius': '16px',
            padding: '18px 24px',
            display: 'flex',
            'align-items': 'center',
            'justify-content': 'space-between',
            gap: '16px',
          }}
        >
          <div>
            <h3 style={{ 'font-size': '1.05rem', 'font-weight': 700, 'margin-bottom': '4px', color: 'var(--m3-on-surface)' }}>
              Pipelines de Ingesta y Procesamiento Distribuido Big Data
            </h3>
            <p style={{ 'font-size': '0.8125rem', color: 'var(--m3-on-surface-variant)', 'line-height': 1.4 }}>
              Dispara tareas de Apache Airflow bajo demanda. PySpark descarga las cartas de MTGJSON, cruza cotizaciones multitienda (TCGplayer, Cardmarket, CardKingdom), genera 1 Parquet por set en el Data Lake e inserta los datos en PostgreSQL con trazabilidad distribuida en Jaeger.
            </p>
          </div>
        </div>

        {/* Grid de 2 Columnas: Lanzador (Izq) + Monitor en Vivo (Der) */}
        <div style={{ display: 'grid', 'grid-template-columns': 'repeat(auto-fit, minmax(460px, 1fr))', gap: '24px' }}>
          {/* ================= COLUMNA IZQUIERDA: FORMULARIO DE DISPARO ================= */}
          <div
            style={{
              background: 'var(--m3-surface-container)',
              'border-radius': '16px',
              border: '1px solid var(--m3-outline-variant)',
              padding: '20px',
              display: 'flex',
              'flex-direction': 'column',
              gap: '18px',
            }}
          >
            <div style={{ display: 'flex', 'align-items': 'center', 'justify-content': 'space-between' }}>
              <h3 style={{ 'font-size': '1.05rem', 'font-weight': 700, display: 'flex', 'align-items': 'center', gap: '8px' }}>
                <span class="material-symbols-outlined" style={{ color: 'var(--m3-primary)' }}>
                  rocket_launch
                </span>
                Configurar y Disparar Ingesta
              </h3>
            </div>

            {/* Selector de DAG */}
            <div>
              <label style={{ 'font-size': '0.75rem', 'font-weight': 700, color: 'var(--m3-on-surface-variant)', 'text-transform': 'uppercase', display: 'block', 'margin-bottom': '8px' }}>
                Seleccionar Pipeline (DAG Airflow)
              </label>
              <div style={{ display: 'grid', 'grid-template-columns': 'repeat(auto-fit, minmax(140px, 1fr))', gap: '8px' }}>
                <button
                  type="button"
                  onClick={() => setSelectedDag('selected_set_ingestion')}
                  style={{
                    padding: '12px 10px',
                    'border-radius': '12px',
                    border: selectedDag() === 'selected_set_ingestion' ? '2px solid var(--m3-primary)' : '1px solid var(--m3-outline-variant)',
                    background: selectedDag() === 'selected_set_ingestion' ? 'rgba(208, 188, 255, 0.12)' : 'var(--m3-surface-container-high)',
                    color: 'var(--m3-on-surface)',
                    'text-align': 'left',
                    cursor: 'pointer',
                    transition: 'all 0.2s',
                  }}
                >
                  <div style={{ 'font-weight': 700, 'font-size': '0.8125rem' }}>Cartas y Precios</div>
                  <div style={{ 'font-size': '0.6875rem', color: 'var(--m3-on-surface-variant)', 'margin-top': '4px' }}>
                    selected_set_ingestion
                  </div>
                </button>

                <button
                  type="button"
                  onClick={() => setSelectedDag('all_sets_ingestion')}
                  style={{
                    padding: '12px 10px',
                    'border-radius': '12px',
                    border: selectedDag() === 'all_sets_ingestion' ? '2px solid var(--m3-primary)' : '1px solid var(--m3-outline-variant)',
                    background: selectedDag() === 'all_sets_ingestion' ? 'rgba(208, 188, 255, 0.12)' : 'var(--m3-surface-container-high)',
                    color: 'var(--m3-on-surface)',
                    'text-align': 'left',
                    cursor: 'pointer',
                    transition: 'all 0.2s',
                  }}
                >
                  <div style={{ 'font-weight': 700, 'font-size': '0.8125rem' }}>Catálogo Sets</div>
                  <div style={{ 'font-size': '0.6875rem', color: 'var(--m3-on-surface-variant)', 'margin-top': '4px' }}>
                    all_sets_ingestion
                  </div>
                </button>

                <button
                  type="button"
                  onClick={() => setSelectedDag('price_prediction_pipeline')}
                  style={{
                    padding: '12px 10px',
                    'border-radius': '12px',
                    border: selectedDag() === 'price_prediction_pipeline' ? '2px solid #a78bfa' : '1px solid var(--m3-outline-variant)',
                    background: selectedDag() === 'price_prediction_pipeline' ? 'rgba(167, 139, 250, 0.16)' : 'var(--m3-surface-container-high)',
                    color: 'var(--m3-on-surface)',
                    'text-align': 'left',
                    cursor: 'pointer',
                    transition: 'all 0.2s',
                  }}
                >
                  <div style={{ 'font-weight': 700, 'font-size': '0.8125rem', color: selectedDag() === 'price_prediction_pipeline' ? '#c4b5fd' : 'inherit' }}>
                    Predicción ML
                  </div>
                  <div style={{ 'font-size': '0.6875rem', color: 'var(--m3-on-surface-variant)', 'margin-top': '4px' }}>
                    GBTRegressor (Spark)
                  </div>
                </button>
              </div>
            </div>

            {/* Opciones Específicas de 'selected_set_ingestion' */}
            <Show when={selectedDag() === 'selected_set_ingestion'}>
              {/* Selector de Sets con Búsqueda y Chips */}
              <div>
                <div style={{ display: 'flex', 'align-items': 'center', 'justify-content': 'space-between', 'margin-bottom': '6px' }}>
                  <label style={{ 'font-size': '0.75rem', 'font-weight': 700, color: 'var(--m3-on-surface-variant)', 'text-transform': 'uppercase' }}>
                    Sets Seleccionados ({selectedSets().length})
                  </label>
                  <div style={{ display: 'flex', gap: '6px' }}>
                    <button
                      type="button"
                      onClick={selectTopSets}
                      style={{ background: 'transparent', border: 'none', color: 'var(--m3-primary)', 'font-size': '0.75rem', cursor: 'pointer', 'font-weight': 600 }}
                    >
                      Populares
                    </button>
                    <span style={{ color: 'var(--m3-outline)' }}>·</span>
                    <button
                      type="button"
                      onClick={clearSets}
                      style={{ background: 'transparent', border: 'none', color: 'var(--m3-outline)', 'font-size': '0.75rem', cursor: 'pointer' }}
                    >
                      Limpiar
                    </button>
                  </div>
                </div>

                {/* Chips de Sets Seleccionados */}
                <div style={{ display: 'flex', 'flex-wrap': 'wrap', gap: '6px', 'min-height': '32px', 'margin-bottom': '12px' }}>
                  <For each={selectedSets()}>
                    {(code) => {
                      const getSetName = () => setNamesMap().get(code.toUpperCase());
                      return (
                        <span
                          style={{
                            background: 'var(--m3-primary-container)',
                            color: 'var(--m3-on-primary-container)',
                            padding: '4px 10px',
                            'border-radius': '8px',
                            'font-size': '0.75rem',
                            'font-weight': 600,
                            display: 'inline-flex',
                            'align-items': 'center',
                            gap: '6px',
                            border: '1px solid var(--m3-primary)',
                            'box-shadow': '0 1px 3px rgba(0,0,0,0.2)',
                          }}
                          title={getSetName() ? `${code}: ${getSetName()}` : code}
                        >
                          <span style={{ 'font-family': 'monospace', 'font-weight': 800 }}>{code}</span>
                          <Show when={getSetName()}>
                            <span style={{ opacity: 0.5 }}>·</span>
                            <span style={{ 'max-width': '160px', overflow: 'hidden', 'text-overflow': 'ellipsis', 'white-space': 'nowrap', 'font-weight': 500 }}>
                              {getSetName()}
                            </span>
                          </Show>
                          <button
                            type="button"
                            onClick={() => toggleSet(code)}
                            style={{
                              background: 'transparent',
                              border: 'none',
                              color: 'inherit',
                              cursor: 'pointer',
                              padding: 0,
                              display: 'flex',
                              opacity: 0.8,
                              transition: 'opacity 0.2s',
                              'margin-left': '2px',
                            }}
                            title={`Quitar ${code}`}
                          >
                            <span class="material-symbols-outlined" style={{ 'font-size': '14px' }}>
                              close
                            </span>
                          </button>
                        </span>
                      );
                    }}
                  </For>
                  <Show when={selectedSets().length === 0}>
                    <span style={{ 'font-size': '0.8125rem', color: 'var(--m3-outline)', fontStyle: 'italic', display: 'flex', 'align-items': 'center', gap: '6px' }}>
                      <span class="material-symbols-outlined" style={{ 'font-size': '16px' }}>info</span>
                      Ningún set seleccionado. Haz clic en la lista abajo para agregar.
                    </span>
                  </Show>
                </div>

                {/* Buscador de Sets con Icono y Contador */}
                <div style={{ 'margin-bottom': '8px' }}>
                  <div style={{ position: 'relative', display: 'flex', 'align-items': 'center' }}>
                    <span
                      class="material-symbols-outlined"
                      style={{
                        position: 'absolute',
                        left: '10px',
                        color: 'var(--m3-outline)',
                        'font-size': '18px',
                        'pointer-events': 'none',
                      }}
                    >
                      search
                    </span>
                    <input
                      type="text"
                      placeholder="Filtrar por nombre o código (ej. Modern Horizons, Outlaws, MH3, BLB)..."
                      value={setFilterText()}
                      onInput={(e) => setSetFilterText(e.currentTarget.value)}
                      style={{
                        width: '100%',
                        background: 'var(--m3-surface-container-high)',
                        border: '1px solid var(--m3-outline-variant)',
                        'border-radius': '8px',
                        padding: '8px 32px 8px 34px',
                        color: 'var(--m3-on-surface)',
                        'font-size': '0.8125rem',
                        outline: 'none',
                      }}
                    />
                    <Show when={setFilterText()}>
                      <button
                        type="button"
                        onClick={() => setSetFilterText('')}
                        style={{
                          position: 'absolute',
                          right: '8px',
                          background: 'transparent',
                          border: 'none',
                          color: 'var(--m3-outline)',
                          cursor: 'pointer',
                          padding: 0,
                          display: 'flex',
                        }}
                        title="Limpiar filtro"
                      >
                        <span class="material-symbols-outlined" style={{ 'font-size': '16px' }}>close</span>
                      </button>
                    </Show>
                  </div>
                  <div style={{ display: 'flex', 'justify-content': 'space-between', 'align-items': 'center', 'margin-top': '4px', padding: '0 2px' }}>
                    <span style={{ 'font-size': '0.6875rem', color: 'var(--m3-outline)' }}>
                      {filteredSets().length} {filteredSets().length === 1 ? 'set disponible' : 'sets disponibles'}
                      {setFilterText() ? ` coincidentes con "${setFilterText()}"` : ' (ordenados por fecha de salida)'}
                    </span>
                    <Show when={setFilterText()}>
                      <button
                        type="button"
                        onClick={() => setSetFilterText('')}
                        style={{ background: 'transparent', border: 'none', color: 'var(--m3-primary)', 'font-size': '0.6875rem', cursor: 'pointer', 'font-weight': 600 }}
                      >
                        Ver todos
                      </button>
                    </Show>
                  </div>
                </div>

                {/* Lista Scrolleable de Sets Disponibles con Código y Nombre Completo */}
                <div
                  style={{
                    display: 'flex',
                    'flex-direction': 'column',
                    gap: '4px',
                    'max-height': '210px',
                    'overflow-y': 'auto',
                    padding: '6px',
                    background: 'var(--m3-surface-container-lowest)',
                    'border-radius': '8px',
                    border: '1px solid var(--m3-outline-variant)',
                  }}
                >
                  <For each={filteredSets()}>
                    {(item) => {
                      const isSel = selectedSets().includes(item.code.toUpperCase());
                      const cleanName = getCleanSetName(item.name, item.code);
                      return (
                        <button
                          type="button"
                          onClick={() => toggleSet(item.code)}
                          style={{
                            display: 'flex',
                            'align-items': 'center',
                            'justify-content': 'space-between',
                            gap: '8px',
                            padding: '6px 10px',
                            'border-radius': '6px',
                            background: isSel ? 'rgba(208, 188, 255, 0.16)' : 'var(--m3-surface-container-high)',
                            color: isSel ? 'var(--m3-primary)' : 'var(--m3-on-surface)',
                            border: isSel ? '1.5px solid var(--m3-primary)' : '1px solid var(--m3-outline-variant)',
                            cursor: 'pointer',
                            transition: 'all 0.15s ease',
                            'text-align': 'left',
                            width: '100%',
                          }}
                          title={`${item.code} - ${cleanName}`}
                        >
                          <div style={{ display: 'flex', 'align-items': 'center', gap: '8px', 'min-width': 0, flex: 1 }}>
                            {/* Badge de Código */}
                            <span
                              style={{
                                background: isSel ? 'var(--m3-primary)' : 'var(--m3-surface-container-highest)',
                                color: isSel ? 'var(--m3-on-primary)' : 'var(--m3-on-surface-variant)',
                                'font-family': 'monospace',
                                'font-weight': 800,
                                'font-size': '0.6875rem',
                                padding: '2px 6px',
                                'border-radius': '4px',
                                'letter-spacing': '0.5px',
                                'flex-shrink': 0,
                              }}
                            >
                              {item.code}
                            </span>

                            {/* Nombre Completo del Set */}
                            <span
                              style={{
                                'font-size': '0.75rem',
                                'font-weight': isSel ? 700 : 500,
                                color: isSel ? 'var(--m3-on-surface)' : 'var(--m3-on-surface)',
                                overflow: 'hidden',
                                'text-overflow': 'ellipsis',
                                'white-space': 'nowrap',
                              }}
                            >
                              {cleanName}
                            </span>
                          </div>

                          {/* Icono de Selección */}
                          <span
                            class="material-symbols-outlined"
                            style={{
                              'font-size': '16px',
                              color: isSel ? 'var(--m3-primary)' : 'var(--m3-outline)',
                              'flex-shrink': 0,
                            }}
                          >
                            {isSel ? 'check_circle' : 'add_circle_outline'}
                          </span>
                        </button>
                      );
                    }}
                  </For>

                  <Show when={filteredSets().length === 0}>
                    <div style={{ padding: '24px 12px', 'text-align': 'center', color: 'var(--m3-outline)' }}>
                      <span class="material-symbols-outlined" style={{ 'font-size': '28px', 'margin-bottom': '4px', opacity: 0.6 }}>
                        search_off
                      </span>
                      <div style={{ 'font-size': '0.8125rem', 'font-weight': 600 }}>
                        No se encontraron sets para "{setFilterText()}"
                      </div>
                      <div style={{ 'font-size': '0.6875rem', 'margin-top': '2px' }}>
                        Prueba buscando por nombre (ej. Modern) o código (ej. MH3)
                      </div>
                    </div>
                  </Show>
                </div>
              </div>

              {/* Modo de Precios (Hoy vs 90 Días Histórico) */}
              <div
                style={{
                  display: 'flex',
                  'align-items': 'center',
                  'justify-content': 'space-between',
                  padding: '12px',
                  background: 'var(--m3-surface-container-high)',
                  'border-radius': '10px',
                  border: '1px solid var(--m3-outline-variant)',
                }}
              >
                <div>
                  <div style={{ 'font-weight': 700, 'font-size': '0.8125rem' }}>Histórico Completo de 90 Días</div>
                  <div style={{ 'font-size': '0.75rem', color: 'var(--m3-on-surface-variant)' }}>
                    {loadHistory() ? 'Descargará AllPrices.json.gz (90 días de evolución temporal)' : 'Snapshot de hoy: AllPricesToday.json.gz (Más rápido)'}
                  </div>
                </div>
                <input
                  type="checkbox"
                  checked={loadHistory()}
                  onChange={(e) => setLoadHistory(e.currentTarget.checked)}
                  style={{ width: '18px', height: '18px', cursor: 'pointer', 'accent-color': 'var(--m3-primary)' }}
                />
              </div>
            </Show>

            {/* Opciones e Información de 'price_prediction_pipeline' */}
            <Show when={selectedDag() === 'price_prediction_pipeline'}>
              <div
                style={{
                  padding: '16px',
                  background: 'linear-gradient(135deg, rgba(139, 92, 246, 0.12), rgba(79, 55, 139, 0.08))',
                  'border-radius': '12px',
                  border: '1px solid rgba(139, 92, 246, 0.3)',
                  display: 'flex',
                  'flex-direction': 'column',
                  gap: '10px',
                }}
              >
                <div style={{ display: 'flex', 'align-items': 'center', gap: '8px', color: '#c4b5fd', 'font-weight': 700, 'font-size': '0.875rem' }}>
                  <span class="material-symbols-outlined" style={{ 'font-size': '20px' }}>psychology</span>
                  Pipeline Machine Learning (PySpark GBTRegressor)
                </div>
                <div style={{ 'font-size': '0.75rem', color: 'var(--m3-on-surface-variant)', 'line-height': 1.5 }}>
                  Entrenamiento distribuido de Gradient-Boosted Trees en Apache Spark. Genera ingeniería de características temporales (lags t-1, t-3, t-7, media móvil 7d y 14d, volatilidad) y predice el próximo precio esperado para cada carta, sincronizando PostgreSQL y el Data Lake Parquet.
                </div>
                <div style={{ display: 'flex', 'flex-wrap': 'wrap', gap: '8px', 'margin-top': '4px', 'font-size': '0.6875rem' }}>
                  <div style={{ background: 'rgba(0,0,0,0.25)', padding: '5px 8px', 'border-radius': '6px', border: '1px solid var(--m3-outline-variant)' }}>
                    <span style={{ color: 'var(--m3-outline)' }}>Algoritmo: </span>
                    <strong style={{ color: 'var(--m3-primary)' }}>Gradient-Boosted Trees</strong>
                  </div>
                  <div style={{ background: 'rgba(0,0,0,0.25)', padding: '5px 8px', 'border-radius': '6px', border: '1px solid var(--m3-outline-variant)' }}>
                    <span style={{ color: 'var(--m3-outline)' }}>Hiperparámetros: </span>
                    <strong style={{ color: '#a78bfa' }}>25 árboles · Profundidad 5</strong>
                  </div>
                  <div style={{ background: 'rgba(0,0,0,0.25)', padding: '5px 8px', 'border-radius': '6px', border: '1px solid var(--m3-outline-variant)' }}>
                    <span style={{ color: 'var(--m3-outline)' }}>Métricas Previas: </span>
                    <strong style={{ color: '#34d399' }}>R²: 91.4% · MAE: $0.82</strong>
                  </div>
                </div>
              </div>
            </Show>

            {/* Mensaje de Error si ocurre */}
            <Show when={submitError()}>
              <div style={{ padding: '10px 14px', background: 'rgba(239, 68, 68, 0.15)', border: '1px solid #ef4444', 'border-radius': '8px', color: '#fca5a5', 'font-size': '0.8125rem' }}>
                {submitError()}
              </div>
            </Show>

            {/* Botón Principal de Disparo */}
            <button
              type="button"
              class="m3-btn m3-btn-filled"
              disabled={isSubmitting() || (selectedDag() === 'selected_set_ingestion' && selectedSets().length === 0)}
              onClick={handleTrigger}
              style={{
                height: '46px',
                'font-size': '0.875rem',
                'font-weight': 700,
                gap: '8px',
                cursor: 'pointer',
                'margin-top': '4px',
                background: selectedDag() === 'price_prediction_pipeline' ? 'linear-gradient(135deg, #7c3aed, #4f46e5)' : undefined,
              }}
            >
              <Show
                when={!isSubmitting()}
                fallback={
                  <>
                    <span class="material-symbols-outlined" style={{ animation: 'spin 1s linear infinite' }}>
                      progress_activity
                    </span>
                    Enviando solicitud a Airflow...
                  </>
                }
              >
                <span class="material-symbols-outlined">
                  {selectedDag() === 'price_prediction_pipeline' ? 'psychology' : 'bolt'}
                </span>
                {selectedDag() === 'price_prediction_pipeline'
                  ? 'Entrenar Modelo y Predecir Precios (Airflow)'
                  : 'Ejecutar Pipeline en Apache Airflow'}
              </Show>
            </button>
          </div>

          {/* ================= COLUMNA DERECHA: MONITOR EN TIEMPO REAL ================= */}
          <div
            style={{
              background: 'var(--m3-surface-container)',
              'border-radius': '16px',
              border: '1px solid var(--m3-outline-variant)',
              padding: '20px',
              display: 'flex',
              'flex-direction': 'column',
              gap: '16px',
            }}
          >
            <div style={{ display: 'flex', 'align-items': 'center', 'justify-content': 'space-between' }}>
              <h3 style={{ 'font-size': '1.05rem', 'font-weight': 700, display: 'flex', 'align-items': 'center', gap: '8px' }}>
                <span class="material-symbols-outlined" style={{ color: '#38bdf8' }}>
                  monitoring
                </span>
                Seguimiento de Progreso & Estado
              </h3>

              <Show when={statusData()}>
                <span
                  style={{
                    background: `${getStatusColor(statusData()?.state)}22`,
                    color: getStatusColor(statusData()?.state),
                    border: `1px solid ${getStatusColor(statusData()?.state)}66`,
                    padding: '3px 10px',
                    'border-radius': '12px',
                    'font-size': '0.75rem',
                    'font-weight': 700,
                  }}
                >
                  {getStatusLabel(statusData()?.state)}
                </span>
              </Show>
            </div>

            {/* BARRA DE PROGRESO CON PORCENTAJE */}
            <div style={{ background: 'var(--m3-surface-container-high)', padding: '16px', 'border-radius': '12px', border: '1px solid var(--m3-outline-variant)' }}>
              <div style={{ display: 'flex', 'align-items': 'center', 'justify-content': 'space-between', 'margin-bottom': '8px' }}>
                <span style={{ 'font-size': '0.8125rem', 'font-weight': 600, color: 'var(--m3-on-surface-variant)' }}>
                  Progreso de Ejecución
                </span>
                <span style={{ 'font-size': '1.35rem', 'font-weight': 800, color: 'var(--m3-primary)' }}>
                  {statusData()?.progress_percent || 0}%
                </span>
              </div>

              {/* Barra SVG / Div Animada */}
              <div
                style={{
                  width: '100%',
                  height: '14px',
                  background: 'var(--m3-surface-container-lowest)',
                  'border-radius': '7px',
                  overflow: 'hidden',
                  position: 'relative',
                  border: '1px solid var(--m3-outline-variant)',
                }}
              >
                <div
                  style={{
                    width: `${statusData()?.progress_percent || 0}%`,
                    height: '100%',
                    background: statusData()?.state === 'failed'
                      ? 'linear-gradient(90deg, #ef4444, #dc2626)'
                      : 'linear-gradient(90deg, var(--m3-primary), #38bdf8)',
                    transition: 'width 0.4s ease-in-out',
                    'border-radius': '7px',
                  }}
                />
              </div>

              {/* Paso Actual */}
              <div style={{ 'margin-top': '10px', display: 'flex', 'align-items': 'center', gap: '8px' }}>
                <span class="material-symbols-outlined" style={{ 'font-size': '18px', color: 'var(--m3-primary)' }}>
                  info
                </span>
                <span style={{ 'font-size': '0.8125rem', color: 'var(--m3-on-surface)', 'font-weight': 500 }}>
                  {statusData()?.current_step || 'Esperando inicio de pipeline...'}
                </span>
              </div>
            </div>

            {/* Stepper de Tareas de Airflow */}
            <div>
              <span style={{ 'font-size': '0.75rem', 'font-weight': 700, color: 'var(--m3-on-surface-variant)', 'text-transform': 'uppercase', display: 'block', 'margin-bottom': '8px' }}>
                Tareas en el DAG ({statusData()?.dag_id || 'Pipeline'})
              </span>
              <div style={{ display: 'grid', 'grid-template-columns': 'repeat(auto-fit, minmax(180px, 1fr))', gap: '8px' }}>
                <For each={statusData()?.tasks || []}>
                  {(task) => (
                    <div
                      style={{
                        padding: '8px 10px',
                        'border-radius': '8px',
                        background: 'var(--m3-surface-container-high)',
                        border: '1px solid var(--m3-outline-variant)',
                        display: 'flex',
                        'align-items': 'center',
                        'justify-content': 'space-between',
                      }}
                    >
                      <span style={{ 'font-size': '0.75rem', 'font-weight': 600, 'text-overflow': 'ellipsis', overflow: 'hidden', 'white-space': 'nowrap', 'max-width': '130px' }} title={task.task_id}>
                        {task.task_id}
                      </span>
                      <span
                        style={{
                          'font-size': '0.625rem',
                          'font-weight': 700,
                          padding: '2px 6px',
                          'border-radius': '6px',
                          background: `${getStatusColor(task.state)}22`,
                          color: getStatusColor(task.state),
                        }}
                      >
                        {task.state || 'pending'}
                      </span>
                    </div>
                  )}
                </For>
                <Show when={(!statusData()?.tasks || statusData()?.tasks.length === 0)}>
                  <div style={{ 'font-size': '0.75rem', color: 'var(--m3-outline)', fontStyle: 'italic', padding: '8px' }}>
                    Las tareas aparecerán tan pronto Airflow programe el DAG.
                  </div>
                </Show>
              </div>
            </div>

            {/* Botones de Observabilidad Externa (Airflow & Jaeger) */}
            <div style={{ display: 'flex', gap: '10px', 'margin-top': 'auto' }}>
              <a
                href={statusData()?.airflow_url || configData()?.airflow_web_url || 'http://localhost:8080'}
                target="_blank"
                rel="noreferrer"
                class="m3-btn m3-btn-tonal"
                style={{ flex: 1, height: '36px', 'font-size': '0.75rem', 'text-decoration': 'none', display: 'flex', 'align-items': 'center', 'justify-content': 'center', gap: '6px' }}
              >
                <span class="material-symbols-outlined" style={{ 'font-size': '16px' }}>account_tree</span>
                Ver Grafo en Airflow
              </a>

              <a
                href={statusData()?.jaeger_url || configData()?.jaeger_ui_url || 'http://localhost:16686'}
                target="_blank"
                rel="noreferrer"
                class="m3-btn m3-btn-tonal"
                style={{
                  flex: 1,
                  height: '36px',
                  'font-size': '0.75rem',
                  'text-decoration': 'none',
                  display: 'flex',
                  'align-items': 'center',
                  'justify-content': 'center',
                  gap: '6px',
                  color: '#c084fc',
                  border: '1px solid rgba(192, 132, 252, 0.3)',
                }}
              >
                <span class="material-symbols-outlined" style={{ 'font-size': '16px' }}>insights</span>
                {detectedTraceId() ? 'Abrir Traza en Jaeger' : 'Buscar en Jaeger'}
              </a>
            </div>
          </div>
        </div>

        {/* ================= SECCIÓN DE LOGS EN VIVO (TERMINAL ESTILO CONSOLA) ================= */}
        <div
          style={{
            background: 'var(--m3-surface-container)',
            'border-radius': '16px',
            border: '1px solid var(--m3-outline-variant)',
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              padding: '12px 18px',
              background: 'var(--m3-surface-container-high)',
              border: 'none',
              'border-bottom': '1px solid var(--m3-outline-variant)',
              display: 'flex',
              'align-items': 'center',
              'justify-content': 'space-between',
            }}
          >
            <div style={{ display: 'flex', 'align-items': 'center', gap: '8px' }}>
              <span class="material-symbols-outlined" style={{ color: '#34d399', 'font-size': '20px' }}>
                terminal
              </span>
              <span style={{ 'font-size': '0.875rem', 'font-weight': 700 }}>
                Salida de Logs en Tiempo Real (Apache Airflow)
              </span>
              <Show when={activeDagRunId()}>
                <span style={{ 'font-size': '0.75rem', color: 'var(--m3-on-surface-variant)' }}>
                  · {activeDagRunId()}
                </span>
              </Show>
            </div>

            <div style={{ display: 'flex', 'align-items': 'center', gap: '8px' }}>
              <label style={{ display: 'flex', 'align-items': 'center', gap: '4px', 'font-size': '0.75rem', color: 'var(--m3-on-surface-variant)', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={autoScrollLogs()}
                  onChange={(e) => setAutoScrollLogs(e.currentTarget.checked)}
                  style={{ 'accent-color': 'var(--m3-primary)' }}
                />
                Auto-scroll
              </label>

              <button
                type="button"
                onClick={pollActiveRun}
                class="m3-btn-icon"
                title="Refrescar logs ahora"
              >
                <span class="material-symbols-outlined" style={{ 'font-size': '18px' }}>refresh</span>
              </button>

              <button
                type="button"
                onClick={() => navigator.clipboard.writeText(logsText())}
                class="m3-btn-icon"
                title="Copiar logs al portapapeles"
              >
                <span class="material-symbols-outlined" style={{ 'font-size': '18px' }}>content_copy</span>
              </button>
            </div>
          </div>

          {/* Banner de Traza Jaeger Detectada si existe en el log */}
          <Show when={detectedTraceId()}>
            <div
              style={{
                background: 'rgba(139, 92, 246, 0.15)',
                borderBottom: '1px solid rgba(139, 92, 246, 0.3)',
                padding: '8px 18px',
                display: 'flex',
                'align-items': 'center',
                'justify-content': 'space-between',
                color: '#d8b4fe',
                'font-size': '0.75rem',
              }}
            >
              <div style={{ display: 'flex', 'align-items': 'center', gap: '6px' }}>
                <span class="material-symbols-outlined" style={{ 'font-size': '16px' }}>link</span>
                <span>Traza Distribuida Detectada en Logs: <strong>{detectedTraceId()}</strong></span>
              </div>
              <a
                href={`${configData()?.jaeger_ui_url || 'http://localhost:16686'}/trace/${detectedTraceId()}`}
                target="_blank"
                rel="noreferrer"
                style={{ color: '#f3e8ff', 'text-decoration': 'underline', 'font-weight': 700 }}
              >
                Ver Traza Completa en Jaeger UI →
              </a>
            </div>
          </Show>

          {/* Consola Monospace */}
          <div
            ref={logContainerRef}
            style={{
              padding: '16px',
              background: '#09080c',
              color: '#a6accd',
              'font-family': 'monospace',
              'font-size': '0.75rem',
              'line-height': 1.5,
              'max-height': '340px',
              'overflow-y': 'auto',
              'white-space': 'pre-wrap',
              'word-break': 'break-all',
            }}
          >
            {logsText() || 'Cargando logs de Airflow...'}
          </div>
        </div>

        {/* ================= GRID INFERIOR: HISTORIAL DE EJECUCIONES Y TRAZAS JAEGER ================= */}
        <div style={{ display: 'grid', 'grid-template-columns': 'repeat(auto-fit, minmax(460px, 1fr))', gap: '24px' }}>
          {/* Historial de Ingestas */}
          <div
            style={{
              background: 'var(--m3-surface-container)',
              'border-radius': '16px',
              border: '1px solid var(--m3-outline-variant)',
              padding: '20px',
            }}
          >
            <div style={{ display: 'flex', 'align-items': 'center', 'justify-content': 'space-between', 'margin-bottom': '14px' }}>
              <h3 style={{ 'font-size': '1rem', 'font-weight': 700, display: 'flex', 'align-items': 'center', gap: '8px' }}>
                <span class="material-symbols-outlined" style={{ color: 'var(--m3-primary)' }}>history</span>
                Historial de Ingestas en Airflow
              </h3>
              <button
                type="button"
                onClick={() => refetchHistory()}
                class="m3-btn-icon"
                title="Refrescar historial"
              >
                <span class="material-symbols-outlined" style={{ 'font-size': '18px' }}>refresh</span>
              </button>
            </div>

            <div style={{ display: 'flex', 'flex-direction': 'column', gap: '8px', 'max-height': '280px', 'overflow-y': 'auto' }}>
              <For each={historyData()?.runs || []}>
                {(run) => {
                  const isCur = activeDagRunId() === run.dag_run_id;
                  const sets = run.conf?.set_codes ? run.conf.set_codes.join(', ') : 'Todos';
                  return (
                    <div
                      onClick={() => loadRunDetails(run.dag_id, run.dag_run_id)}
                      style={{
                        padding: '10px 14px',
                        'border-radius': '10px',
                        background: isCur ? 'rgba(208, 188, 255, 0.12)' : 'var(--m3-surface-container-high)',
                        border: isCur ? '1px solid var(--m3-primary)' : '1px solid var(--m3-outline-variant)',
                        cursor: 'pointer',
                        display: 'flex',
                        'align-items': 'center',
                        'justify-content': 'space-between',
                        transition: 'all 0.2s',
                      }}
                    >
                      <div>
                        <div style={{ 'font-size': '0.8125rem', 'font-weight': 700 }}>
                          {run.dag_id}
                        </div>
                        <div style={{ 'font-size': '0.6875rem', color: 'var(--m3-on-surface-variant)' }}>
                          Sets: {sets} · {run.start_date ? new Date(run.start_date).toLocaleString() : 'En cola'}
                        </div>
                      </div>

                      <div style={{ display: 'flex', 'align-items': 'center', gap: '8px' }}>
                        <span
                          style={{
                            'font-size': '0.6875rem',
                            'font-weight': 700,
                            padding: '2px 6px',
                            'border-radius': '6px',
                            background: `${getStatusColor(run.state)}22`,
                            color: getStatusColor(run.state),
                          }}
                        >
                          {run.state}
                        </span>
                        <span class="material-symbols-outlined" style={{ 'font-size': '16px', color: 'var(--m3-outline)' }}>
                          chevron_right
                        </span>
                      </div>
                    </div>
                  );
                }}
              </For>
            </div>
          </div>

          {/* Trazas de Jaeger Recientes */}
          <div
            style={{
              background: 'var(--m3-surface-container)',
              'border-radius': '16px',
              border: '1px solid var(--m3-outline-variant)',
              padding: '20px',
            }}
          >
            <div style={{ display: 'flex', 'align-items': 'center', 'justify-content': 'space-between', 'margin-bottom': '14px' }}>
              <h3 style={{ 'font-size': '1rem', 'font-weight': 700, display: 'flex', 'align-items': 'center', gap: '8px' }}>
                <span class="material-symbols-outlined" style={{ color: '#a78bfa' }}>analytics</span>
                Trazas Recientes en Jaeger (mtg-spark-pipeline)
              </h3>
              <button
                type="button"
                onClick={() => refetchTraces()}
                class="m3-btn-icon"
                title="Refrescar trazas"
              >
                <span class="material-symbols-outlined" style={{ 'font-size': '18px' }}>refresh</span>
              </button>
            </div>

            <div style={{ display: 'flex', 'flex-direction': 'column', gap: '8px', 'max-height': '280px', 'overflow-y': 'auto' }}>
              <For each={tracesData()?.traces || []}>
                {(tr) => (
                  <a
                    href={tr.jaeger_url}
                    target="_blank"
                    rel="noreferrer"
                    style={{
                      padding: '10px 14px',
                      'border-radius': '10px',
                      background: 'var(--m3-surface-container-high)',
                      border: '1px solid var(--m3-outline-variant)',
                      'text-decoration': 'none',
                      color: 'inherit',
                      display: 'flex',
                      'align-items': 'center',
                      'justify-content': 'space-between',
                      transition: 'all 0.2s',
                    }}
                  >
                    <div>
                      <div style={{ 'font-size': '0.8125rem', 'font-weight': 700, color: 'var(--m3-primary)' }}>
                        {tr.operation_name}
                      </div>
                      <div style={{ 'font-size': '0.6875rem', color: 'var(--m3-on-surface-variant)' }}>
                        Trace: {tr.trace_id.slice(0, 12)}... · {tr.spans_count} spans
                      </div>
                    </div>

                    <div style={{ display: 'flex', 'align-items': 'center', gap: '8px' }}>
                      <span style={{ 'font-size': '0.75rem', 'font-weight': 700, color: '#38bdf8' }}>
                        {tr.duration_ms} ms
                      </span>
                      <span class="material-symbols-outlined" style={{ 'font-size': '16px', color: 'var(--m3-outline)' }}>
                        open_in_new
                      </span>
                    </div>
                  </a>
                )}
              </For>
              <Show when={(!tracesData()?.traces || tracesData()?.traces.length === 0)}>
                <div style={{ 'font-size': '0.8125rem', color: 'var(--m3-outline)', fontStyle: 'italic', padding: '12px' }}>
                  No se encontraron trazas recientes en Jaeger. Ejecuta una ingesta para generar nuevas trazas distribuidas.
                </div>
              </Show>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
};
