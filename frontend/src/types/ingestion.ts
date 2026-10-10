export interface IngestionTriggerRequest {
  dag_id: string;
  set_codes: string[];
  load_history: boolean;
}

export interface IngestionTriggerResponse {
  dag_id: string;
  dag_run_id: string;
  state: string;
  logical_date?: string;
  conf: Record<string, any>;
  message: string;
  airflow_url: string;
}

export interface TaskInstanceItem {
  task_id: string;
  state?: string;
  duration?: number;
  start_date?: string;
  end_date?: string;
  try_number: number;
}

export interface IngestionStatusResponse {
  dag_id: string;
  dag_run_id: string;
  state: 'queued' | 'running' | 'success' | 'failed' | string;
  progress_percent: number;
  current_step: string;
  start_date?: string;
  end_date?: string;
  execution_date?: string;
  conf: Record<string, any>;
  tasks: TaskInstanceItem[];
  airflow_url: string;
  jaeger_url: string;
  latest_trace_id?: string;
}

export interface IngestionLogResponse {
  dag_id: string;
  dag_run_id: string;
  task_id: string;
  log: string;
  jaeger_trace_id?: string;
  jaeger_trace_url?: string;
}

export interface IngestionDagOption {
  dag_id: string;
  name: string;
  description: string;
  supports_sets: boolean;
  supports_history: boolean;
}

export interface IngestionSetOption {
  code: string;
  name: string;
}

export interface IngestionConfigResponse {
  available_dags: IngestionDagOption[];
  available_sets: IngestionSetOption[];
  airflow_connected: boolean;
  jaeger_connected: boolean;
  airflow_web_url: string;
  jaeger_ui_url: string;
}

export interface IngestionHistoryItem {
  dag_id: string;
  dag_run_id: string;
  state: string;
  progress_percent: number;
  start_date?: string;
  end_date?: string;
  conf: Record<string, any>;
  run_type?: string;
  airflow_url: string;
  jaeger_trace_id?: string;
  jaeger_url?: string;
}

export interface IngestionHistoryResponse {
  runs: IngestionHistoryItem[];
  total: number;
}

export interface JaegerTraceSummary {
  trace_id: string;
  operation_name: string;
  duration_ms: number;
  start_time: string;
  spans_count: number;
  jaeger_url: string;
}

export interface JaegerTracesResponse {
  traces: JaegerTraceSummary[];
  total: number;
}
