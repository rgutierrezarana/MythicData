"""
Módulo de Observabilidad y Trazabilidad Distribuida (OpenTracing / OpenTelemetry + Jaeger)
para Jobs de Apache Spark y Pipelines de Ingesta MTG.

Funcionalidades:
1. Instrumentación de funciones Spark con spans y atributos enriquecidos.
2. Inyección automática de Trace ID, Span ID y URL de Jaeger en los logs del sistema.
3. Exportación OTLP / Jaeger hacia el colector Jaeger All-In-One.
4. Soporte para decorador @trace_function y context manager trace_span.
5. Registro de logs como eventos dentro del span activo en Jaeger.
6. Tolerancia a fallos: Si Jaeger no está disponible o el tracing está desactivado,
   opera de forma transparente sin interrumpir los pipelines.
"""

import os
import sys
import time
import socket
import logging
import functools
from contextlib import contextmanager
from typing import Optional, Dict, Any, Callable

# Configuración de variables de entorno para Jaeger / OpenTelemetry
ENABLE_TRACING = os.getenv("ENABLE_TRACING", "true").lower() in ("true", "1", "yes")
SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "mtg-spark-pipeline")
JAEGER_HOST = os.getenv("JAEGER_HOST", "jaeger")
JAEGER_PORT = int(os.getenv("JAEGER_PORT", "6831"))
JAEGER_UI_URL = os.getenv("JAEGER_UI_URL", "http://localhost:16686").rstrip("/")
OTEL_ENDPOINT = os.getenv(
    "OTEL_EXPORTER_OTLP_ENDPOINT", 
    f"http://{JAEGER_HOST}:4318/v1/traces" if JAEGER_HOST != "localhost" else "http://localhost:4318/v1/traces"
)

# OpenTelemetry imports con fallback seguro
_OTEL_AVAILABLE = False
try:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode, Span
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor, ConsoleSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    _OTEL_AVAILABLE = True
except ImportError:
    pass

# OpenTracing imports con fallback
_OPENTRACING_AVAILABLE = False
try:
    import opentracing
    _OPENTRACING_AVAILABLE = True
except ImportError:
    pass

_tracer_initialized = False
_global_tracer = None


def init_tracer(service_name: Optional[str] = None):
    """
    Inicializa el TracerProvider de OpenTelemetry configurado para Jaeger con exportador OTLP HTTP/gRPC.
    Configura el Tracer global para instrumentación de funciones de Spark.
    """
    global _tracer_initialized, _global_tracer

    if _tracer_initialized and _global_tracer is not None:
        return _global_tracer

    svc_name = service_name or SERVICE_NAME

    if not ENABLE_TRACING or not _OTEL_AVAILABLE:
        # Fallback a NoOp Tracer
        if _OTEL_AVAILABLE:
            _global_tracer = trace.get_tracer(svc_name)
        _tracer_initialized = True
        return _global_tracer

    try:
        current_provider = trace.get_tracer_provider()
        if not isinstance(current_provider, TracerProvider):
            resource = Resource.create({
                "service.name": svc_name,
                "service.instance.id": socket.gethostname(),
                "environment": os.getenv("ENVIRONMENT", "production"),
                "framework": "Apache Spark & Airflow"
            })

            provider = TracerProvider(resource=resource)
            
            # Intentar conectar con el colector OTLP de Jaeger
            try:
                otlp_exporter = OTLPSpanExporter(
                    endpoint=OTEL_ENDPOINT,
                    timeout=2
                )
                processor = BatchSpanProcessor(otlp_exporter, max_queue_size=2048, schedule_delay_millis=500)
                provider.add_span_processor(processor)
            except Exception as exp_err:
                logging.getLogger("MTGTracing").debug(
                    f"Endpoint OTLP ({OTEL_ENDPOINT}) no disponible temporalmente: {exp_err}."
                )

            trace.set_tracer_provider(provider)

        _global_tracer = trace.get_tracer(svc_name)
        _tracer_initialized = True
        return _global_tracer

    except Exception as e:
        logging.getLogger("MTGTracing").debug(f"Error inicializando Tracer de OpenTelemetry: {e}")
        if _OTEL_AVAILABLE:
            _global_tracer = trace.get_tracer(svc_name)
        _tracer_initialized = True
        return _global_tracer


def get_tracer():
    """Retorna la instancia activa del Tracer."""
    if not _tracer_initialized:
        return init_tracer()
    return _global_tracer or (_OTEL_AVAILABLE and trace.get_tracer(SERVICE_NAME))


def get_current_trace_id() -> Optional[str]:
    """Retorna el Trace ID actual en formato hexadecimal estándar de 32 caracteres."""
    if not _OTEL_AVAILABLE:
        return None
    span = trace.get_current_span()
    if span and span.get_span_context().is_valid:
        return f"{span.get_span_context().trace_id:032x}"
    return None


def get_current_span_id() -> Optional[str]:
    """Retorna el Span ID actual en formato hexadecimal estándar de 16 caracteres."""
    if not _OTEL_AVAILABLE:
        return None
    span = trace.get_current_span()
    if span and span.get_span_context().is_valid:
        return f"{span.get_span_context().span_id:016x}"
    return None


def get_jaeger_trace_url(trace_id: Optional[str] = None) -> Optional[str]:
    """
    Genera el enlace directo a la interfaz web de Jaeger para el Trace ID dado o el actual.
    Ejemplo: http://localhost:16686/trace/4bf92f3577b34da6a3ce929d0e0e4736
    """
    t_id = trace_id or get_current_trace_id()
    if t_id:
        return f"{JAEGER_UI_URL}/trace/{t_id}"
    return None


# ==============================================================================
# Filtro y Formateador de Logging para Correlación de Logs con Jaeger
# ==============================================================================

class TraceLogFilter(logging.Filter):
    """
    Filtro de Logging que inyecta automáticamente los campos 'trace_id', 'span_id'
    y 'jaeger_url' en cada LogRecord para correlación directa en consola y archivos de logs.
    """
    def filter(self, record: logging.LogRecord) -> bool:
        t_id = get_current_trace_id()
        s_id = get_current_span_id()
        
        record.trace_id = t_id if t_id else "-"
        record.span_id = s_id if s_id else "-"
        record.jaeger_url = get_jaeger_trace_url(t_id) if t_id else "-"
        return True


class TraceFormatter(logging.Formatter):
    """
    Formateador de logs que incluye información de traza y el enlace de Jaeger.
    Formato:
    [2026-10-09 04:25:10] [INFO] [trace_id=... span_id=...] MTGPipeline: Mensaje
    """
    def format(self, record: logging.LogRecord) -> str:
        if not hasattr(record, "trace_id"):
            t_id = get_current_trace_id()
            s_id = get_current_span_id()
            record.trace_id = t_id if t_id else "-"
            record.span_id = s_id if s_id else "-"
            record.jaeger_url = get_jaeger_trace_url(t_id) if t_id else "-"

        return super().format(record)


class SpanLogHandler(logging.Handler):
    """
    Handler de logging que sincroniza cada mensaje de log con el Span activo de OpenTelemetry / Jaeger
    creando un 'Span Event' enriquecido con el nivel y el mensaje del log.
    """
    def emit(self, record: logging.LogRecord):
        if not _OTEL_AVAILABLE:
            return
        try:
            span = trace.get_current_span()
            if span and span.get_span_context().is_valid:
                span.add_event(
                    name=f"log.{record.levelname.lower()}",
                    attributes={
                        "log.level": record.levelname,
                        "log.message": record.getMessage(),
                        "log.logger": record.name,
                        "log.file": record.filename or "",
                        "log.line": record.lineno or 0
                    }
                )
        except Exception:
            pass


def configure_traced_logger(
    name: str = "MTGPipeline", 
    level: int = logging.INFO,
    include_jaeger_link: bool = True
) -> logging.Logger:
    """
    Configura y retorna un Logger enriquecido con información de trazas y enlace a Jaeger.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Evitar duplicar handlers
    if not any(isinstance(f, TraceLogFilter) for h in logger.handlers for f in h.filters):
        handler = logging.StreamHandler(sys.stdout)
        trace_filter = TraceLogFilter()
        handler.addFilter(trace_filter)
        
        if include_jaeger_link:
            fmt = "[%(asctime)s] [%(levelname)s] [trace_id=%(trace_id)s span_id=%(span_id)s] %(name)s: %(message)s"
        else:
            fmt = "[%(asctime)s] [%(levelname)s] %(name)s: %(message)s"
            
        formatter = TraceFormatter(fmt=fmt, datefmt="%Y-%m-%d %H:%M:%S")
        handler.setFormatter(formatter)
        
        # Reemplazar handlers existentes para evitar logs dobles
        logger.handlers = [handler]
        
        # Agregar SpanLogHandler para que los logs aparezcan dentro de la UI de Jaeger
        span_handler = SpanLogHandler()
        span_handler.setFormatter(formatter)
        logger.addHandler(span_handler)
        
    return logger


# ==============================================================================
# Context Manager y Decorador para Instrumentar Funciones Spark
# ==============================================================================

@contextmanager
def trace_span(
    name: str, 
    attributes: Optional[Dict[str, Any]] = None,
    log_jaeger_link: bool = False
):
    """
    Context Manager para envolver bloques de código de PySpark en un Span de Jaeger.
    
    Uso:
        with trace_span("spark_read_parquet", {"file.path": path}) as span:
            df = spark.read.parquet(path)
    """
    tracer = get_tracer()
    if not tracer or not _OTEL_AVAILABLE or not ENABLE_TRACING:
        yield None
        return

    with tracer.start_as_current_span(name) as span:
        if attributes:
            for k, v in attributes.items():
                if v is not None:
                    span.set_attribute(k, str(v) if not isinstance(v, (int, float, bool, str)) else v)
        
        trace_id = get_current_trace_id()
        if log_jaeger_link and trace_id:
            jaeger_link = get_jaeger_trace_url(trace_id)
            logging.getLogger("MTGPipeline").info(f"📍 Trace iniciado '{name}' -> Ver en Jaeger: {jaeger_link}")

        try:
            yield span
            span.set_status(Status(StatusCode.OK))
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise


def trace_function(
    span_name: Optional[str] = None,
    attributes: Optional[Dict[str, Any]] = None,
    log_jaeger_link: bool = False
):
    """
    Decorador para instrumentar automáticamente cualquier función de Spark / ETL con OpenTracing / Jaeger.
    
    Uso:
        @trace_function("process_single_set", log_jaeger_link=True)
        def process_single_set(spark, conn, set_code, all_prices):
            ...
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            name = span_name or f"spark.{func.__module__}.{func.__name__}"
            
            # Recopilar atributos iniciales
            span_attrs = {
                "function.name": func.__name__,
                "function.module": func.__module__,
                "spark.service": SERVICE_NAME
            }
            if attributes:
                span_attrs.update(attributes)
                
            # Extraer argumentos relevantes para tracing sin comprometer datos pesados
            if args:
                for idx, arg in enumerate(args):
                    if isinstance(arg, (str, int, float, bool)):
                        span_attrs[f"arg.{idx}"] = arg
            if kwargs:
                for k, v in kwargs.items():
                    if isinstance(v, (str, int, float, bool)):
                        span_attrs[f"kwarg.{k}"] = v

            with trace_span(name, attributes=span_attrs, log_jaeger_link=log_jaeger_link) as span:
                start_time = time.time()
                result = func(*args, **kwargs)
                duration_ms = (time.time() - start_time) * 1000
                
                if span:
                    span.set_attribute("execution.duration_ms", duration_ms)
                    if result is not None and isinstance(result, (int, float, str, bool)):
                        span.set_attribute("function.result", str(result))
                return result
        return wrapper
    return decorator


def add_span_event(name: str, attributes: Optional[Dict[str, Any]] = None):
    """Agrega un evento/anotación con timestamp al span activo."""
    if not _OTEL_AVAILABLE:
        return
    span = trace.get_current_span()
    if span and span.get_span_context().is_valid:
        span.add_event(name=name, attributes=attributes or {})


def set_span_attribute(key: str, value: Any):
    """Establece un atributo o tag en el span activo."""
    if not _OTEL_AVAILABLE:
        return
    span = trace.get_current_span()
    if span and span.get_span_context().is_valid:
        if value is not None:
            val = str(value) if not isinstance(value, (int, float, bool, str)) else value
            span.set_attribute(key, val)
