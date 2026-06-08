-- 0001_source_entities.backfill.sql
-- Populate source_entities and link existing inventory. Idempotent (md5-deterministic
-- ids + ON CONFLICT DO NOTHING + WHERE entity_ulid IS NULL). Re-runnable safely.

BEGIN;

-- 1) Platform source-entities from the live deep-link index (one per source_domain).
INSERT INTO source_entities (entity_ulid, source_key, kind, domain, country)
SELECT 'se_'||md5(d.source_domain), d.source_domain, 'platform', d.source_domain, d.country
FROM (
  SELECT source_domain,
         (array_agg(country ORDER BY (country <> '') DESC))[1] AS country
  FROM vehicle_index
  WHERE source_domain IS NOT NULL AND source_domain <> ''
  GROUP BY source_domain
) d
ON CONFLICT (source_key) DO NOTHING;

-- 2) Dealer source-entities from rich vehicles (one per source_platform).
INSERT INTO source_entities (entity_ulid, source_key, kind, domain, country)
SELECT 'se_'||md5(v.source_platform), v.source_platform, 'dealer', v.source_platform,
       (array_agg(v.source_country ORDER BY (v.source_country IS NOT NULL) DESC))[1]
FROM vehicles v
WHERE v.source_platform IS NOT NULL AND v.source_platform <> ''
GROUP BY v.source_platform
ON CONFLICT (source_key) DO NOTHING;

-- 3) T1 giants — entities ready even at 0 inventory (defense from domain_map snapshot, audit §C).
INSERT INTO source_entities (entity_ulid, source_key, kind, domain, country, defense_tier, waf) VALUES
  ('se_'||md5('mobile.de'),        'mobile.de',        'platform','mobile.de',       'DE','T1','akamai_v3'),
  ('se_'||md5('kleinanzeigen.de'), 'kleinanzeigen.de', 'platform','kleinanzeigen.de','DE','T1','akamai_v3'),
  ('se_'||md5('autoscout24.de'),   'autoscout24.de',   'platform','autoscout24.de',  'DE','T1','akamai_v3'),
  ('se_'||md5('leboncoin.fr'),     'leboncoin.fr',     'platform','leboncoin.fr',    'FR','T1','datadome'),
  ('se_'||md5('lacentrale.fr'),    'lacentrale.fr',    'platform','lacentrale.fr',   'FR','T1','datadome'),
  ('se_'||md5('coches.net'),       'coches.net',       'platform','coches.net',      'ES','T1','none')
ON CONFLICT (source_key) DO UPDATE SET defense_tier = EXCLUDED.defense_tier, waf = EXCLUDED.waf;

-- 4) Link inventory -> entity (deterministic; only rows not yet linked).
UPDATE vehicle_index SET entity_ulid = 'se_'||md5(source_domain)
  WHERE entity_ulid IS NULL AND source_domain IS NOT NULL AND source_domain <> '';
UPDATE vehicles SET entity_ulid = 'se_'||md5(source_platform)
  WHERE entity_ulid IS NULL AND source_platform IS NOT NULL AND source_platform <> '';

-- 5) Defense tier/waf for the 19 harvesting platforms (T2 = relevant inventory, no deep block;
--    waf from live probe 2026-06-08 where verified, else domain_map label).
UPDATE source_entities s SET defense_tier = 'T2', waf = m.waf FROM (VALUES
  ('autolina.ch','none'),      ('tutti.ch','cf_free'),     ('viabovag.nl','none'),
  ('gaspedaal.nl','blocked_403'), ('anibis.ch','cf_free'), ('autohero.com','none'),
  ('vroom.be','cf_cdn'),       ('autotrack.nl','blocked_403'), ('ocasionplus.com','none'),
  ('simplicicar.com','none'),  ('marktplaats.nl','none'),  ('comparis.ch','none'),
  ('distinxion.fr','none'),    ('paruvendu.fr','none'),    ('2ememain.be','none'),
  ('2dehands.be','none'),      ('clicars.com','cf_cdn'),   ('gowago.ch','none'),
  ('occasions.jeanlain.com','unknown')
) AS m(key,waf) WHERE s.source_key = m.key;

-- 6) config_ref where a versioned config file exists in the main worktree (configs/portals).
UPDATE source_entities SET config_ref = 'configs/portals/'||source_key||'.json'
  WHERE source_key IN ('autolina.ch','autotrack.nl','viabovag.nl');

-- 7) Dealer defense_tier from the real P2 probe (discovery_candidates.inventory_tier).
UPDATE source_entities s SET defense_tier = dc.inventory_tier
FROM discovery_candidates dc
WHERE s.kind = 'dealer' AND dc.domain = s.source_key
  AND dc.inventory_tier IN ('T1','T2','T3');

-- 8) Validate FKs now that every row is linked (turns NOT VALID -> VALID).
ALTER TABLE vehicle_index VALIDATE CONSTRAINT fk_vi_source_entity;
ALTER TABLE vehicles      VALIDATE CONSTRAINT fk_veh_source_entity;

COMMIT;

ANALYZE source_entities;
ANALYZE vehicle_index;
ANALYZE vehicles;
