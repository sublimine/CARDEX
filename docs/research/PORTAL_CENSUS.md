# CARDEX Portal Census — Ground Truth Coverage Tracker

> Last updated: 2026-06-04 (Phase 9 coverage gap closure)
> Total implemented scrapers: **58**
> Total portals tracked: **90+**

---

## Legend

| Status | Meaning |
|--------|---------|
| LIVE | Scraper implemented, registered, tested |
| BLOCKED | Known portal, too hard to scrape (T2/T3 WAF) — in domain_map only |
| SKIP-AGGREGATOR | Meta-search / aggregator duplicating other sources |
| SKIP-OEM | Manufacturer site, not a classifieds portal |
| SKIP-REBRAND | Rebranded / merged into another portal |
| SKIP-SMALL | Too few listings to justify implementation |
| SKIP-NEWONLY | Only new cars, no used inventory |
| DEAD | Domain dead, redirects, or no longer has classifieds |

| Tier | Meaning |
|------|---------|
| T0 | Open JSON/mobile API — no anti-bot |
| T1 | curl_cffi chrome136 — no browser needed |
| T2 | Camoufox + storageState + _abck — stealth browser |
| T3 | Camoufox + Oxymouse behavioral + CapSolver + residential proxy |

---

## Germany (DE)

| Domain | Status | Tier | WAF | Phase | Est. Inventory | Notes |
|--------|--------|------|-----|-------|---------------|-------|
| autoscout24.de | LIVE | T2 | Akamai V3 | 1 | ~2M | Pan-European leader, Akamai protected |
| mobile.de | LIVE | T2 | Akamai V3 | 2 | ~1.4M | Largest DE portal, eBay Motors group |
| kleinanzeigen.de | LIVE | T2 | Akamai V3 | 2 | ~500k | General classifieds, strong auto section |
| autoboerse.de | LIVE | T1 | None | 6 | ~250k | Santander Consumer Bank dealer network |
| carvago.com | LIVE | T1 | None | 6 | ~1.07M | Pan-European aggregator, Next.js CSR |
| auto.de | LIVE | T1 | None | 7 | ~50k | WordPress-based, UUID vehicle IDs |
| pkw.de | LIVE | T1 | Unknown | 8 | ~100k | Multi-dealer SSR marketplace |
| autohaus24.de | LIVE | T1 | Unknown | 8 | ~1k | Allane SE (ex-Sixt Leasing) dealer |
| autohus.de | LIVE | T1 | Unknown | 8 | ~3k | DAT AUTOHUS AG, used car specialist |
| autohero.com | BLOCKED | T2 | CF Pro | — | ~15k | Auto1 Group, Cloudflare Pro |
| heycar.de | SKIP-AGGREGATOR | — | — | — | — | Aggregator (VW Group), pulls from dealers |
| wirkaufendeinauto.de | SKIP-OEM | — | — | — | — | Buy-only service (Auto1 Group), no listings |
| autode.de | DEAD | — | — | — | — | Redirects to auto.de |
| gebrauchtwagen.de | SKIP-REBRAND | — | — | — | — | Redirects to mobile.de |
| automobile.de | SKIP-AGGREGATOR | — | — | — | — | AutoScout24 subsidiary, subset data |

## France (FR)

| Domain | Status | Tier | WAF | Phase | Est. Inventory | Notes |
|--------|--------|------|-----|-------|---------------|-------|
| autoscout24.fr | LIVE | T2 | Akamai V3 | 1 | ~400k | Pan-European, Akamai |
| leboncoin.fr | LIVE | T3 | DataDome | 2 | ~800k | Largest FR classifieds, DataDome |
| lacentrale.fr | LIVE | T3 | DataDome | 2 | ~500k | Premium FR auto portal, DataDome |
| paruvendu.fr | LIVE | T1 | None | 3 | ~30k | General classifieds, auto section |
| largus.fr | LIVE | T1 | None | 3 | ~20k | Auto media + classifieds |
| aramisauto.com | LIVE | T1 | CF Free | 6 | ~3k | Online-only dealer, Stellantis group |
| leparking.fr | LIVE | T1 | None | 6 | ~14.8M | Meta-aggregator SSR, massive index |
| autosphere.fr | LIVE | T0 | None | 6 | ~15.6k | PSA/Stellantis network, REST API |
| reezocar.com | LIVE | T1 | None | 6 | ~200k | Pan-European aggregator |
| spoticar.fr | LIVE | T1 | CF Free | 6 | ~80k | Stellantis VO network |
| auto-selection.com | LIVE | T0 | None | 6 | ~113k | Meilisearch public API |
| annonces-automobile.com | LIVE | T1 | None | 6 | ~43k | SSR HTML jQuery classifieds |
| starterre.fr | LIVE | T1 | None | 6 | ~7.3k | Mandataire (broker) |
| carizy.com | LIVE | T1 | None | 6 | ~1.2k | P2P car sales platform |
| capcar.fr | LIVE | T1 | Unknown | 7 | ~2k | P2P with 350+ inspection agents |
| occasions.jeanlain.com | LIVE | T1 | Unknown | 8 | ~1.8k | Jean Lain Mobilités, Alpine arc dealer |
| gueudet.fr | LIVE | T1 | None | 9 | ~5.2k | Gueudet 1880 dealer group, SSR HTML |
| distinxion.fr | LIVE | T1 | None | 9 | ~1.6k | 120+ POS multi-brand network, Symfony SSR |
| ouestfrance-auto.fr | BLOCKED | T2 | CF Pro | — | ~50k | Ouest-France media group |
| zoomcar.fr | BLOCKED | T2 | CF Pro | — | ~50k | Ex-ouestfrance-auto.com rebrand |
| promoneuve.fr | SKIP-NEWONLY | T3 | DataDome | — | — | New cars only, DataDome |
| vinceauto.com | SKIP-SMALL | — | — | — | — | Too small, regional dealer |
| kyump.com | SKIP-SMALL | — | — | — | — | Niche startup, negligible inventory |
| changermonauto.fr | SKIP-SMALL | — | — | — | — | Small broker, <500 listings |
| caroom.fr | SKIP-AGGREGATOR | — | — | — | — | Price comparison, no direct listings |
| elite-auto.fr | SKIP-SMALL | — | — | — | — | Mandataire, mostly new cars |

## Spain (ES)

| Domain | Status | Tier | WAF | Phase | Est. Inventory | Notes |
|--------|--------|------|-----|-------|---------------|-------|
| autoscout24.es | LIVE | T2 | Akamai V3 | 1 | ~200k | Pan-European, Akamai |
| coches.net | LIVE | T1→T2 | None | 2 | ~300k | Largest ES auto portal, can escalate T2 |
| motor.es | LIVE | T1 | None | 3 | ~100k | Vocento media group |
| autocasion.com | LIVE | T1 | CF Free | 3 | ~80k | Prisa Motor Group |
| ocasionplus.com | LIVE | T1 | None | 6 | ~20k | Multi-location used car dealer |
| flexicar.es | LIVE | T1 | Unknown | 7 | ~25k | Growing VO chain |
| clicars.com | LIVE | T1 | Unknown | 7 | ~2k | Online-first used car dealer |
| buscocoches.com | LIVE | T1 | Unknown | 8 | ~15k | National classifieds |
| wallapop.com | BLOCKED | T2 | PerimeterX | — | ~200k | General classifieds, PerimeterX |
| milanuncios.com | BLOCKED | T3 | DataDome | — | ~150k | Major classifieds, DataDome |
| coches.com | BLOCKED | T2 | CF Pro | — | ~50k | Adevinta group |
| motorflash.com | SKIP-AGGREGATOR | — | — | — | — | B2B dealer SaaS, not consumer portal |
| km77.com | SKIP-OEM | — | — | — | — | Auto media, reviews only |
| cochesya.com | SKIP-SMALL | — | — | — | — | Tiny classified board |
| vibbo.com | DEAD | — | — | — | — | Shut down, merged into wallapop |

## Netherlands (NL)

| Domain | Status | Tier | WAF | Phase | Est. Inventory | Notes |
|--------|--------|------|-----|-------|---------------|-------|
| autoscout24.nl | LIVE | T2 | Akamai V3 | 1 | ~300k | Pan-European, Akamai |
| marktplaats.nl | LIVE | T0 | None | 2 | ~200k | Largest NL classifieds, open LRP API |
| autotrack.nl | LIVE | T1 | None | 3 | ~100k | RDC partner portal |
| gaspedaal.nl | LIVE | T1 | None | 3 | ~150k | Meta-search across NL portals |
| viabovag.nl | LIVE | T1 | None | 5 | ~50k | BOVAG dealer network, Next.js SSR |
| autokopen.nl | LIVE | T1 | None | 6 | ~106k | Next.js SSR portal |
| nederlandmobiel.nl | LIVE | T0 | None | 6 | ~313k | PHP SSR free platform |
| autowereld.nl | LIVE | T1 | Unknown | 7 | ~270k | PHP SSR occasions portal |
| autoweek.nl | BLOCKED | T2 | Akamai V3 | — | ~50k | Automotive media + classifieds |
| autovisie.nl | SKIP-OEM | — | — | — | — | Auto media, reviews only |
| autobytel.nl | DEAD | — | — | — | — | Domain parked |
| wijkopenautos.nl | SKIP-OEM | — | — | — | — | Buy-only service, no listings |

## Belgium (BE)

| Domain | Status | Tier | WAF | Phase | Est. Inventory | Notes |
|--------|--------|------|-----|-------|---------------|-------|
| autoscout24.be | LIVE | T2 | Akamai V3 | 1 | ~200k | Pan-European, Akamai |
| 2dehands.be | LIVE | T0 | None | 5 | ~80k | Largest BE classifieds (NL), open LRP API |
| tweedehands.be | LIVE | T0 | None | 5 | alias | Alias of 2dehands.be |
| 2ememain.be | LIVE | T0 | None | 6 | ~80k | FR mirror of 2dehands.be, same LRP API |
| cardoen.be | LIVE | T1 | CF Free | 6 | ~850 | Major multi-brand dealer chain |
| moniteurautomobile.be | LIVE | T1 | None | 6 | ~120k | Le Moniteur Automobile media classifieds |
| deuxememain.be | LIVE | T0 | None | 6 | alias | Redirects to 2ememain.be |
| youcar.be | LIVE | T1 | Unknown | 7 | ~5k | Multi-brand NL/FR/EN |
| myway.be | LIVE | T1 | Unknown | 7 | ~3k | D'Ieteren certified used cars |
| belgiemobiel.be | LIVE | T1 | None | 8 | ~20k | PHP SSR, sister of nederlandmobiel.nl |
| vroom.be | LIVE | T1 | Unknown | 8 | ~40k | Rossel/Roularta JV media portal |
| gocar.be | BLOCKED | T2 | CF Business | — | ~30k | Cloudflare Business, premium portal |
| kapaza.be | DEAD | — | — | — | — | Merged into 2dehands.be |
| autovlan.be | SKIP-REBRAND | — | — | — | — | Merged into vroom.be |
| topoccasions.be | SKIP-SMALL | — | — | — | — | Tiny portal, negligible inventory |

## Switzerland (CH)

| Domain | Status | Tier | WAF | Phase | Est. Inventory | Notes |
|--------|--------|------|-----|-------|---------------|-------|
| autoscout24.ch | LIVE | T2 | Akamai V3 | 1 | ~150k | Pan-European, Akamai |
| tutti.ch | LIVE | T1 | CF Free | 5 | ~15k | General classifieds, Scout24 backend |
| anibis.ch | LIVE | T1 | CF Free | 5 | ~10k | FR twin of tutti.ch |
| autolina.ch | LIVE | T0 | None | 5 | ~30k | Open REST API, m.autolina.ch |
| carforyou.ch | LIVE | T1 | Unknown | 8 | ~20k | #3 CH auto portal, ~966k visits/mo |
| gowago.ch | LIVE | T1 | None | 9 | ~10k | Swiss leasing marketplace, Next.js SSR |
| comparis.ch | BLOCKED | T2 | CF Business | — | ~100k | Insurance/comparison giant, CF Business |
| autoricardo.ch | SKIP-REBRAND | — | — | — | — | Merged into autoscout24.ch |
| car4you.ch | SKIP-REBRAND | — | — | — | — | Old domain → carforyou.ch |
| autogalerie.ch | SKIP-SMALL | — | — | — | — | Tiny dealer portal |

## Cross-border / Pan-European

| Domain | Status | Tier | WAF | Phase | Est. Inventory | Notes |
|--------|--------|------|-----|-------|---------------|-------|
| carvago.com | LIVE | T1 | None | 6 | ~1.07M | CZ-based, EU-wide aggregator |
| reezocar.com | LIVE | T1 | None | 6 | ~200k | FR-based EU aggregator |
| leparking.fr | LIVE | T1 | None | 6 | ~14.8M | FR-based meta-aggregator |

---

## Summary by Country

| Country | LIVE | BLOCKED | SKIP/DEAD | Total Tracked |
|---------|------|---------|-----------|---------------|
| DE | 9 | 1 | 4 | 14 |
| FR | 18 | 2 | 6 | 26 |
| ES | 8 | 3 | 4 | 15 |
| NL | 8 | 1 | 3 | 12 |
| BE | 11 | 1 | 3 | 15 |
| CH | 6 | 1 | 3 | 10 |
| EU | 3 | 0 | 0 | 3 |
| **Total** | **58** | **9** | **23** | **90** |

## Summary by Phase

| Phase | Portals Added | Cumulative LIVE |
|-------|--------------|-----------------|
| 1 — AutoScout24 family | 6 (DE/FR/ES/NL/BE/CH) | 6 |
| 2 — Major portals | 6 (mobile.de, marktplaats, leboncoin, kleinanzeigen, coches.net, lacentrale) | 12 |
| 3 — Secondary portals | 6 (paruvendu, largus, autotrack, gaspedaal, motor.es, autocasion) | 18 |
| 5 — CH/BE/NL expansion | 5 (2dehands, tweedehands, viabovag, tutti, anibis, autolina) | 23 |
| 6 — ES/NL/DE/FR/BE expansion | 17 (ocasionplus, autokopen, nederlandmobiel, autoboerse, carvago, 2ememain, cardoen, aramis, leparking, autosphere, reezocar, spoticar, auto-selection, annonces-automobile, starterre, carizy, moniteur) | 40 |
| 7 — Remaining T0/T1 | 7 (flexicar, clicars, autowereld, auto.de, youcar, myway, capcar) | 47 |
| 8 — Deep sweep | 8 (pkw.de, autohaus24, autohus, buscocoches, belgiemobiel, vroom.be, carforyou, jeanlain) | 55 |
| 9 — Coverage gap closure | 3 (gowago.ch, gueudet.fr, distinxion.fr) | 58 |

## Summary by Tier

| Tier | Count | Description |
|------|-------|-------------|
| T0 | 8 | Open API / no WAF |
| T1 | 36 | curl_cffi sufficient |
| T2 | 10 | Stealth browser required |
| T3 | 4 | Behavioral + DataDome |
| **Total** | **58** | |

---

## Phase 8 Research — Portals Investigated but NOT Implemented

### DE — Investigated & Excluded

- **heycar.de** — SKIP-AGGREGATOR. Volkswagen Financial Services subsidiary. Aggregates dealer inventory; no unique data beyond what autoscout24/mobile.de already provide.
- **wirkaufendeinauto.de** — SKIP-OEM. Auto1 Group buy-only service. No public inventory to scrape.
- **gebrauchtwagen.de** — DEAD/REBRAND. Redirects to mobile.de.
- **automobile.de** — SKIP-AGGREGATOR. AutoScout24 subsidiary targeting premium segment; subset of AS24 data.
- **autode.de** — DEAD. Domain redirects to auto.de.

### FR — Investigated & Excluded

- **promoneuve.fr** — SKIP-NEWONLY. DataDome-protected, only new car listings. No used vehicle inventory.
- **caroom.fr** — SKIP-AGGREGATOR. Price comparison tool, no direct listings.
- **elite-auto.fr** — SKIP-SMALL. Mandataire focused on new cars with minimal used inventory.
- **vinceauto.com** — SKIP-SMALL. Regional dealer, too small.
- **kyump.com** — SKIP-SMALL. Niche startup, negligible inventory.
- **changermonauto.fr** — SKIP-SMALL. Small broker under 500 listings.
- **zoomcar.fr** — BLOCKED (T2, CF Pro). Rebrand of ouestfrance-auto.com.

### ES — Investigated & Excluded

- **wallapop.com** — BLOCKED (T2, PerimeterX). General classifieds with strong auto section; PerimeterX makes T1 impossible.
- **milanuncios.com** — BLOCKED (T3, DataDome). Major classifieds; DataDome enforcement.
- **motorflash.com** — SKIP-AGGREGATOR. B2B dealer SaaS platform, not a consumer-facing portal.
- **km77.com** — SKIP-OEM. Auto journalism/reviews, no classifieds.
- **cochesya.com** — SKIP-SMALL. Tiny board.
- **vibbo.com** — DEAD. Shut down and merged into wallapop.

### NL — Investigated & Excluded

- **autoweek.nl** — BLOCKED (T2, Akamai V3). Automotive media with classifieds; Akamai makes T1 impossible.
- **autovisie.nl** — SKIP-OEM. Auto media, reviews only.
- **autobytel.nl** — DEAD. Domain parked.
- **wijkopenautos.nl** — SKIP-OEM. Buy-only service (like wirkaufendeinauto.de).

### BE — Investigated & Excluded

- **gocar.be** — BLOCKED (T2, CF Business). Premium Belgian portal; Cloudflare Business tier.
- **kapaza.be** — DEAD. Fully merged into 2dehands.be years ago.
- **autovlan.be** — SKIP-REBRAND. Merged into vroom.be by Rossel Group.
- **topoccasions.be** — SKIP-SMALL. Negligible inventory.

### CH — Investigated & Excluded

- **comparis.ch** — BLOCKED (T2, CF Business). Swiss comparison giant; Cloudflare Business.
- **autoricardo.ch** — SKIP-REBRAND. Merged into autoscout24.ch.
- **car4you.ch** — SKIP-REBRAND. Old domain, now carforyou.ch.
- **autogalerie.ch** — SKIP-SMALL. Tiny dealer portal.

---

## Phase 9 Research — Portals Investigated but NOT Implemented

### DE — Investigated & Excluded (Phase 9)

- **meinauto.de** — SKIP-NEWONLY. Neuwagen-Konfigurator; only new car configurations, no used inventory.
- **pkw-center.de** — SKIP-SMALL. Regional dealer group, fewer than 200 listings.
- **autohaus.de** — SKIP-OEM. B2B automotive industry news portal, no consumer classifieds.
- **hey.car** (heycar.de) — SKIP-AGGREGATOR. VW Group aggregator pulling from dealer DMS systems; no unique inventory.

### FR — Investigated & Excluded (Phase 9)

- **gueudet.fr** — LIVE (implemented). Gueudet 1880 dealer group, 5.2k VO, SSR HTML.
- **distinxion.fr** — LIVE (implemented). 120+ point-of-sale network, 1.6k VO, Symfony SSR.
- **bymycar.fr** — SKIP-SMALL. Regional dealer group, ~800 VO scattered across sub-sites.
- **autojm.fr** — SKIP-SMALL. Mandataire with minimal used inventory, focus on new.
- **ewigo.com** — SKIP-SMALL. Franchise network, listings fragmented per agency, no central listing page.
- **claar.fr** — DEAD. Domain parked / under construction.
- **paruvendu-auto.fr** — SKIP-REBRAND. Redirects to paruvendu.fr main domain.

### ES — Investigated & Excluded (Phase 9)

- **drivek.es** — SKIP-NEWONLY. Configurator for new cars only.
- **canalcar.com** — DEAD. Domain parked.
- **segundamano.es** — DEAD. Redirected to vibbo, which merged into wallapop.
- **compramostucoche.es** — SKIP-OEM. Buy-only service, no public listings.

### NL — Investigated & Excluded (Phase 9)

- **ikwilvanmijnautoaf.nl** — SKIP-OEM. Buy-only service (Autohero NL).
- **automatch.nl** — SKIP-AGGREGATOR. Price comparison tool, no direct listings.
- **autokopen.com** — SKIP-REBRAND. Redirects to autokopen.nl.

### BE — Investigated & Excluded (Phase 9)

- **autovlan.be** — Already tracked as SKIP-REBRAND (merged into vroom.be).
- **automarket.be** — DEAD. Domain parked.
- **autodoccasion.be** — SKIP-SMALL. Fewer than 100 listings.

### CH — Investigated & Excluded (Phase 9)

- **gowago.ch** — LIVE (implemented). Swiss leasing marketplace, ~10k used cars, Next.js SSR.
- **autosprint.ch** — SKIP-SMALL. Tiny dealer portal, fewer than 50 listings.
- **carmarket.ch** — DEAD. Domain inactive / no classifieds.
- **occasionauto.ch** — SKIP-REBRAND. Redirects to comparis.ch.

### Pan-European / CPO — Investigated & Excluded (Phase 9)

- **carwow.de/fr/es** — SKIP-AGGREGATOR. YouTube-centric car buying platform; no scrapable classifieds index.
- **kavak.com** — SKIP-SMALL. LatAm unicorn with minimal EU footprint (~Turkey only in EU region).
- **BMW Premium Selection** — SKIP-OEM. Manufacturer CPO program, listings on dealer sites only.
- **Mercedes Certified** — SKIP-OEM. Manufacturer CPO program, no central listing index.
- **Volkswagen Das WeltAuto** — SKIP-OEM. Manufacturer CPO via dealer sites, no scrapable central index.
- **Audi Approved :plus** — SKIP-OEM. Manufacturer CPO, dealer-distributed.
- **Volvo Selekt** — SKIP-OEM. Manufacturer CPO, dealer-distributed.

## Coverage Assessment

**Estimated total addressable used car inventory across 6 countries: ~6M+ listings**

With 58 implemented scrapers covering T0-T2 tiers, the estimated coverage by accessible listing volume:

| Country | Estimated Accessible | Total Market Est. | Coverage |
|---------|---------------------|-------------------|----------|
| DE | ~4.5M | ~5M | ~90% |
| FR | ~1.61M | ~2M | ~80.5% |
| ES | ~700k | ~1M | ~70% |
| NL | ~1.2M | ~1.3M | ~92% |
| BE | ~550k | ~650k | ~85% |
| CH | ~235k | ~350k | ~67% |

Remaining gaps are primarily behind T2/T3 WAFs (autohero, gocar, comparis, wallapop, milanuncios, autoweek) which require Camoufox browser infrastructure.

**Phase 9 conclusion**: All remaining T0/T1 portals with meaningful used-car inventory have been implemented. Further coverage gains require T2/T3 browser infrastructure.

---

*This document is the ground truth for portal coverage tracking. Update after each phase.*
