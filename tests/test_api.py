# """
# Pruebas unitarias para el API REST de FastAPI (MTG Card Explorer)
# """

# import unittest
# from fastapi.testclient import TestClient

# from backend.main import app
# from backend.database import init_db


# class TestMTGAPI(unittest.TestCase):

#     @classmethod
#     def setUpClass(cls):
#         init_db()
#         cls.client = TestClient(app)

#     def test_health_check(self):
#         """Verifica que el endpoint de salud responda con 200 y estado healthy."""
#         response = self.client.get("/api/v1/health")
#         self.assertEqual(response.status_code, 200)
#         data = response.json()
#         self.assertEqual(data["status"], "healthy")

#     def test_list_cards_pagination(self):
#         """Verifica que el listado de cartas retorne una estructura paginada con items."""
#         response = self.client.get("/api/v1/cards?page=1&page_size=10")
#         self.assertEqual(response.status_code, 200)
#         data = response.json()
#         self.assertIn("items", data)
#         self.assertIn("total", data)
#         self.assertIn("page", data)
#         self.assertEqual(data["page"], 1)
#         self.assertLessEqual(len(data["items"]), 10)

#     def test_search_cards_by_query(self):
#         """Verifica que la búsqueda por texto filtre cartas por nombre."""
#         response = self.client.get("/api/v1/cards?q=Abrade")
#         self.assertEqual(response.status_code, 200)
#         data = response.json()
#         if data["total"] > 0:
#             self.assertTrue(any("abrade" in c["name"].lower() for c in data["items"]))

#     def test_filter_by_set(self):
#         """Verifica que el filtro por set_code retorne exclusivamente cartas del set solicitado."""
#         response = self.client.get("/api/v1/cards?set_code=MH3&page_size=20")
#         self.assertEqual(response.status_code, 200)
#         data = response.json()
#         for card in data["items"]:
#             self.assertEqual(card["set_code"], "MH3")

#     def test_filter_metadata(self):
#         """Verifica que los metadatos contengan catálogo de sets, rarezas, tipos y estadísticas."""
#         response = self.client.get("/api/v1/filters/metadata")
#         self.assertEqual(response.status_code, 200)
#         data = response.json()
#         self.assertIn("sets", data)
#         self.assertIn("types", data)
#         self.assertIn("rarities", data)
#         self.assertIn("price_stats", data)
#         self.assertGreater(len(data["sets"]), 0)

#     def test_get_card_detail(self):
#         """Verifica la consulta de detalle individual de carta por UUID."""
#         # 1. Obtener primera carta disponible
#         list_resp = self.client.get("/api/v1/cards?page_size=1")
#         self.assertEqual(list_resp.status_code, 200)
#         cards = list_resp.json()["items"]
#         if cards:
#             sample_uuid = cards[0]["uuid"]
#             detail_resp = self.client.get(f"/api/v1/cards/{sample_uuid}")
#             self.assertEqual(detail_resp.status_code, 200)
#             detail = detail_resp.json()
#             self.assertEqual(detail["uuid"], sample_uuid)
#             self.assertIn("name", detail)
#             self.assertIn("prices", detail)

#     def test_get_card_price_history_filtered(self):
#         """Verifica la consulta del historial de precios y estadísticas con filtros dinámicos."""
#         list_resp = self.client.get("/api/v1/cards?has_price=true&page_size=1")
#         self.assertEqual(list_resp.status_code, 200)
#         cards = list_resp.json()["items"]
#         if cards:
#             sample_uuid = cards[0]["uuid"]
#             hist_resp = self.client.get(f"/api/v1/cards/{sample_uuid}/price-history?provider=all&finish=all&days=90")
#             self.assertEqual(hist_resp.status_code, 200)
#             data = hist_resp.json()
#             self.assertEqual(data["card_uuid"], sample_uuid)
#             self.assertIn("stats", data)
#             self.assertIn("history", data)
#             self.assertIn("available_filters", data)
#             self.assertIn("trend", data["stats"])


# if __name__ == "__main__":
#     unittest.main()
