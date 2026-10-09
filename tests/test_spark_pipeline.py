# """
# Script de pruebas unitarias y de integración para el pipeline de ingesta MTG (PySpark + PostgreSQL)
# """

# import os
# import sys
# import unittest
# from datetime import date

# # Agregar directorio raíz al PYTHONPATH
# sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
# sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../spark_jobs")))

# from spark_jobs.process_cards_and_prices import extract_price_records, get_card_latest_prices

# class TestMTGPipeline(unittest.TestCase):

#     def test_extract_price_records(self):
#         """
#         Prueba que la extracción de precios aplana correctamente la jerarquía anidada de MTGJSON
#         y separa el snapshot actual del histórico.
#         """
#         sample_uuid = "test-uuid-12345"
#         uuid_set = {sample_uuid}

#         sample_prices_data = {
#             sample_uuid: {
#                 "paper": {
#                     "tcgplayer": {
#                         "currency": "USD",
#                         "retail": {
#                             "normal": {
#                                 "2026-09-01": 25.50,
#                                 "2026-10-02": 30.00
#                             },
#                             "foil": {
#                                 "2026-10-02": 55.00
#                             }
#                         },
#                         "buylist": {
#                             "normal": {
#                                 "2026-10-02": 20.00
#                             }
#                         }
#                     },
#                     "cardmarket": {
#                         "currency": "EUR",
#                         "retail": {
#                             "normal": {
#                                 "2026-10-02": 24.00
#                             }
#                         }
#                     }
#                 }
#             }
#         }

#         all_prices, latest_prices = extract_price_records(uuid_set, sample_prices_data, "MH3")

#         # 1. Verificar total histórico (5 puntos en total: tcg normal d1, tcg normal d2, tcg foil, tcg buylist, cm retail normal = 5)
#         self.assertEqual(len(all_prices), 5)

#         # 2. Verificar snapshot más reciente (4 combinaciones únicas: tcg retail normal, tcg retail foil, tcg buylist normal, cm retail normal)
#         self.assertEqual(len(latest_prices), 4)

#         # 3. Verificar que para tcgplayer normal el precio más reciente sea 30.00 de fecha 2026-10-02
#         tcg_normal_latest = [
#             p for p in latest_prices
#             if p["provider"] == "tcgplayer" and p["price_type"] == "retail" and p["finish"] == "normal"
#         ][0]

#         self.assertEqual(tcg_normal_latest["price"], 30.00)
#         self.assertEqual(tcg_normal_latest["price_date"], date(2026, 10, 2))
#         self.assertEqual(tcg_normal_latest["currency"], "USD")
#         self.assertEqual(tcg_normal_latest["set_code"], "MH3")

#     def test_get_card_latest_prices_summary(self):
#         """
#         Prueba que get_card_latest_prices consolida los precios actuales (USD, EUR, Foil)
#         para permitir el upsert directo en la tabla cards sin duplicar registros.
#         """
#         sample_uuid = "card-test-uuid-99"
#         latest_prices = [
#             {
#                 "card_uuid": sample_uuid,
#                 "provider": "tcgplayer",
#                 "game_format": "paper",
#                 "price_type": "retail",
#                 "finish": "normal",
#                 "currency": "USD",
#                 "price": 32.50,
#                 "price_date": date(2026, 10, 2)
#             },
#             {
#                 "card_uuid": sample_uuid,
#                 "provider": "tcgplayer",
#                 "game_format": "paper",
#                 "price_type": "retail",
#                 "finish": "foil",
#                 "currency": "USD",
#                 "price": 60.00,
#                 "price_date": date(2026, 10, 2)
#             },
#             {
#                 "card_uuid": sample_uuid,
#                 "provider": "cardmarket",
#                 "game_format": "paper",
#                 "price_type": "retail",
#                 "finish": "normal",
#                 "currency": "EUR",
#                 "price": 28.00,
#                 "price_date": date(2026, 10, 2)
#             }
#         ]

#         summary = get_card_latest_prices(sample_uuid, latest_prices)

#         self.assertEqual(summary["current_price_usd"], 32.50)
#         self.assertEqual(summary["current_price_eur"], 28.00)
#         self.assertEqual(summary["current_price_foil"], 60.00)
#         self.assertEqual(summary["current_price_date"], date(2026, 10, 2))
#         self.assertEqual(summary["current_price_provider"], "tcgplayer")

#     def test_differentiate_cards_across_multiple_sets(self):
#         """
#         Prueba que la misma carta en diferentes sets tiene UUIDs distintos y queda perfectamente diferenciada.
#         """
#         uuid_set_mh2 = "uuid-ragavan-mh2"
#         uuid_set_mul = "uuid-ragavan-mul"

#         sample_prices_data = {
#             uuid_set_mh2: {
#                 "paper": {
#                     "tcgplayer": {
#                         "currency": "USD",
#                         "retail": {"normal": {"2026-10-02": 45.00}}
#                     }
#                 }
#             },
#             uuid_set_mul: {
#                 "paper": {
#                     "tcgplayer": {
#                         "currency": "USD",
#                         "retail": {"normal": {"2026-10-02": 35.00}}
#                     }
#                 }
#             }
#         }

#         all_p_mh2, latest_p_mh2 = extract_price_records({uuid_set_mh2}, sample_prices_data, "MH2")
#         all_p_mul, latest_p_mul = extract_price_records({uuid_set_mul}, sample_prices_data, "MUL")

#         self.assertEqual(latest_p_mh2[0]["price"], 45.00)
#         self.assertEqual(latest_p_mh2[0]["set_code"], "MH2")

#         self.assertEqual(latest_p_mul[0]["price"], 35.00)
#         self.assertEqual(latest_p_mul[0]["set_code"], "MUL")

#     def test_handle_missing_or_null_prices_gracefully(self):
#         """
#         Prueba que el pipeline maneja cartas sin precios sin lanzar excepciones.
#         """
#         uuid_without_price = "uuid-no-price-123"
#         all_prices, latest_prices = extract_price_records({uuid_without_price}, {}, "MH3")
#         self.assertEqual(len(all_prices), 0)
#         self.assertEqual(len(latest_prices), 0)

#         summary = get_card_latest_prices(uuid_without_price, [])
#         self.assertIsNone(summary["current_price_usd"])
#         self.assertIsNone(summary["current_price_eur"])
#         self.assertIsNone(summary["current_price_foil"])
#         self.assertIsNone(summary["current_price_date"])


# if __name__ == "__main__":
#     unittest.main()
