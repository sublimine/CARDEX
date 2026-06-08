"""
Evaluate the is-car-dealer decision: heuristic-alone vs LLM-assisted, on a REAL
labelled sample of live homepages. Measures precision/recall/accuracy, the number
of LLM calls actually made (cost), and per-call latency + host RAM.

    python -m scripts.eval_llm_classifier            # full live run (fetches homepages)

Labels are hand-curated from prior empirical evidence (GUARDIAN audits):
  * dealers: domains verified to yield real car inventory / from dedicated dealer
    registries (BOVAG/AGVS/OEM).
  * non-dealers: the known false positives the heuristic-only gate let through
    (art collection, opticians, audio brand, butcher, driving school, museum…).
Unreachable hosts are excluded from the metrics and reported separately — nothing
is invented.
"""
from __future__ import annotations

import sys
import time

# (name, city, domain, label)  label: 1 = real car dealer, 0 = NOT a car dealer
SAMPLE: list[tuple[str, str, str, int]] = [
    # ── real car dealers (label 1) ──
    ("Dacia Meaux", "Meaux", "dacia-meaux.fr", 1),
    ("Nissan Epernay", "Epernay", "nissan-epernay.fr", 1),
    ("Mercedes-Benz Compiegne", "Compiegne", "mercedes-benz-compiegne.fr", 1),
    ("Garage Mosch", "Eiken", "garage-moesch.ch", 1),
    ("Auto Inderbitzin AG", "Oberarth", "auto-inderbitzin.ch", 1),
    ("Auto Huiskes", "Schaijk", "autohuiskes.nl", 1),
    ("Van der Vaart Autos", "Elst", "vandervaartautos.nl", 1),
    ("Autobedrijf van Gorkum", "Dronten", "advg.nl", 1),
    ("Emil Frey", "Safenwil", "emilfrey.ch", 1),
    ("Autohaus Ostmann", "Goettingen", "autohaus-ostmann.de", 1),
    # ── NOT car dealers (label 0) — the FP types the heuristic-only gate let pass ──
    ("Artcar", "Zurich", "bmwartcarcollection.com", 0),   # BMW art-car collection / museum
    ("AP Optik", "Berlin", "ap-optik.de", 0),             # optician
    ("Audiovalve", "Zurich", "audiovalve.info", 0),       # hi-fi tube amplifiers
    ("Swiss Optik", "Schaffhausen", "swiss-optik.ch", 0), # optician (incident FP)
    ("Fahrschule Marty", "Zurich", "fahrschule-marty.ch", 0),  # driving school (incident FP)
    ("Boucherie Erard", "Geneve", "boucherie-erard.ch", 0),    # butcher (incident FP)
    # ── target-FP TYPES the user named: motorcycle / tyre / body shops the heuristic
    #    accepted into discovery_candidates (real resolved rows) but that do NOT sell cars
    ("Riviera Motorcycles", "Montreux", "rivieramotorcycles.ch", 0),  # motorcycle dealer
    ("Manu Motos", "Geneve", "manu-motos.ch", 0),                     # motorcycle shop
    ("Pneu Treier", "Aarau", "pneu-treier.ch", 0),                    # tyre shop
    ("Carrosserie Palmieri", "Lausanne", "carrosserie-palmieri.ch", 0),  # body/paint shop
    ("AMAG Solothurn", "Solothurn", "solothurn.amag.ch", 1),         # real car dealer (AMAG group)
]


def _fetch(domain: str, timeout: float = 12.0) -> tuple[str | None, str]:
    """Fetch https://domain/ via curl_cffi (Strategy-B impersonation). (html, note)."""
    from curl_cffi import requests as cffi

    for scheme in ("https", "http"):
        try:
            r = cffi.get(f"{scheme}://{domain}/", impersonate="chrome", timeout=timeout,
                         allow_redirects=True, verify=False)
        except Exception as exc:  # noqa: BLE001
            last = f"{type(exc).__name__}"
            continue
        if r.status_code and r.status_code < 400 and r.text:
            return r.text, f"{scheme}:{r.status_code}"
        last = f"{scheme}:{r.status_code}"
    return None, last


def _metrics(b: dict) -> str:
    tp, fp, tn, fn = b["tp"], b["fp"], b["tn"], b["fn"]
    prec = tp / (tp + fp) if (tp + fp) else float("nan")
    rec = tp / (tp + fn) if (tp + fn) else float("nan")
    acc = (tp + tn) / (tp + fp + tn + fn) if (tp + fp + tn + fn) else float("nan")
    return (f"precision={prec:.3f} recall={rec:.3f} accuracy={acc:.3f} "
            f"(tp={tp} fp={fp} tn={tn} fn={fn})")


def main() -> int:
    from scrapers.discovery.domain_resolution.validate import confirms_dealer
    from scrapers.llm import decisions as d
    from scrapers.llm.ollama_client import get_client

    cl = get_client()
    print(f"ollama available={cl.available()} model_present={cl.model_present()} model={cl.model}")

    # Fetch every homepage ONCE (cache) so both modes score identical inputs.
    pages: list[tuple[str, str, str, int, str]] = []   # (name,city,domain,label,html)
    unreachable: list[str] = []
    for name, city, domain, label in SAMPLE:
        html, note = _fetch(domain)
        if html is None:
            unreachable.append(f"{domain} ({note})")
        else:
            pages.append((name, city, domain, label, html))
    print(f"fetched {len(pages)}/{len(SAMPLE)} (unreachable: {len(unreachable)})")

    # Warm the model so the first real call isn't a ~25s cold load skewing latency.
    if cl.available():
        cl.generate_json("Reply with {\"ok\":true}", schema={"type": "object"}, max_tokens=10)

    # heuristic-only confusion (mode-independent)
    h = {"tp": 0, "fp": 0, "tn": 0, "fn": 0}
    for name, city, _dom, label, html in pages:
        ok, _ = confirms_dealer(html, name, city, require_name=False)
        _tally(h, ok, label)
    print(f"\nheuristic-only : {_metrics(h)}")

    for mode in ("economy", "precision"):
        m = {"tp": 0, "fp": 0, "tn": 0, "fn": 0}
        calls, lats, flips = 0, [], []
        for name, city, domain, label, html in pages:
            t0 = time.perf_counter()
            v = d.classify_is_car_dealer(html, name, city, require_name=False, client=cl, mode=mode)
            dt = time.perf_counter() - t0
            if v.consulted_llm:
                calls += 1
                lats.append(dt)
            _tally(m, v.is_dealer, label)
            ok, _ = confirms_dealer(html, name, city, require_name=False)
            if v.is_dealer != ok:
                flips.append(f"{domain}:{ok}->{v.is_dealer}({v.kind or v.source})")
        lat = (f"avg={sum(lats)/len(lats):.1f}s max={max(lats):.1f}s" if lats else "n/a")
        print(f"llm [{mode:9}]: {_metrics(m)}  | llm_calls={calls} lat={lat}")
        if flips:
            print(f"            flips: {', '.join(flips)}")

    if unreachable:
        print("\nunreachable    : " + "; ".join(unreachable))
    return 0


def _tally(box: dict, pred: bool, label: int) -> None:
    if pred and label == 1:
        box["tp"] += 1
    elif pred and label == 0:
        box["fp"] += 1
    elif (not pred) and label == 0:
        box["tn"] += 1
    else:
        box["fn"] += 1


if __name__ == "__main__":
    sys.exit(main())
