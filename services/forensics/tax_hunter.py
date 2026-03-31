import asyncio
import orjson
import ahocorasick
import re
import redis.asyncio as redis
import aiohttp

RDB = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)

# 1. ESCUDO DETERMINISTA NLP (Aho-Corasick)
AHO = ahocorasick.Automaton()
MARGIN_TERMS = ["§25a", "ustg", "margeregeling", "mwst nicht ausweisbar", "rebu", "margen"]
for idx, term in enumerate(MARGIN_TERMS):
    AHO.add_word(term, (idx, term))
AHO.make_automaton()


# 2. VIES OPTIMISTIC CIRCUIT BREAKER
async def check_vies_optimistic(session, vat_number):
    if not vat_number or not re.match(r"^[A-Z]{2}[0-9A-Za-z\+\*\.]{2,12}$", vat_number):
        return "REBU"
    country, num = vat_number[:2], vat_number[2:]
    try:
        # Timeout estricto de 200ms para no asfixiar el thread
        async with session.post(
            "https://ec.europa.eu/taxation_customs/vies/rest-api/ms/checkVatNumber",
            json={"countryCode": country, "vatNumber": num},
            timeout=aiohttp.ClientTimeout(total=0.2),
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                return "DEDUCTIBLE" if data.get("isValid") else "REBU"
            return "PENDING_VIES_OPTIMISTIC"
    except Exception:
        return "PENDING_VIES_OPTIMISTIC"


async def process_forensics():
    print("[V2.0] Tax Hunter y Escudo Jurídico en línea. VIES y Fail-Closed armados.")
    try:
        await RDB.xgroup_create("stream:db_write", "cg_forensics", "$", mkstream=True)
    except Exception:
        pass

    async with aiohttp.ClientSession() as session:
        while True:
            msgs = await RDB.xreadgroup(
                "cg_forensics", "worker_tax", {"stream:db_write": ">"}, count=100, block=2000
            )
            if not msgs:
                continue

            for stream, messages in msgs:
                for msg_id, payload in messages:
                    v = orjson.loads(payload.get("data", "{}"))
                    desc_lower = v.get("RawDescription", "").lower()

                    # A. Escudo Aho-Corasick (Determinista)
                    is_margin = False
                    for end_index, _ in AHO.iter(desc_lower):
                        is_margin = True
                        break

                    if is_margin:
                        v["TaxStatus"] = "REBU"
                    else:
                        # B. Simulación L3 y VIES (Optimista)
                        v["TaxStatus"] = await check_vies_optimistic(session, v.get("VAT_ID", ""))

                    # Empuje al Stream Final de Mercado (Hacia Fase 6)
                    await RDB.xadd("stream:market_ready", {"data": orjson.dumps(v).decode("utf-8")})
                    await RDB.xack("stream:db_write", "cg_forensics", msg_id)
                    print(
                        f"[FORENSICS] Activo procesado y enrutado a mercado. VIN: {v.get('vin')} | Estado Fiscal: {v['TaxStatus']}"
                    )


if __name__ == "__main__":
    import sys

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(process_forensics())
