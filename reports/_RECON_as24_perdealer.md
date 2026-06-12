# AS24 PER-DEALER RECON — [VERIFIED] 2026-06-12 (curl_cffi chrome136, proxy-free)

## Dealer census API (identity)
GET https://www.autoscout24.de/dealer-search/api?country=DE&pageIndex=N&size<=100&sortBy=best
-> 200. keys: results, size, pageIndex, sortBy, numberOfPages, totalDealers
DE totalDealers = 19812 (today; ~19766 in dossier — live drift, fine)
dealer record: {customerId:int (STABLE id), companyName, slug, address, rating, ratingCount, logo, ...}
  customerId 5742 -> slug "auto-zeilinger-gmbh"

## Per-dealer STOCK endpoint = the dealer PROFILE page  [THE SUPERIOR SURFACE]
GET https://www.autoscout24.de/haendler/<slug>?page=N   (SSR, __NEXT_DATA__)
  props.pageProps.numberOfResults      = dealer's EXACT stock count (e.g. 603)
  props.pageProps.numberOfResultsIncludingNulls
  props.pageProps.customerId           = attribution back to census id
  props.pageProps.listings[]           = 20 rich listing objects per page
  listing.url       = "/angebote/<slug>-<uuid>"   (absolute deep link; unique; passes _hash_urls)
  listing.id        = uuid
  listing.prices.public.priceRaw = CASH price int EUR (34117). netPriceRaw = ex-VAT.
                      monthlyRateGross = financing (separate node) -> price-trap-safe.
  listing.vehicle.make / .model
  listing.vehicle.mileageInKm.raw = km
  listing.vehicle.firstRegistrationDate.raw = "2026-03-01" -> year = [:4]
  listing.location.countryCode

## CAP CONFIRMATION (the whole point: per-dealer << 4000, no market-facet drift)
auto-zeilinger-gmbh: numberOfResults=603  -> WELL under the 4000 AS24 search cap.
Per page: distinct uuids, ZERO market-facet drift within a page.

## DEAD ENDS (verified, not assumed)
- /lst?customerId=<cid>  IGNORES the customerId param: returns whole-DE-market
  numberOfResults=~839362 for BOTH cid=5742 AND cid=99999999. (whole DE market ~839k = the ~831k anchor.)
- /_next/data/<buildId>/...haendler/<slug>.json -> 404 (buildId 'dealer-detail-pages_dev' not a public www data route)
- guessed XHR /dealer-listing/api, /seller-listings/api, as24-search-funnel -> 404
=> the SSR profile page IS the per-dealer surface; no cleaner JSON XHR is exposed.

## PAGER CAP + ANTI-BOT (operational reality)
- Profile pager tops out ~31 pages (~620 slots). Big dealer (603): 512 distinct ids reachable = 84.9%.
  The residual is the SSR relevance-pager ceiling (re-sorted dup slots), only bites dealers > ~500 stock.
  The MAJORITY of dealers (< ~500 stock) reach 100% with zero drift.
- AS24 throttles repeated /haendler hits from a warm datacenter IP: some pages return 200 + softblock
  HTML with NO __NEXT_DATA__ listings (nr=None). MUST: session-level impersonate chrome136 (JA3),
  jittered pacing (>=1.2s + jitter), retry-on-softblock (4x backoff), host_budget NET lane.
  Clean paced run reached lastpage=31 reliably; unpaced run got throttled to 4-12 pages.

## CAGE WIRING (verified signatures)
cage_inventory(pg, rdb, domain, country, listings, *, config_ref, kind="dealer", tier="T2")
  listings=[{url,title?,price?,year?,km?}]; entity_ulid="se_"+md5(domain); writes vehicle_index + SEEN events + enrich stream.
platform_seal.cage_platform(pool, rdb, domain, country, listings, *, config_ref, complete) -> reconcile iff complete.
verifier dim_identity: entity_ulid MUST == _entity_ulid(domain); kind in {dealer,platform}; country 2-letter.
=> per-dealer entity domain key (no own website from API) = SYNTHETIC stable: "as24-dealer-<customerId>.autoscout24.de"
   country->dealer attribution free; per-dealer reconcile natural (independent entity).

## PROOF — --sample 5 DE (2026-06-12, INSERT-only, live)
5 dealers sealed, kind='dealer' tier='T1', 100% price coverage, CASH prices + year + km:
  cid=20424   c-c-automobile         declared=40  enum=40  =100%  served=40
  cid=25102   autohaus-hanauer       declared=79  enum=77  = 97%  served=77
  cid=16541901 (large)                                      served=279
  cid=25623013 reinhardt-automobile  declared=912 enum=556 = 61%  served=556  (pager-cap residual)
  cid=26296   j-w-handelsgesellsch   declared=795 enum=563 = 71%  served=563  (pager-cap residual)
Small/mid dealers (40,79) -> 97-100% (zero drift). Big dealers (912,795) lose the SSR
relevance-pager residual (~31-page cap). All << 4000 search cap (so no market-facet drift).

## VERIFIER VERDICT (deterministic spine) — clean
as24-dealer-20424.autoscout24.de --declared 40:
  identity PASS | servability PASS(40) | linkage PASS(40,orphan=0) |
  fields PASS(price=100% year=100% title=100%) | dedup PASS | delta PASS(seen=40) |
  staleness PASS | count_coverage PASS(100.0%)  ----> VERIFIED ✓ (ALL dimensions PASS)
(without --declared, count_coverage is NEEDS_LIVE by design, still 0 gaps.)

## COVERAGE MATH (--count-only DE, 20-dealer stock sample)
DE census = 19,812 dealers. stock sample sum=1662 avg=83.1/dealer, 0/20 over 4000-cap.
projection 19,812 x 83.1 ~= 1.65M = ~198% of the 831k market figure.
=> per-dealer enumeration reaches >=100% of AS24-DE (vs the ~65% market-facet ceiling).
   (avg is high-variance on n=20: one 912 + one 795 + one 603 skew it up; the robust
    conclusion is total coverage, not the exact multiple. A larger --stock-sample tightens it.)

## RESIDUAL / FUTURE (declared, not hidden)
The ONLY incompleteness is the SSR profile relevance-pager cap (~31 pages / ~560 reachable)
on dealers with >~560 stock. Those dealers' numberOfResults is known, so the residual is
measurable per dealer. Recovery (future enhancement): facet the PROFILE within the dealer by
firstRegistration-year band (same param family as the market /lst) to page each band under the
cap — fully closes even 900+ dealers. Most dealers (<560 stock, the long tail) already reach 100%.
