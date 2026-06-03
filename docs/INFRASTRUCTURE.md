# Infrastructure Research — Cardex Scraping Platform

> European car-listing scraping (DE, FR, ES, NL, BE, CH) running on a VPS.
> All figures researched June 2026. Prices ex-VAT unless noted. USD figures are
> vendor list prices; EUR conversions use ~€1 = $1.08 and are marked `≈`.
> Every claim is tagged: **[V]** = read from a source below, **[M]** = vendor
> marketing claim (not independently verified), **[unverified]** = could not confirm.

---

## 1. VPS Comparison

All prices monthly, ex-VAT. "Shared" = contended vCPU; "Dedicated" = guaranteed cores.

| Provider | Example plan | Price/mo | vCPU | RAM | Disk | Traffic policy | EU DC locations | Scraping stance (AUP/ToS) | Caveats |
|---|---|---|---|---|---|---|---|---|---|
| **Hetzner** | CX22 (shared, Intel/AMD) | **€3.79** [V] | 2 | 4 GB | 40 GB NVMe | 20 TB incl., then €1.19/TB | DE (Falkenstein, Nuremberg), FI (Helsinki) | No explicit scraping ban found; system policies prohibit "misuse", crypto mining, and abuse [V]. DC IPs widely flagged by anti-bot vendors [V] | Datacenter ASN well-known to anti-bot; some sites (e.g. Cloudflare-era reports) block Hetzner ranges [V] |
| **Hetzner** | CPX22 (shared, AMD EPYC) | **€7.99** [V] (was €5.99 pre-Apr 2026) | 2 | 4 GB | 80 GB NVMe | 20 TB incl. | DE, FI | same as above | Price rose Apr 1 2026 [V] |
| **Hetzner** | CCX13 (dedicated AMD) | ~€12–13 [unverified exact] | 2 ded. | 8 GB | 80 GB | 20 TB incl. | DE, FI | same | Dedicated vCPU line; exact 2026 price unverified |
| **Contabo** | VPS 10 (NVMe) | **€4.50** [V] | 4 | 8 GB | NVMe (tiered) | Unmetered up to port speed (~32 TB fair-use typical) [M] | DE (multiple), UK, FR + global (11 locations) [V] | No explicit scraping clause found [unverified] | Heavily oversubscribed; variable performance; setup fee on some terms; DC IPs flagged |
| **Netcup** | VPS 1000 G11 | **≈€3.99** [V] | 2 (shared) | 8 GB | 256 GB SSD | 80 TB incl. typical [unverified exact] | DE (Nuremberg), AT (Vienna) | No explicit scraping ban surfaced [unverified] | German DC; strong value; |
| **Netcup** | RS 1000 G12 (root, dedicated) | **€8.74** [V] | 4 ded. (EPYC 9645) | 8 GB DDR5 ECC | 256 GB NVMe | high incl. | DE (Nuremberg), AT (Vienna) | same | Dedicated cores + ECC at low price [V] |
| **OVHcloud** | VPS-1 / Starter | **€3.99** [V] | 2 | 2 GB | 40 GB NVMe | Unlimited traffic (EU/NA) [V] | FR, DE, UK, PL (+ CA, AU) [V] | ToS bans port scans, sniffing, spoofing, Black-Hat SEO; scraping not named explicitly [V] | ~30% price hike on VPS-1 post-2026 [V]; anti-DDoS included |
| **DigitalOcean** | Basic Droplet | **$4** ≈€3.70 [V] | 1 | 512 MB–1 GB | 10–25 GB SSD | 0.5–1 TB incl., $0.01/GB over | Amsterdam (AMS3), Frankfurt (FRA1) [V] | **Explicitly bans scraping**: prohibits "harvesting or scraping of any content of the Services" and "spidering, and harvesting" [V] | AUP language is the most restrictive of the set [V] |
| **Vultr** | Cloud Compute 1 GB | **$5** ≈€4.60 [V] (IPv6-only $2.50) | 1 | 1 GB | 25 GB SSD | 1 TB incl., bandwidth pools across account [V] | Frankfurt, Amsterdam, Paris, London, etc. (32 locations) [V] | AUP restricts abuse; scraping not explicitly named [unverified] | New VX1 line (Oct 2025) cheaper perf/$ [V] |
| **Linode/Akamai** | Nanode / Shared 1 GB | **$5** ≈€4.60 [V] | 1 | 1 GB | 25 GB SSD | 1 TB incl. (generous tiers) [V] | Frankfurt, Amsterdam, London, Paris, Stockholm, Milan [V] | AUP restricts abuse; scraping not explicitly named [unverified] | Owned by Akamai (anti-bot vendor) — note conflict-of-interest optics, no functional impact [V] |
| **Oracle Cloud** | Always Free Ampere A1 | **€0** [V] | up to 4 (Arm) | 24 GB | up to 200 GB block | 10 TB egress/mo free | Amsterdam, Frankfurt, Marseille, Zurich, etc. [V] | Free-tier ToS restricts abuse; capacity not guaranteed [V] | **Ampere A1 capacity almost always "out of capacity"** in EU free regions; reliable only on Pay-As-You-Go [V] |

### Recommendation

**Primary: Hetzner CCX-line (dedicated) or CPX22 for the orchestrator + Camoufox workers.**

- For a **single production worker box**: **Hetzner CPX22 — 2 vCPU / 4 GB / 80 GB NVMe / 20 TB traffic at €7.99/mo** [V]. Reason: best-in-class EU price/performance, generous 20 TB included traffic (Camoufox + proxy traffic is RAM/CPU-bound, not egress-bound, so 20 TB is ample), German/Finnish DCs close to all six target countries, and a clean AUP with **no explicit scraping prohibition** [V].
- If headless Camoufox concurrency matters (Firefox forks are RAM-hungry, ~200 MB+ per context [M]), step up to **CCX13 (dedicated 2 vCPU / 8 GB)** so browser contexts don't contend for CPU. Exact 2026 CCX price is **[unverified]** — confirm in console.
- **Netcup RS 1000 G12 (€8.74, 4 dedicated EPYC 9645 cores, 8 GB DDR5 ECC, NVMe)** is the strongest dedicated-core alternative [V] — more raw cores than Hetzner CCX13 at a similar price, German DC. Good fallback / second region.
- **Budget floor**: Contabo VPS 10 (€4.50, 4 vCPU / 8 GB) gives the most RAM-per-euro for parallel browsers, but oversubscription means inconsistent latency and DC IPs are flagged — acceptable only because we route scraping through proxies, not the VPS IP.

**Avoid for the scraping egress path:**
- **DigitalOcean** — its AUP **explicitly prohibits scraping/harvesting** [V]. Usable for control-plane/API hosting, not for issuing scrape requests from the droplet IP.
- **Oracle free tier** — Ampere A1 EU capacity is effectively unobtainable on free accounts [V]; do not architect around it.

**Sources:**
- https://www.hetzner.com/cloud/regular-performance
- https://www.hetzner.com/pressroom/new-cx-plans/
- https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/
- https://www.hetzner.com/legal/system-policies/
- https://contabo.com/en/pricing/
- https://contabo.com/en/locations/europe/
- https://www.netcup.com/en/server/vps
- https://netcupvoucher.com/blog/netcup-root-server-g12-is-out
- https://www.ovhcloud.com/en/vps/
- https://us.ovhcloud.com/legal/terms-of-service/
- https://www.digitalocean.com/legal/acceptable-use-policy
- https://www.vultr.com/pricing/
- https://www.vultr.com/products/vx1-compute/
- https://betterstack.com/community/guides/web-servers/linode-akamai-review/
- https://www.oracle.com/cloud/free/
- https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm

---

## 2. Proxy Providers (paid only — free proxies out of scope)

Two tiers matter for this project:
- **ISP / static residential** (sticky IP, datacenter-speed, real-ISP ASN) → best for **T1/T2** sites with light-to-moderate anti-bot.
- **Rotating residential** (per-GB, huge pool) → best for **T3** sites behind DataDome/Akamai.

### 2a. ISP / static residential

| Provider | Price | Pool / coverage | Mgmt API | Notes |
|---|---|---|---|---|
| **Decodo (ex-Smartproxy)** | ISP from **$0.35/IP** (min 10) up to ~$3.33/IP/mo; shared-ISP also billed per-GB [V] | ISP pool published per-country incl. DE/FR/ES/NL; CH/BE coverage **[unverified]** | Yes [M] | Exclusive (private-history) IPs available; flexible billing models [V] |
| **IPRoyal** | ISP (static residential) from **$2.40/IP/mo** (90-day) / $1.80 (24h); unlimited traffic per IP [V] | 500K+ ISP IPs across 31+ countries [V]; per-country DE/FR/ES/NL/BE/CH split **[unverified]** | Yes [M] | SOCKS5 supported; non-expiring residential GB on the rotating product is a standout [V] |
| **NetNut** | Static residential (ISP) tiered: ~$17.5/GB entry → $2.49/GB (800 GB) → enterprise ~$1.08–1.59/GB [V] | **1M+ static-ISP IPs** (one of the largest) [V]; per-country split **[unverified]** | Yes [M] | No PAYG; monthly bandwidth commit required [V]; ISP billed per-GB not per-IP |

### 2b. Rotating residential + mobile

| Provider | Price/GB (PAYG → volume) | Pool size | Per-country DE/FR/ES/NL/BE/CH | Success vs DataDome/Akamai | Mgmt API |
|---|---|---|---|---|---|
| **Bright Data** | **$5.04/GB PAYG → $3.50 (Growth) → ~$2.00 enterprise** [M] | **150M+ IPs / 195 countries** (largest) [M] | All six published in dashboard [M]; exact CH/BE counts **[unverified]** | Vendor: 97–99% general [M]. Independent: strongest on DataDome/Akamai targets via Web Unlocker; "failed attempts free" on protected sites [M] | Yes — full API [M] |
| **Oxylabs** | **~$8/GB PAYG → $7.5 (Starter) → $3.5 enterprise** [M] | **175M+ IPs / 195 countries** [M] | All six published [M]; CH/BE counts **[unverified]** | **Independent (Proxyway 2025): 85.82% on hard anti-bot targets; struggled on G2/DataDome** [V]. Vendor general claim 99.95% [M] | Yes [M] |
| **SOAX** | **$4/GB PAYG → $3.40–3.60 (Starter/Adv) → $0.32 enterprise**; mobile from $4.50/GB [V/M] | 155M+ residential, 191M+ total incl. mobile/ISP/DC; 195 countries [M] | All proxy types share one pool; per-country DE/FR/ES/NL **[unverified]**, CH/BE **[unverified]** | Vendor "clean/whitelisted IPs" [M]; independent DataDome figure **[unverified]** | Yes [M] |
| **IPRoyal** | **$7/GB (1 GB) → $1.75/GB bulk**; non-expiring traffic [V] | ~32M residential IPs / 195+ countries [V] | DE/FR/ES/NL covered [M]; CH/BE **[unverified]** | Independent DataDome/Akamai figure **[unverified]**; generally rated mid-tier on hard targets | Yes [M] |
| **Mobile** (Bright Data / SOAX / IPRoyal) | Mobile typically **$4.50–$9/GB** depending on vendor [V partial] | 4G/5G carrier IPs; smallest pools, highest trust | per-country mobile counts **[unverified]** | Highest trust score vs DataDome (carrier-grade NAT IPs) [M] | Yes [M] |

### Recommendation

- **ISP-sticky (T1/T2): IPRoyal ISP at $2.40/IP/mo with unlimited per-IP traffic** [V]. Reason: flat per-IP cost with **unlimited bandwidth** removes per-GB metering anxiety for high-volume T1/T2 polling, SOCKS5 support, and 31+ countries cover the targets. **Decodo ISP ($0.35/IP entry)** is the cheaper alternative if you need many disposable IPs and can accept per-GB on the shared pool [V]. Buy a small block per target country, pin sticky sessions, rotate only on block.
- **Residential-rotating (T3): Bright Data** as primary [M], because the only independently-corroborated edge on **DataDome/Akamai-protected** car portals (AutoScout24 = Akamai [V]; many classifieds = DataDome [V]) comes from its larger pool + Web Unlocker, and its "no charge on failed protected requests" model caps T3 cost risk [M]. **Oxylabs is explicitly second-choice for T3**: a 2025 independent Proxyway benchmark measured only **85.82% on hard anti-bot targets and called out DataDome/G2 as a weakness** [V] — so do not make Oxylabs the DataDome workhorse. **SOAX** is the value pick if Bright Data's price is prohibitive ($4/GB PAYG, single pool for residential+mobile+ISP) [V], but its DataDome success rate is **[unverified]** — pilot before committing.
- **Mobile**: reserve for the hardest DataDome targets only (highest €/GB); carrier IPs carry the best trust scores [M].

> **Marketing vs independent caveat:** pool sizes (150M/175M/191M) and "99%+ success" are **vendor marketing [M]**. The only independent success figure found is Oxylabs 85.82% on hard targets (Proxyway 2025) [V]. Treat all other success rates as unproven until piloted against the actual target portals.

**Sources:**
- https://oxylabs.io/pricing/residential-proxy-pool
- https://oxylabs.io/pricing/isp-proxies
- https://proxyway.com/reviews/oxylabs-proxies
- https://proxyway.com/research/web-scraping-api-report-2025
- https://brightdata.com/pricing/proxy-network/residential-proxies
- https://decodo.com/proxies/isp-proxies/pricing
- https://decodo.com/proxies/static-residential-proxies
- https://iproyal.com/pricing/residential-proxies/
- https://use-apify.com/blog/iproyal-pricing-plans-2026
- https://netnut.io/
- https://proxyway.com/reviews/netnut-proxies
- https://soax.com/pricing
- https://soax.com/proxies

---

## 3. CAPTCHA Solvers

Prices per 1,000 solves. Support and latency are largely vendor-stated **[M]** unless noted.

| Solver | Image/text | reCAPTCHA v2 | reCAPTCHA v3/Enterprise | hCaptcha | CF Turnstile | DataDome | Latency | Success (claim) |
|---|---|---|---|---|---|---|---|---|
| **CapSolver** | $0.40 [V] | ~$0.8–1.0 [M] | $3.0 (v3 Enterprise) [V] | supported [V] | **$1.2** [V] | supported [V] | sub-second [M] | 99%+ [M] |
| **2Captcha** | $0.50–1.00 [V] | ~$2.99 [V] | $5.00+ [V] | ~$2.99 [V] | supported [M] | supported (premium) [M] | slower (human-assisted, ~tens of s for reCAPTCHA) [V] | high [M] |
| **Anti-Captcha** | $0.50 [V] | $1.0 [V] | higher tier [M] | supported [M] | supported [M] | supported [M] | moderate [M] | high [M] |
| **NopeCHA** | $0.40 [V] | $1.00 [V] | multi-credit (2–6 credits on risky IPs) [V] | supported [V] | supported [V] | AWS WAF/FunCaptcha/GeeTest too [V] | ~1.5 s reCAPTCHA [M] | "27× cheaper, 17× faster" — **vendor benchmark [M]** |

**Notes / which portals actually show CAPTCHAs:**
- The dominant defense on EU car portals is **continuous anti-bot scoring (Akamai on AutoScout24; DataDome on many classifieds), not interactive CAPTCHA** [V]. DataDome typically surfaces a **device-check / slider challenge** only when its trust score drops, and **DataDome's slider is not reliably solvable by generic reCAPTCHA/hCaptcha solvers** — CapSolver lists DataDome support [V] but real-world DataDome bypass is driven by **proxy quality + browser fingerprint**, not a solver call. [V]
- Therefore CAPTCHA solving here is a **fallback**, not the primary mechanism. Budget for it as overflow.
- **Recommendation: CapSolver as primary** (broadest modern-type coverage incl. Turnstile at $1.2/1k, AI-based, sub-second) [V], with **NopeCHA as the cheap secondary** for reCAPTCHA/Turnstile volume ($0.40 image / $1.00 reCAPTCHA, free ~100/day to pilot) [V]. Keep 2Captcha/Anti-Captcha only if a target needs human-assisted solving.

**Sources:**
- https://docs.capsolver.com/en/pricing/
- https://docs.capsolver.com/en/guide/captcha/cloudflare_turnstile/
- https://2captcha.com/
- https://anti-captcha.com/
- https://nopecha.com/pricing
- https://developers.nopecha.com/
- https://scrapfly.io/blog/posts/how-to-bypass-datadome-anti-scraping
- https://aimultiple.com/captcha-solving-services

---

## 4. Browser Anti-Detect

| Tool | Open-source / self-host | Headless-on-VPS suitable | Engine / approach | 2025–2026 anti-fingerprint quality |
|---|---|---|---|---|
| **Camoufox** (daijro) | **Yes — MPL, fully self-hostable** [V] | **Yes — built for headless at scale** [V] | Firefox fork patched at **C++ level**; fingerprint spoofing without JS injection; Playwright agent sandboxed [V] | **0% headless detection** (changes happen before JS can inspect); engine-level canvas hashes match real Firefox; beat Patchright on DataDome in one 2026 test [V]. TLS has a Firefox shape — detectable but **whitelisted** on many targets that block Chrome automation [V] |
| **Playwright + stealth / Patchright** | Yes — OSS | Yes | Chromium patched at JS/CDP level | Patchright ~67% headless-detection reduction (JS-level), weaker than engine-level; canvas-hash sites still catch JS overrides [V]. `nodriver` scored best-in-class (0 blocked) in a 2026 31-target benchmark [V] |
| **GoLogin** | No — proprietary; cloud + desktop | Has cloud/Linux + API, but **GUI-centric**; no built-in proxies [V] | Chromium-based profile manager | Mid-tier fingerprinting; "occasional detection issues reported" [V] |
| **Multilogin** | No — proprietary, **GUI desktop app** | **Poor fit for headless VPS** (desktop-first) [V] | Advanced fingerprint engine + bundled residential proxies (30M+) [M] | Rated strongest GUI antidetect, but licensing + GUI model make it wrong for autonomous headless scraping [V] |
| **AdsPower** | No — proprietary, **GUI desktop app** | **Poor fit for headless VPS** [V] | Chromium profiles + RPA recorder | Affordable, Asia-popular, automation RPA; still GUI/profile-oriented, no proxies bundled [V] |

### Conclusion

**Yes — Camoufox (github.com/daijro/camoufox) is the correct T2/T3 pillar for a headless VPS.** Reasons:
1. **It is open-source and self-hostable** — no per-profile licensing, no GUI dependency, runs headless on a Linux VPS by design [V]. Multilogin and AdsPower are GUI desktop products and are **structurally unsuitable** for an autonomous VPS pipeline [V]. GoLogin is closer but proprietary, GUI-centric, and brings no proxies [V].
2. **Engine-level (C++) fingerprint spoofing** defeats canvas-hash and JS-inspection detectors that catch Playwright/Patchright's JS-level overrides; independent 2025–2026 tests measured **0% headless detection** and showed Camoufox passing DataDome/Google gates where Chromium stealth and even Patchright failed [V].
3. **Native Playwright control** with a sandboxed agent — fits a programmatic scraping engine cleanly [V].

Caveats to plan for: Camoufox's **Firefox-shaped TLS is detectable** (mitigated by it being whitelisted on many anti-Chrome targets) [V]; the upstream repo had a **maintainer hiatus (daijro hospitalized since Mar 2025), with @coryking maintaining a Firefox 142 fork** — pin a known-good build and watch maintenance status [V]. Pair Camoufox with good residential/ISP proxies (Section 2); fingerprint alone does not beat DataDome's IP + behavior scoring [V].

**Sources:**
- https://github.com/daijro/camoufox
- https://camoufox.com/stealth/
- https://github.com/techinz/browsers-benchmark
- https://ianlpaterson.com/blog/anti-detect-browser-benchmark-patchright-nodriver-curl-cffi/
- https://bytetunnels.com/posts/playwright-vs-camoufox-stealth-automation-head-to-head/
- https://www.proxies.sx/blog/ai-browser-automation-camoufox-nodriver-2026
- https://multilogin.com/blog/multilogin-vs-gologin-vs-adspower/
- https://oxylabs.io/blog/gologin-vs-adspower

---

## 5. DNS / Domain + Reverse DNS (PTR)

**Short answer: a forward domain + matching PTR on the VPS IP has negligible effect on scraping success, because scrape traffic should not originate from the VPS IP at all — it goes through proxies (Section 2).** Where it matters:

| Factor | Effect on scraping reputation |
|---|---|
| PTR reveals hosting/datacenter ASN | A datacenter PTR (e.g. `static.xxx.clients.your-server.de`) **confirms** the IP is a datacenter, which anti-bot systems already infer from the ASN. Adding a clean PTR does **not** launder a datacenter IP into a residential-looking one [V]. |
| Generic vs custom PTR | Generic/auto PTR patterns are used by spam filters and anti-bot heuristics to flag non-residential sources [V]. Mainly relevant to **email deliverability**, not HTTP scraping. |
| Forward+reverse match (FCrDNS) | Improves **outbound email** reputation and looks tidy in audits; **no measurable HTTP-scraping benefit** because target anti-bot relies on TLS/JS/behavior + IP-ASN, not on whether your origin IP has a PTR [V]. |

**Practical guidance:** set a clean custom PTR + A record on the VPS only for **operational hygiene** (monitoring, outbound notification email, not landing in spam). Do **not** expect it to improve scrape pass rates — that is determined by proxy IP quality and browser fingerprint. [V]

**Sources:**
- https://support.dnsimple.com/articles/reverse-dns-ptr-records/
- https://www.cloudns.net/blog/reverse-dns-ptr-record/
- https://emailwarmup.com/blog/ptr-record/
- https://www.vergecloud.com/blog/the-complete-guide-to-reverse-dns-lookup/

---

## 6. Monthly Cost Table

Two scenarios. Proxy/CAPTCHA volumes are **assumptions** — tune to real traffic.

### Minimum viable (single box, light volume)

| Item | Choice | Monthly (EUR) |
|---|---|---|
| VPS | Hetzner CPX22 (2 vCPU / 4 GB / 20 TB) | €7.99 [V] |
| ISP proxies (T1/T2) | IPRoyal ISP, 5 IPs × $2.40 ≈ €11 [V] | ≈€11 |
| Residential rotating (T3) | SOAX PAYG ~10 GB × $4/GB ≈ €37 [V] | ≈€37 |
| CAPTCHA fallback | NopeCHA, ~5k reCAPTCHA × $1/1k ≈ €4.6 [V] | ≈€5 |
| Domain + DNS | ~€1/mo amortized | ≈€1 |
| **Total** | | **≈ €62/mo** |

### Optimal (dedicated cores, hard-target volume, DataDome-grade)

| Item | Choice | Monthly (EUR) |
|---|---|---|
| VPS | Hetzner CCX13 dedicated (2 ded / 8 GB) — exact price **[unverified]**, est. | ≈€13 |
| (or) 2nd region | Netcup RS 1000 G12 (4 ded EPYC / 8 GB) | €8.74 [V] |
| ISP proxies (T1/T2) | IPRoyal ISP, 15 IPs × $2.40 ≈ €33 [V] | ≈€33 |
| Residential rotating (T3) | Bright Data ~50 GB @ ~$3.50/GB (Growth) ≈ €162 [M] | ≈€162 |
| Mobile (hardest DataDome) | ~5 GB @ ~$6/GB ≈ €28 [partial V] | ≈€28 |
| CAPTCHA | CapSolver, ~20k mixed (Turnstile $1.2 + reCAPTCHA) ≈ €25 [V] | ≈€25 |
| Domain + DNS + monitoring | | ≈€3 |
| **Total (single region)** | | **≈ €264/mo** |
| **Total (+ Netcup 2nd region)** | | **≈ €273/mo** |

> Dominant cost is **residential-rotating GB for T3 DataDome/Akamai targets**, not compute. Drive total cost down by maximizing T1/T2 coverage on flat-rate ISP proxies and reserving per-GB residential/mobile strictly for sites that actually challenge. Bright Data's "free on failed protected requests" model [M] is the main lever to cap T3 overruns.

**Sources:**
- https://www.hetzner.com/cloud/regular-performance
- https://netcupvoucher.com/blog/netcup-root-server-g12-is-out
- https://iproyal.com/pricing/
- https://soax.com/pricing
- https://brightdata.com/pricing/proxy-network/residential-proxies
- https://docs.capsolver.com/en/pricing/
- https://nopecha.com/pricing
