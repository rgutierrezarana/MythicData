# """
# Pruebas unitarias para el módulo de Trazabilidad OpenTracing / OpenTelemetry y Jaeger
# """

# import os
# import io
# import sys
# import logging
# import unittest

# # Agregar directorios al path
# sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
# sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../spark_jobs")))

# from spark_jobs.tracing_utils import (
#     init_tracer,
#     get_tracer,
#     trace_span,
#     trace_function,
#     get_current_trace_id,
#     get_current_span_id,
#     get_jaeger_trace_url,
#     set_span_attribute,
#     add_span_event,
#     TraceLogFilter,
#     TraceFormatter,
#     configure_traced_logger
# )


# class TestTracingAndJaeger(unittest.TestCase):

#     def setUp(self):
#         self.tracer = init_tracer("test-spark-service")

#     def test_tracer_initialization(self):
#         """Verifica que el tracer se inicialice y retorne una instancia válida."""
#         tracer = get_tracer()
#         self.assertIsNotNone(tracer)

#     def test_trace_span_and_context_ids(self):
#         """Verifica que un span genere Trace ID y Span ID válidos de 32 y 16 caracteres hexadecimales."""
#         with trace_span("test_operation", {"custom.tag": "value123"}) as span:
#             trace_id = get_current_trace_id()
#             span_id = get_current_span_id()

#             self.assertIsNotNone(trace_id)
#             self.assertIsNotNone(span_id)
#             self.assertEqual(len(trace_id), 32)
#             self.assertEqual(len(span_id), 16)

#             # Verificar URL de Jaeger
#             jaeger_url = get_jaeger_trace_url(trace_id)
#             self.assertTrue(jaeger_url.endswith(f"/trace/{trace_id}"))

#     def test_trace_function_decorator(self):
#         """Verifica que el decorador @trace_function preserve el resultado y capture atributos."""
#         @trace_function("custom_sum_function")
#         def add_numbers(a: int, b: int) -> int:
#             set_span_attribute("math.operation", "addition")
#             add_span_event("calculating_sum", {"operand_a": a, "operand_b": b})
#             return a + b

#         result = add_numbers(15, 27)
#         self.assertEqual(result, 42)

#     def test_log_trace_correlation(self):
#         """
#         Verifica que los logs generados dentro de una función trazada contengan el Trace ID y Span ID
#         permitiendo la correlación directa con Jaeger desde los archivos de logs.
#         """
#         log_capture = io.StringIO()
#         handler = logging.StreamHandler(log_capture)
#         handler.addFilter(TraceLogFilter())
#         handler.setFormatter(TraceFormatter("[%(levelname)s] [trace_id=%(trace_id)s span_id=%(span_id)s] %(message)s"))

#         test_logger = logging.getLogger("TestLogger")
#         test_logger.setLevel(logging.INFO)
#         test_logger.handlers = [handler]

#         with trace_span("log_correlation_test"):
#             active_trace_id = get_current_trace_id()
#             active_span_id = get_current_span_id()
#             test_logger.info("Mensaje de prueba para correlacionar con Jaeger")

#         log_output = log_capture.getvalue()
#         self.assertIn(f"trace_id={active_trace_id}", log_output)
#         self.assertIn(f"span_id={active_span_id}", log_output)
#         self.assertIn("Mensaje de prueba para correlacionar con Jaeger", log_output)

#     def test_span_exception_recording(self):
#         """Verifica que excepciones dentro de una función trazada se propaguen correctamente tras registrar el fallo."""
#         @trace_function("failing_spark_task")
#         def fail_operation():
#             raise ValueError("Error simulado en procesamiento Spark")

#         with self.assertRaises(ValueError):
#             fail_operation()

#     def test_jaeger_url_format(self):
#         """Verifica la generación correcta del enlace hacia la interfaz de Jaeger."""
#         sample_trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
#         url = get_jaeger_trace_url(sample_trace_id)
#         self.assertIn("http://localhost:16686/trace/4bf92f3577b34da6a3ce929d0e0e4736", url)


# if __name__ == "__main__":
#     unittest.main()
