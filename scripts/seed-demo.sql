-- =============================================================================
-- CARDEX — Demo seed data (30 vehicles across EU portals)
-- Run once after init-pg.sql to populate the marketplace with sample listings.
-- =============================================================================

-- Skip if already seeded
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM vehicles WHERE source_platform = 'SEED_DEMO' LIMIT 1) THEN
    RAISE NOTICE 'Demo seed already applied, skipping.';
    RETURN;
  END IF;
END $$;

INSERT INTO vehicles (
  vehicle_ulid, fingerprint_sha256,
  source_id, source_platform, ingestion_channel,
  make, model, variant, year, mileage_km,
  fuel_type, transmission, color, power_kw, doors,
  price_raw, currency_raw, gross_physical_cost_eur,
  source_url, source_country,
  listing_status, lifecycle_status,
  seller_type, lat, lng
) VALUES

-- BMW -------------------------------------------------------------------------
('01HVSEED000000000000000001', md5('seed-001'),
 'seed-001', 'SEED_DEMO', 'SCRAPER',
 'BMW', '3 Series', '320d Sport Line', 2021, 48200,
 'Diesel', 'Automatic', 'Black', 140, 4,
 28900, 'EUR', 28900,
 'https://www.autoscout24.de/angebote/bmw-320d-diesel-schwarz-seed-001', 'DE',
 'ACTIVE', 'MARKET_READY', 'dealer', 52.5200, 13.4050),

('01HVSEED000000000000000002', md5('seed-002'),
 'seed-002', 'SEED_DEMO', 'SCRAPER',
 'BMW', '5 Series', '520i Luxury', 2020, 61000,
 'Gasoline', 'Automatic', 'White', 135, 4,
 33500, 'EUR', 33500,
 'https://www.autoscout24.de/angebote/bmw-520i-benzin-weiss-seed-002', 'DE',
 'ACTIVE', 'MARKET_READY', 'dealer', 48.1351, 11.5820),

('01HVSEED000000000000000003', md5('seed-003'),
 'seed-003', 'SEED_DEMO', 'SCRAPER',
 'BMW', 'X3', 'xDrive20d', 2022, 22000,
 'Diesel', 'Automatic', 'Grey', 140, 5,
 41900, 'EUR', 41900,
 'https://www.mobile.de/fahrzeugboerse/bmw-x3-seed-003', 'DE',
 'ACTIVE', 'MARKET_READY', 'dealer', 53.5753, 10.0153),

-- Mercedes-Benz ---------------------------------------------------------------
('01HVSEED000000000000000004', md5('seed-004'),
 'seed-004', 'SEED_DEMO', 'SCRAPER',
 'Mercedes-Benz', 'C-Class', 'C220d AMG Line', 2021, 39800,
 'Diesel', 'Automatic', 'Silver', 143, 4,
 35900, 'EUR', 35900,
 'https://www.autoscout24.de/angebote/mercedes-c220d-silber-seed-004', 'DE',
 'ACTIVE', 'MARKET_READY', 'dealer', 51.2217, 6.7762),

('01HVSEED000000000000000005', md5('seed-005'),
 'seed-005', 'SEED_DEMO', 'SCRAPER',
 'Mercedes-Benz', 'E-Class', 'E300 Avantgarde', 2020, 55000,
 'Gasoline', 'Automatic', 'Blue', 190, 4,
 38500, 'EUR', 38500,
 'https://www.mobile.de/fahrzeugboerse/mercedes-e300-seed-005', 'DE',
 'ACTIVE', 'MARKET_READY', 'dealer', 50.1109, 8.6821),

-- Volkswagen ------------------------------------------------------------------
('01HVSEED000000000000000006', md5('seed-006'),
 'seed-006', 'SEED_DEMO', 'SCRAPER',
 'Volkswagen', 'Golf', 'GTI 2.0 TSI', 2022, 18500,
 'Gasoline', 'Manual', 'Red', 180, 5,
 32900, 'EUR', 32900,
 'https://www.autoscout24.de/angebote/vw-golf-gti-rot-seed-006', 'DE',
 'ACTIVE', 'MARKET_READY', 'private', 52.3759, 9.7320),

('01HVSEED000000000000000007', md5('seed-007'),
 'seed-007', 'SEED_DEMO', 'SCRAPER',
 'Volkswagen', 'Passat', 'TDI Business', 2021, 67000,
 'Diesel', 'Automatic', 'Black', 110, 4,
 22900, 'EUR', 22900,
 'https://www.mobile.de/fahrzeugboerse/vw-passat-tdi-seed-007', 'DE',
 'ACTIVE', 'MARKET_READY', 'dealer', 53.0793, 8.8017),

('01HVSEED000000000000000008', md5('seed-008'),
 'seed-008', 'SEED_DEMO', 'SCRAPER',
 'Volkswagen', 'ID.4', 'Pro Performance', 2023, 12000,
 'Electric', 'Automatic', 'White', 150, 5,
 42500, 'EUR', 42500,
 'https://www.autoscout24.de/angebote/vw-id4-pro-weiss-seed-008', 'DE',
 'ACTIVE', 'MARKET_READY', 'dealer', 51.0504, 13.7373),

-- Audi ------------------------------------------------------------------------
('01HVSEED000000000000000009', md5('seed-009'),
 'seed-009', 'SEED_DEMO', 'SCRAPER',
 'Audi', 'A4', '2.0 TDI S-Line', 2021, 43000,
 'Diesel', 'Automatic', 'Grey', 140, 4,
 31900, 'EUR', 31900,
 'https://www.autoscout24.de/angebote/audi-a4-tdi-grau-seed-009', 'DE',
 'ACTIVE', 'MARKET_READY', 'dealer', 49.4521, 11.0767),

('01HVSEED000000000000000010', md5('seed-010'),
 'seed-010', 'SEED_DEMO', 'SCRAPER',
 'Audi', 'Q5', '40 TDI quattro', 2022, 28000,
 'Diesel', 'Automatic', 'Silver', 150, 5,
 44900, 'EUR', 44900,
 'https://www.mobile.de/fahrzeugboerse/audi-q5-tdi-seed-010', 'DE',
 'ACTIVE', 'MARKET_READY', 'dealer', 48.7758, 9.1829),

-- Toyota ----------------------------------------------------------------------
('01HVSEED000000000000000011', md5('seed-011'),
 'seed-011', 'SEED_DEMO', 'SCRAPER',
 'Toyota', 'Corolla', '2.0 Hybrid', 2022, 21000,
 'Hybrid', 'Automatic', 'White', 112, 5,
 27500, 'EUR', 27500,
 'https://www.wallapop.com/coches/toyota-corolla-seed-011', 'ES',
 'ACTIVE', 'MARKET_READY', 'private', 40.4168, -3.7038),

('01HVSEED000000000000000012', md5('seed-012'),
 'seed-012', 'SEED_DEMO', 'SCRAPER',
 'Toyota', 'RAV4', 'Hybrid AWD', 2021, 34000,
 'Hybrid', 'Automatic', 'Black', 160, 5,
 35900, 'EUR', 35900,
 'https://www.coches.net/toyota/rav4/seed-012', 'ES',
 'ACTIVE', 'MARKET_READY', 'dealer', 41.3851, 2.1734),

-- Ford ------------------------------------------------------------------------
('01HVSEED000000000000000013', md5('seed-013'),
 'seed-013', 'SEED_DEMO', 'SCRAPER',
 'Ford', 'Focus', 'ST-Line 1.5 EcoBoost', 2021, 41000,
 'Gasoline', 'Manual', 'Blue', 110, 5,
 18900, 'EUR', 18900,
 'https://www.leboncoin.fr/voitures/ford-focus-st-seed-013', 'FR',
 'ACTIVE', 'MARKET_READY', 'private', 48.8566, 2.3522),

('01HVSEED000000000000000014', md5('seed-014'),
 'seed-014', 'SEED_DEMO', 'SCRAPER',
 'Ford', 'Mustang Mach-E', 'Extended Range RWD', 2022, 19000,
 'Electric', 'Automatic', 'Red', 198, 5,
 44900, 'EUR', 44900,
 'https://www.autoscout24.de/angebote/ford-mach-e-rot-seed-014', 'DE',
 'ACTIVE', 'MARKET_READY', 'dealer', 48.1351, 11.5820),

-- Renault ---------------------------------------------------------------------
('01HVSEED000000000000000015', md5('seed-015'),
 'seed-015', 'SEED_DEMO', 'SCRAPER',
 'Renault', 'Megane', 'E-Tech Electric', 2023, 8000,
 'Electric', 'Automatic', 'Grey', 160, 5,
 36900, 'EUR', 36900,
 'https://www.leboncoin.fr/voitures/renault-megane-etech-seed-015', 'FR',
 'ACTIVE', 'MARKET_READY', 'dealer', 45.7640, 4.8357),

('01HVSEED000000000000000016', md5('seed-016'),
 'seed-016', 'SEED_DEMO', 'SCRAPER',
 'Renault', 'Clio', '1.0 TCe Zen', 2022, 24000,
 'Gasoline', 'Manual', 'Orange', 66, 5,
 14500, 'EUR', 14500,
 'https://www.leboncoin.fr/voitures/renault-clio-seed-016', 'FR',
 'ACTIVE', 'MARKET_READY', 'private', 43.2965, 5.3813),

-- Peugeot ---------------------------------------------------------------------
('01HVSEED000000000000000017', md5('seed-017'),
 'seed-017', 'SEED_DEMO', 'SCRAPER',
 'Peugeot', '308', '1.5 BlueHDi Allure', 2022, 31000,
 'Diesel', 'Automatic', 'White', 96, 5,
 21900, 'EUR', 21900,
 'https://www.leboncoin.fr/voitures/peugeot-308-seed-017', 'FR',
 'ACTIVE', 'MARKET_READY', 'dealer', 48.5734, 7.7521),

-- SEAT / Cupra ----------------------------------------------------------------
('01HVSEED000000000000000018', md5('seed-018'),
 'seed-018', 'SEED_DEMO', 'SCRAPER',
 'SEAT', 'Leon', '1.5 TSI FR', 2022, 19000,
 'Gasoline', 'Manual', 'Blue', 110, 5,
 22900, 'EUR', 22900,
 'https://www.coches.net/seat/leon/seed-018', 'ES',
 'ACTIVE', 'MARKET_READY', 'dealer', 39.4699, -0.3763),

('01HVSEED000000000000000019', md5('seed-019'),
 'seed-019', 'SEED_DEMO', 'SCRAPER',
 'Cupra', 'Formentor', 'VZ 2.0 TSI 4Drive', 2022, 26000,
 'Gasoline', 'Automatic', 'Black', 228, 5,
 38900, 'EUR', 38900,
 'https://www.wallapop.com/coches/cupra-formentor-seed-019', 'ES',
 'ACTIVE', 'MARKET_READY', 'private', 41.6488, -0.8891),

-- Volvo -----------------------------------------------------------------------
('01HVSEED000000000000000020', md5('seed-020'),
 'seed-020', 'SEED_DEMO', 'SCRAPER',
 'Volvo', 'XC60', 'Recharge T6 AWD', 2022, 31000,
 'Hybrid', 'Automatic', 'Silver', 253, 5,
 47900, 'EUR', 47900,
 'https://www.marktplaats.nl/v/volvo/xc60/seed-020', 'NL',
 'ACTIVE', 'MARKET_READY', 'dealer', 52.3676, 4.9041),

-- Hyundai ---------------------------------------------------------------------
('01HVSEED000000000000000021', md5('seed-021'),
 'seed-021', 'SEED_DEMO', 'SCRAPER',
 'Hyundai', 'IONIQ 5', 'Long Range AWD', 2022, 25000,
 'Electric', 'Automatic', 'White', 225, 5,
 43900, 'EUR', 43900,
 'https://www.marktplaats.nl/v/hyundai/ioniq5/seed-021', 'NL',
 'ACTIVE', 'MARKET_READY', 'dealer', 51.9225, 4.4792),

-- Kia -------------------------------------------------------------------------
('01HVSEED000000000000000022', md5('seed-022'),
 'seed-022', 'SEED_DEMO', 'SCRAPER',
 'Kia', 'EV6', 'GT-Line AWD', 2022, 22000,
 'Electric', 'Automatic', 'Grey', 239, 5,
 42500, 'EUR', 42500,
 'https://www.autoscout24.de/angebote/kia-ev6-grau-seed-022', 'DE',
 'ACTIVE', 'MARKET_READY', 'dealer', 50.9333, 6.9500),

-- Skoda -----------------------------------------------------------------------
('01HVSEED000000000000000023', md5('seed-023'),
 'seed-023', 'SEED_DEMO', 'SCRAPER',
 'Skoda', 'Octavia', '2.0 TDI Style DSG', 2021, 52000,
 'Diesel', 'Automatic', 'Green', 110, 5,
 23900, 'EUR', 23900,
 'https://www.mobile.de/fahrzeugboerse/skoda-octavia-tdi-seed-023', 'DE',
 'ACTIVE', 'MARKET_READY', 'dealer', 51.3397, 12.3731),

-- Opel / Vauxhall -------------------------------------------------------------
('01HVSEED000000000000000024', md5('seed-024'),
 'seed-024', 'SEED_DEMO', 'SCRAPER',
 'Opel', 'Astra', '1.2 Turbo GS', 2023, 9500,
 'Gasoline', 'Automatic', 'Black', 96, 5,
 25900, 'EUR', 25900,
 'https://www.leboncoin.fr/voitures/opel-astra-gs-seed-024', 'FR',
 'ACTIVE', 'MARKET_READY', 'dealer', 47.2184, 1.5536),

-- Tesla -----------------------------------------------------------------------
('01HVSEED000000000000000025', md5('seed-025'),
 'seed-025', 'SEED_DEMO', 'SCRAPER',
 'Tesla', 'Model 3', 'Long Range AWD', 2022, 35000,
 'Electric', 'Automatic', 'White', 366, 4,
 39900, 'EUR', 39900,
 'https://www.marktplaats.nl/v/tesla/model3/seed-025', 'NL',
 'ACTIVE', 'MARKET_READY', 'private', 52.0907, 5.1214),

('01HVSEED000000000000000026', md5('seed-026'),
 'seed-026', 'SEED_DEMO', 'SCRAPER',
 'Tesla', 'Model Y', 'Performance', 2023, 18000,
 'Electric', 'Automatic', 'Red', 393, 5,
 54900, 'EUR', 54900,
 'https://www.autoscout24.de/angebote/tesla-model-y-perf-seed-026', 'DE',
 'ACTIVE', 'MARKET_READY', 'private', 52.5200, 13.4050),

-- Porsche ---------------------------------------------------------------------
('01HVSEED000000000000000027', md5('seed-027'),
 'seed-027', 'SEED_DEMO', 'SCRAPER',
 'Porsche', 'Cayenne', 'E-Hybrid', 2021, 41000,
 'Hybrid', 'Automatic', 'Silver', 340, 5,
 79900, 'EUR', 79900,
 'https://www.mobile.de/fahrzeugboerse/porsche-cayenne-hybrid-seed-027', 'DE',
 'ACTIVE', 'MARKET_READY', 'dealer', 49.4521, 11.0767),

-- Fiat ------------------------------------------------------------------------
('01HVSEED000000000000000028', md5('seed-028'),
 'seed-028', 'SEED_DEMO', 'SCRAPER',
 'Fiat', '500', '1.0 Hybrid Dolcevita', 2022, 15000,
 'Hybrid', 'Manual', 'Yellow', 51, 3,
 15900, 'EUR', 15900,
 'https://www.wallapop.com/coches/fiat-500-seed-028', 'ES',
 'ACTIVE', 'MARKET_READY', 'private', 41.9028, 12.4964),

-- Honda -----------------------------------------------------------------------
('01HVSEED000000000000000029', md5('seed-029'),
 'seed-029', 'SEED_DEMO', 'SCRAPER',
 'Honda', 'CR-V', 'e:HEV 4WD', 2023, 11000,
 'Hybrid', 'Automatic', 'Blue', 135, 5,
 43900, 'EUR', 43900,
 'https://www.marktplaats.nl/v/honda/crv/seed-029', 'NL',
 'ACTIVE', 'MARKET_READY', 'dealer', 51.5555, 5.0913),

-- Nissan ----------------------------------------------------------------------
('01HVSEED000000000000000030', md5('seed-030'),
 'seed-030', 'SEED_DEMO', 'SCRAPER',
 'Nissan', 'Leaf', 'e+ Tekna 62kWh', 2022, 28000,
 'Electric', 'Automatic', 'White', 160, 5,
 26900, 'EUR', 26900,
 'https://www.autoscout24.de/angebote/nissan-leaf-plus-seed-030', 'DE',
 'ACTIVE', 'MARKET_READY', 'private', 53.5753, 10.0153);
