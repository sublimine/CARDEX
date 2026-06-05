#!/bin/sh
# =============================================================================
# CARDEX — MeiliSearch index initialisation + demo seed
# Creates the "vehicles" index, configures attributes, and adds 30 sample docs.
# =============================================================================

set -e

MEILI_URL="${MEILI_URL:-http://meilisearch:7700}"
MEILI_KEY="${MEILI_MASTER_KEY:-cardex_meili_dev_only}"
INDEX="vehicles"

echo "[meili-seed] Waiting for MeiliSearch at $MEILI_URL ..."
until curl -sf "$MEILI_URL/health" -H "Authorization: Bearer $MEILI_KEY" | grep -q '"status":"available"'; do
  sleep 2
done
echo "[meili-seed] MeiliSearch is up."

# ── Create index ──────────────────────────────────────────────────────────────
curl -sf -X POST "$MEILI_URL/indexes" \
  -H "Authorization: Bearer $MEILI_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"uid\":\"$INDEX\",\"primaryKey\":\"vehicle_ulid\"}" || true

sleep 2

# ── Filterable attributes ─────────────────────────────────────────────────────
curl -sf -X PUT "$MEILI_URL/indexes/$INDEX/settings/filterable-attributes" \
  -H "Authorization: Bearer $MEILI_KEY" \
  -H "Content-Type: application/json" \
  -d '["make","model","year","mileage_km","price_eur","source_country","fuel_type","transmission","listing_status","h3_res4"]'

# ── Sortable attributes ───────────────────────────────────────────────────────
curl -sf -X PUT "$MEILI_URL/indexes/$INDEX/settings/sortable-attributes" \
  -H "Authorization: Bearer $MEILI_KEY" \
  -H "Content-Type: application/json" \
  -d '["price_eur","mileage_km","year"]'

# ── Searchable attributes ─────────────────────────────────────────────────────
curl -sf -X PUT "$MEILI_URL/indexes/$INDEX/settings/searchable-attributes" \
  -H "Authorization: Bearer $MEILI_KEY" \
  -H "Content-Type: application/json" \
  -d '["make","model","variant","color","fuel_type","transmission"]'

sleep 3
echo "[meili-seed] Index settings applied. Adding 30 demo vehicles..."

# ── Add documents ─────────────────────────────────────────────────────────────
curl -sf -X POST "$MEILI_URL/indexes/$INDEX/documents" \
  -H "Authorization: Bearer $MEILI_KEY" \
  -H "Content-Type: application/json" \
  -d '[
  {"vehicle_ulid":"01HVSEED000000000000000001","make":"BMW","model":"3 Series","variant":"320d Sport Line","year":2021,"mileage_km":48200,"price_eur":28900,"fuel_type":"Diesel","transmission":"Automatic","color":"Black","source_country":"DE","source_url":"https://www.autoscout24.de/angebote/bmw-320d-diesel-schwarz-seed-001","thumbnail_url":null,"listing_status":"ACTIVE","h3_res4":"8408534bfffffff"},
  {"vehicle_ulid":"01HVSEED000000000000000002","make":"BMW","model":"5 Series","variant":"520i Luxury","year":2020,"mileage_km":61000,"price_eur":33500,"fuel_type":"Gasoline","transmission":"Automatic","color":"White","source_country":"DE","source_url":"https://www.autoscout24.de/angebote/bmw-520i-benzin-weiss-seed-002","thumbnail_url":null,"listing_status":"ACTIVE","h3_res4":"841faebffffffff"},
  {"vehicle_ulid":"01HVSEED000000000000000003","make":"BMW","model":"X3","variant":"xDrive20d","year":2022,"mileage_km":22000,"price_eur":41900,"fuel_type":"Diesel","transmission":"Automatic","color":"Grey","source_country":"DE","source_url":"https://www.mobile.de/fahrzeugboerse/bmw-x3-seed-003","thumbnail_url":null,"listing_status":"ACTIVE","h3_res4":"8408534bfffffff"},
  {"vehicle_ulid":"01HVSEED000000000000000004","make":"Mercedes-Benz","model":"C-Class","variant":"C220d AMG Line","year":2021,"mileage_km":39800,"price_eur":35900,"fuel_type":"Diesel","transmission":"Automatic","color":"Silver","source_country":"DE","source_url":"https://www.autoscout24.de/angebote/mercedes-c220d-silber-seed-004","thumbnail_url":null,"listing_status":"ACTIVE","h3_res4":"84172aeffffffff"},
  {"vehicle_ulid":"01HVSEED000000000000000005","make":"Mercedes-Benz","model":"E-Class","variant":"E300 Avantgarde","year":2020,"mileage_km":55000,"price_eur":38500,"fuel_type":"Gasoline","transmission":"Automatic","color":"Blue","source_country":"DE","source_url":"https://www.mobile.de/fahrzeugboerse/mercedes-e300-seed-005","thumbnail_url":null,"listing_status":"ACTIVE","h3_res4":"84172aeffffffff"},
  {"vehicle_ulid":"01HVSEED000000000000000006","make":"Volkswagen","model":"Golf","variant":"GTI 2.0 TSI","year":2022,"mileage_km":18500,"price_eur":32900,"fuel_type":"Gasoline","transmission":"Manual","color":"Red","source_country":"DE","source_url":"https://www.autoscout24.de/angebote/vw-golf-gti-rot-seed-006","thumbnail_url":null,"listing_status":"ACTIVE","h3_res4":"84172aeffffffff"},
  {"vehicle_ulid":"01HVSEED000000000000000007","make":"Volkswagen","model":"Passat","variant":"TDI Business","year":2021,"mileage_km":67000,"price_eur":22900,"fuel_type":"Diesel","transmission":"Automatic","color":"Black","source_country":"DE","source_url":"https://www.mobile.de/fahrzeugboerse/vw-passat-tdi-seed-007","thumbnail_url":null,"listing_status":"ACTIVE","h3_res4":"8408534bfffffff"},
  {"vehicle_ulid":"01HVSEED000000000000000008","make":"Volkswagen","model":"ID.4","variant":"Pro Performance","year":2023,"mileage_km":12000,"price_eur":42500,"fuel_type":"Electric","transmission":"Automatic","color":"White","source_country":"DE","source_url":"https://www.autoscout24.de/angebote/vw-id4-pro-weiss-seed-008","thumbnail_url":null,"listing_status":"ACTIVE","h3_res4":"8408534bfffffff"},
  {"vehicle_ulid":"01HVSEED000000000000000009","make":"Audi","model":"A4","variant":"2.0 TDI S-Line","year":2021,"mileage_km":43000,"price_eur":31900,"fuel_type":"Diesel","transmission":"Automatic","color":"Grey","source_country":"DE","source_url":"https://www.autoscout24.de/angebote/audi-a4-tdi-grau-seed-009","thumbnail_url":null,"listing_status":"ACTIVE","h3_res4":"841faebffffffff"},
  {"vehicle_ulid":"01HVSEED000000000000000010","make":"Audi","model":"Q5","variant":"40 TDI quattro","year":2022,"mileage_km":28000,"price_eur":44900,"fuel_type":"Diesel","transmission":"Automatic","color":"Silver","source_country":"DE","source_url":"https://www.mobile.de/fahrzeugboerse/audi-q5-tdi-seed-010","thumbnail_url":null,"listing_status":"ACTIVE","h3_res4":"841faebffffffff"},
  {"vehicle_ulid":"01HVSEED000000000000000011","make":"Toyota","model":"Corolla","variant":"2.0 Hybrid","year":2022,"mileage_km":21000,"price_eur":27500,"fuel_type":"Hybrid","transmission":"Automatic","color":"White","source_country":"ES","source_url":"https://www.wallapop.com/coches/toyota-corolla-seed-011","thumbnail_url":null,"listing_status":"ACTIVE","h3_res4":"84390cbffffffff"},
  {"vehicle_ulid":"01HVSEED000000000000000012","make":"Toyota","model":"RAV4","variant":"Hybrid AWD","year":2021,"mileage_km":34000,"price_eur":35900,"fuel_type":"Hybrid","transmission":"Automatic","color":"Black","source_country":"ES","source_url":"https://www.coches.net/toyota/rav4/seed-012","thumbnail_url":null,"listing_status":"ACTIVE","h3_res4":"84390cbffffffff"},
  {"vehicle_ulid":"01HVSEED000000000000000013","make":"Ford","model":"Focus","variant":"ST-Line 1.5 EcoBoost","year":2021,"mileage_km":41000,"price_eur":18900,"fuel_type":"Gasoline","transmission":"Manual","color":"Blue","source_country":"FR","source_url":"https://www.leboncoin.fr/voitures/ford-focus-st-seed-013","thumbnail_url":null,"listing_status":"ACTIVE","h3_res4":"8415aaaffffffff"},
  {"vehicle_ulid":"01HVSEED000000000000000014","make":"Ford","model":"Mustang Mach-E","variant":"Extended Range RWD","year":2022,"mileage_km":19000,"price_eur":44900,"fuel_type":"Electric","transmission":"Automatic","color":"Red","source_country":"DE","source_url":"https://www.autoscout24.de/angebote/ford-mach-e-rot-seed-014","thumbnail_url":null,"listing_status":"ACTIVE","h3_res4":"841faebffffffff"},
  {"vehicle_ulid":"01HVSEED000000000000000015","make":"Renault","model":"Megane","variant":"E-Tech Electric","year":2023,"mileage_km":8000,"price_eur":36900,"fuel_type":"Electric","transmission":"Automatic","color":"Grey","source_country":"FR","source_url":"https://www.leboncoin.fr/voitures/renault-megane-etech-seed-015","thumbnail_url":null,"listing_status":"ACTIVE","h3_res4":"8415aaaffffffff"},
  {"vehicle_ulid":"01HVSEED000000000000000016","make":"Renault","model":"Clio","variant":"1.0 TCe Zen","year":2022,"mileage_km":24000,"price_eur":14500,"fuel_type":"Gasoline","transmission":"Manual","color":"Orange","source_country":"FR","source_url":"https://www.leboncoin.fr/voitures/renault-clio-seed-016","thumbnail_url":null,"listing_status":"ACTIVE","h3_res4":"8415aaaffffffff"},
  {"vehicle_ulid":"01HVSEED000000000000000017","make":"Peugeot","model":"308","variant":"1.5 BlueHDi Allure","year":2022,"mileage_km":31000,"price_eur":21900,"fuel_type":"Diesel","transmission":"Automatic","color":"White","source_country":"FR","source_url":"https://www.leboncoin.fr/voitures/peugeot-308-seed-017","thumbnail_url":null,"listing_status":"ACTIVE","h3_res4":"8415aaaffffffff"},
  {"vehicle_ulid":"01HVSEED000000000000000018","make":"SEAT","model":"Leon","variant":"1.5 TSI FR","year":2022,"mileage_km":19000,"price_eur":22900,"fuel_type":"Gasoline","transmission":"Manual","color":"Blue","source_country":"ES","source_url":"https://www.coches.net/seat/leon/seed-018","thumbnail_url":null,"listing_status":"ACTIVE","h3_res4":"84390cbffffffff"},
  {"vehicle_ulid":"01HVSEED000000000000000019","make":"Cupra","model":"Formentor","variant":"VZ 2.0 TSI 4Drive","year":2022,"mileage_km":26000,"price_eur":38900,"fuel_type":"Gasoline","transmission":"Automatic","color":"Black","source_country":"ES","source_url":"https://www.wallapop.com/coches/cupra-formentor-seed-019","thumbnail_url":null,"listing_status":"ACTIVE","h3_res4":"84390cbffffffff"},
  {"vehicle_ulid":"01HVSEED000000000000000020","make":"Volvo","model":"XC60","variant":"Recharge T6 AWD","year":2022,"mileage_km":31000,"price_eur":47900,"fuel_type":"Hybrid","transmission":"Automatic","color":"Silver","source_country":"NL","source_url":"https://www.marktplaats.nl/v/volvo/xc60/seed-020","thumbnail_url":null,"listing_status":"ACTIVE","h3_res4":"84180e3ffffffff"},
  {"vehicle_ulid":"01HVSEED000000000000000021","make":"Hyundai","model":"IONIQ 5","variant":"Long Range AWD","year":2022,"mileage_km":25000,"price_eur":43900,"fuel_type":"Electric","transmission":"Automatic","color":"White","source_country":"NL","source_url":"https://www.marktplaats.nl/v/hyundai/ioniq5/seed-021","thumbnail_url":null,"listing_status":"ACTIVE","h3_res4":"84180e3ffffffff"},
  {"vehicle_ulid":"01HVSEED000000000000000022","make":"Kia","model":"EV6","variant":"GT-Line AWD","year":2022,"mileage_km":22000,"price_eur":42500,"fuel_type":"Electric","transmission":"Automatic","color":"Grey","source_country":"DE","source_url":"https://www.autoscout24.de/angebote/kia-ev6-grau-seed-022","thumbnail_url":null,"listing_status":"ACTIVE","h3_res4":"84172aeffffffff"},
  {"vehicle_ulid":"01HVSEED000000000000000023","make":"Skoda","model":"Octavia","variant":"2.0 TDI Style DSG","year":2021,"mileage_km":52000,"price_eur":23900,"fuel_type":"Diesel","transmission":"Automatic","color":"Green","source_country":"DE","source_url":"https://www.mobile.de/fahrzeugboerse/skoda-octavia-tdi-seed-023","thumbnail_url":null,"listing_status":"ACTIVE","h3_res4":"8408534bfffffff"},
  {"vehicle_ulid":"01HVSEED000000000000000024","make":"Opel","model":"Astra","variant":"1.2 Turbo GS","year":2023,"mileage_km":9500,"price_eur":25900,"fuel_type":"Gasoline","transmission":"Automatic","color":"Black","source_country":"FR","source_url":"https://www.leboncoin.fr/voitures/opel-astra-gs-seed-024","thumbnail_url":null,"listing_status":"ACTIVE","h3_res4":"8415aaaffffffff"},
  {"vehicle_ulid":"01HVSEED000000000000000025","make":"Tesla","model":"Model 3","variant":"Long Range AWD","year":2022,"mileage_km":35000,"price_eur":39900,"fuel_type":"Electric","transmission":"Automatic","color":"White","source_country":"NL","source_url":"https://www.marktplaats.nl/v/tesla/model3/seed-025","thumbnail_url":null,"listing_status":"ACTIVE","h3_res4":"84180e3ffffffff"},
  {"vehicle_ulid":"01HVSEED000000000000000026","make":"Tesla","model":"Model Y","variant":"Performance","year":2023,"mileage_km":18000,"price_eur":54900,"fuel_type":"Electric","transmission":"Automatic","color":"Red","source_country":"DE","source_url":"https://www.autoscout24.de/angebote/tesla-model-y-perf-seed-026","thumbnail_url":null,"listing_status":"ACTIVE","h3_res4":"8408534bfffffff"},
  {"vehicle_ulid":"01HVSEED000000000000000027","make":"Porsche","model":"Cayenne","variant":"E-Hybrid","year":2021,"mileage_km":41000,"price_eur":79900,"fuel_type":"Hybrid","transmission":"Automatic","color":"Silver","source_country":"DE","source_url":"https://www.mobile.de/fahrzeugboerse/porsche-cayenne-hybrid-seed-027","thumbnail_url":null,"listing_status":"ACTIVE","h3_res4":"841faebffffffff"},
  {"vehicle_ulid":"01HVSEED000000000000000028","make":"Fiat","model":"500","variant":"1.0 Hybrid Dolcevita","year":2022,"mileage_km":15000,"price_eur":15900,"fuel_type":"Hybrid","transmission":"Manual","color":"Yellow","source_country":"ES","source_url":"https://www.wallapop.com/coches/fiat-500-seed-028","thumbnail_url":null,"listing_status":"ACTIVE","h3_res4":"84390cbffffffff"},
  {"vehicle_ulid":"01HVSEED000000000000000029","make":"Honda","model":"CR-V","variant":"e:HEV 4WD","year":2023,"mileage_km":11000,"price_eur":43900,"fuel_type":"Hybrid","transmission":"Automatic","color":"Blue","source_country":"NL","source_url":"https://www.marktplaats.nl/v/honda/crv/seed-029","thumbnail_url":null,"listing_status":"ACTIVE","h3_res4":"84180e3ffffffff"},
  {"vehicle_ulid":"01HVSEED000000000000000030","make":"Nissan","model":"Leaf","variant":"e+ Tekna 62kWh","year":2022,"mileage_km":28000,"price_eur":26900,"fuel_type":"Electric","transmission":"Automatic","color":"White","source_country":"DE","source_url":"https://www.autoscout24.de/angebote/nissan-leaf-plus-seed-030","thumbnail_url":null,"listing_status":"ACTIVE","h3_res4":"8408534bfffffff"}
]'

echo "[meili-seed] 30 demo vehicles indexed in MeiliSearch. Done."
