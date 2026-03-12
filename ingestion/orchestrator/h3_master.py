"""
Orquestador Continental H3 — Sembrado de hexágonos para los 6 países objetivo.
Genera tareas geográficas en queue:h3_tasks para consumo por el enjambre api_crawler.
Sintaxis H3 v4: polygon_to_cells + LatLngPoly (Latitud, Longitud).
"""
import json
import logging
import os

import h3
import redis

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [H3 MASTER] %(message)s",
)

REDIS_ADDR = os.getenv("REDIS_ADDR", "127.0.0.1:6379")
_host, _, _port = REDIS_ADDR.partition(":")
rdb = redis.Redis(host=_host or "127.0.0.1", port=int(_port or 6379), db=0, decode_responses=True)

# Bounding boxes de los 6 países [MinLat, MinLng, MaxLat, MaxLng]
MARKETS = {
    "DE": [47.2, 5.8, 55.1, 15.0],
    "FR": [41.3, -5.1, 51.1, 9.5],
    "ES": [36.0, -9.3, 43.8, 3.3],
    "BE": [49.4, 2.5, 51.5, 6.4],
    "NL": [50.7, 3.3, 53.5, 7.2],
    "CH": [45.8, 5.9, 47.8, 10.5],
}


def seed_continent():
    rdb.delete("queue:h3_tasks")
    total_hexagons = 0
    base_resolution = 4  # ~250 km² por hexágono

    logging.info("Iniciando triangulación continental sobre: DE, FR, ES, BE, NL, CH")

    for country, bbox in MARKETS.items():
        min_lat, min_lng, max_lat, max_lng = bbox

        # H3 v4: tuplas estrictas (Latitud, Longitud)
        exterior = [
            (min_lat, min_lng),
            (min_lat, max_lng),
            (max_lat, max_lng),
            (max_lat, min_lng),
            (min_lat, min_lng),
        ]

        poly = h3.LatLngPoly(exterior)
        hexagons = h3.polygon_to_cells(poly, base_resolution)

        for h in hexagons:
            task = json.dumps({"country": country, "h3_index": h, "resolution": base_resolution})
            rdb.lpush("queue:h3_tasks", task)

        logging.info("[%s] Mapeado. %d sectores geográficos generados.", country, len(hexagons))
        total_hexagons += len(hexagons)

    logging.info("Sembrado completado. %d vectores inyectados en Redis. Despertando Enjambre...", total_hexagons)


if __name__ == "__main__":
    seed_continent()
