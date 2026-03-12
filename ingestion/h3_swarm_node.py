import asyncio
import hmac
import hashlib
import orjson
import h3
from curl_cffi.requests import AsyncSession
from redis.asyncio import Redis

# Configuración Estricta
REDIS_URL = "redis://localhost:6379"
GATEWAY_URL = "http://host.docker.internal:8080/v1/ingest"
HMAC_SECRET = b"sk_test_cardex_b2b_secret_v1"
MAX_PAGINATION_LIMIT = 400  # Límite teórico de Autoscout/Mobile.de

redis_client = Redis.from_url(REDIS_URL)


def generate_signature(payload_bytes: bytes) -> str:
    """Firma el payload para el Gateway HFT (Fase 3)"""
    return hmac.new(HMAC_SECRET, payload_bytes, hashlib.sha256).hexdigest()


async def attack_hex_zone(session: AsyncSession, hex_id: str):
    """
    Simula el ataque a un portal usando las coordenadas del hexágono.
    Sustituir la lógica de parseo por la del portal específico.
    """
    lat, lng = h3.h3_to_geo(hex_id)
    # El radio se ajusta al tamaño del hexágono actual
    resolution = h3.h3_get_resolution(hex_id)

    # Suplantación absoluta de la huella TLS (JA3/JA4)
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}

    # EJEMPLO DE ENDPOINT (Debe adaptarse al target real)
    # target_url = f"https://api.target-portal.com/search?lat={lat}&lon={lng}&radius={h3_radius}"

    # Simulamos latencia de red y respuesta del WAF
    await asyncio.sleep(0.5)

    # MOCK LOGIC: Simulamos que encontramos mucha densidad en resoluciones bajas
    if resolution < 6:
        return {"total_results": 500, "data": []}  # Falla por saturación
    else:
        # Simulamos éxito de extracción
        return {
            "total_results": 12,
            "data": [
                {
                    "vin": f"SCANNED_H3_{hex_id[:8]}",
                    "PriceRaw": 22500.00,
                    "Currency": "EUR",
                    "OriginCountry": "DE",
                    "TargetMarket": "ES",
                    "DaysOnMarket": 2,
                    "RawDescription": f"Coche extraído del hexágono {hex_id}",
                    "Lat": lat,
                    "Lng": lng,
                }
            ],
        }


async def process_hex(session: AsyncSession, hex_id: str):
    """Motor de Subdivisión Fractal Recursiva"""
    print(f"[NODE] 🎯 Atacando Hexágono: {hex_id} (Res: {h3.h3_get_resolution(hex_id)})")

    try:
        response = await attack_hex_zone(session, hex_id)
        total_results = response.get("total_results", 0)

        if total_results > MAX_PAGINATION_LIMIT:
            # EL NÚCLEO FRACTAL: El hexágono está saturado. Lo reventamos en 7 hijos.
            res = h3.h3_get_resolution(hex_id)
            print(
                f"[NODE] ⚠️ Saturación en {hex_id} ({total_results} activos). Subdividiendo a Res {res+1}..."
            )
            children = h3.h3_to_children(hex_id, res + 1)

            # Inyectamos los 7 hijos de vuelta a la cola de Redis de forma atómica
            await redis_client.lpush("queue:h3_tasks", *children)
            return

        # Extracción exitosa. Procesamos los activos y los disparamos al Gateway.
        vehicles = response.get("data", [])
        if not vehicles:
            return

        for v in vehicles:
            payload = orjson.dumps(v)
            signature = generate_signature(payload)

            # Inyección en milisegundos hacia el Dark Pool
            resp = await session.post(
                GATEWAY_URL,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "X-Partner-ID": "CARDEX_H3_SWARM",
                    "X-Cardex-Signature": signature,
                },
            )
            print(f"[NODE] 🟢 Activo Inyectado -> Gateway [Status: {resp.status_code}] | VIN: {v['vin']}")

    except Exception as e:
        print(f"[NODE] ❌ Error en Hex {hex_id}: {str(e)}")
        # Sistema de reintento: vuelve a la cola
        await redis_client.lpush("queue:h3_tasks", hex_id)


async def swarm_worker():
    """Bucle infinito del nodo extractor"""
    print("[NODE] 🕷️ Swarm Worker Online. TLS Spoofing Activo (Chrome 120).")

    # Iniciamos sesión persistente con curl_cffi para reutilizar sockets TCP
    async with AsyncSession(impersonate="chrome110") as session:
        while True:
            # BLPOP: Espera bloqueante (0 CPU usage) hasta que haya un hexágono en la cola
            task = await redis_client.blpop("queue:h3_tasks", timeout=0)
            if task:
                hex_id = task[1].decode("utf-8")
                await process_hex(session, hex_id)


async def seed_initial_grid():
    """Inyecta la malla inicial si la cola está vacía"""
    queue_len = await redis_client.llen("queue:h3_tasks")
    if queue_len == 0:
        print("[ORACLE] Generando malla base europea (Resolución 4)...")
        # Semilla inicial de ejemplo (Múnich y alrededores)
        seed_hex = h3.geo_to_h3(48.1351, 11.5820, 4)
        await redis_client.lpush("queue:h3_tasks", seed_hex)


async def main():
    await seed_initial_grid()
    await swarm_worker()


if __name__ == "__main__":
    asyncio.run(main())
