"""
Free proxy pool — own IP rotation, no paid service.

Fetches public free-proxy lists (proxyscrape, geonode free tier — no API key), validates
each concurrently against a real target, and serves the live ones for rotation. Free
proxies are mostly dead/slow, so validation is aggressive and the pool is meant to be
refreshed often. Validation can target an arbitrary URL so we can measure, with HARD
evidence, whether a proxy actually bypasses a specific block (e.g. PagesJaunes DataDome)
rather than just "is alive".

RAM-safe: bounded concurrency, bounded sample, short timeouts. No DB, no side effects.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

log = logging.getLogger("proxy_pool")

# Free, keyless list endpoints. proxyscrape v4 returns ip:port text.
_SOURCES: dict[str, str] = {
    "proxyscrape_http": "https://api.proxyscrape.com/v4/free-proxy-list/get?request=display_proxies&protocol=http&proxy_format=ipport&format=text&timeout=2000",
    "proxyscrape_socks5": "https://api.proxyscrape.com/v4/free-proxy-list/get?request=display_proxies&protocol=socks5&proxy_format=ipport&format=text&timeout=2000",
    "geonode": "https://proxylist.geonode.com/api/proxy-list?limit=500&page=1&sort_by=lastChecked&sort_type=desc",
}


@dataclass
class Proxy:
    scheme: str          # http | socks5
    addr: str            # ip:port
    latency_ms: int = 0

    @property
    def url(self) -> str:
        return f"{self.scheme}://{self.addr}"


@dataclass
class PoolStats:
    fetched: int = 0
    tested: int = 0
    live: int = 0
    by_source: dict = field(default_factory=dict)


async def fetch_lists(session) -> list[Proxy]:
    """Pull raw proxies from all free sources (deduped). Never raises."""
    import json

    seen: set[str] = set()
    out: list[Proxy] = []
    for name, url in _SOURCES.items():
        try:
            r = await session.get(url, timeout=20)
            body = r.text or ""
        except Exception as exc:  # noqa: BLE001
            log.debug("proxy source %s failed: %s", name, type(exc).__name__)
            continue
        if name == "geonode":
            try:
                for row in json.loads(body).get("data", []):
                    ip, port = row.get("ip"), row.get("port")
                    protos = [p.lower() for p in (row.get("protocols") or [])]
                    scheme = "socks5" if "socks5" in protos else "http"
                    if ip and port and f"{ip}:{port}" not in seen:
                        seen.add(f"{ip}:{port}")
                        out.append(Proxy(scheme, f"{ip}:{port}"))
            except Exception:  # noqa: BLE001
                continue
        else:
            scheme = "socks5" if "socks5" in name else "http"
            for line in body.splitlines():
                ap = line.strip()
                if ap and ":" in ap and ap not in seen:
                    seen.add(ap)
                    out.append(Proxy(scheme, ap))
    return out


async def _check(proxy: Proxy, target: str, ok_status: tuple[int, ...], timeout: float) -> bool:
    """True if a request through ``proxy`` to ``target`` returns an acceptable status."""
    import curl_cffi.requests as cr

    t0 = time.monotonic()
    try:
        async with cr.AsyncSession(impersonate="chrome", timeout=timeout) as s:
            r = await s.get(target, proxies={"http": proxy.url, "https": proxy.url},
                            allow_redirects=True)
        if int(getattr(r, "status_code", 0) or 0) in ok_status:
            proxy.latency_ms = int((time.monotonic() - t0) * 1000)
            return True
    except Exception:  # noqa: BLE001 — dead/slow proxy = not live
        return False
    return False


async def validate(
    proxies: list[Proxy], *, target: str, ok_status: tuple[int, ...] = (200,),
    concurrency: int = 50, timeout: float = 8.0, sample: int = 0,
) -> tuple[list[Proxy], PoolStats]:
    """
    Validate proxies against ``target`` concurrently; return the live ones (sorted by
    latency). ``ok_status`` lets us demand a real 200 from a blocked site (hard
    evidence of bypass), not just connectivity. ``sample`` caps how many are tested.
    """
    stats = PoolStats(fetched=len(proxies))
    pool = proxies[:sample] if sample else proxies
    sem = asyncio.Semaphore(concurrency)
    live: list[Proxy] = []

    async def _one(p: Proxy) -> None:
        async with sem:
            stats.tested += 1
            if await _check(p, target, ok_status, timeout):
                live.append(p)
                stats.by_source[p.scheme] = stats.by_source.get(p.scheme, 0) + 1

    await asyncio.gather(*(_one(p) for p in pool))
    stats.live = len(live)
    live.sort(key=lambda p: p.latency_ms)
    return live, stats


class RotatingPool:
    """
    Self-refreshing pool of free proxies VALIDATED against a target (e.g. PagesJaunes).

    Hands out live proxies round-robin; a caller marks one dead on failure. When the
    live set falls below ``floor`` it refetches lists and re-validates against the same
    target, so the pool keeps itself topped up as free proxies die. Validation against
    the real blocked target is the point — only proxies proven to return 200 there are
    served (hard evidence of bypass, not mere liveness).
    """

    def __init__(self, *, target: str, ok_status: tuple[int, ...] = (200,),
                 floor: int = 4, sample: int = 700, timeout: float = 12.0):
        self._target = target
        self._ok = ok_status
        self._floor = floor
        self._sample = sample
        self._timeout = timeout
        self._live: list[Proxy] = []
        self._i = 0
        self.refreshes = 0

    @property
    def size(self) -> int:
        return len(self._live)

    async def refresh(self, session) -> int:
        """Refetch lists + re-validate against the target; replace the live set."""
        raw = await fetch_lists(session)
        live, st = await validate(raw, target=self._target, ok_status=self._ok,
                                  concurrency=80, timeout=self._timeout, sample=self._sample)
        self._live = live
        self._i = 0
        self.refreshes += 1
        log.info("proxy pool refresh #%d: %d live vs target (tested %d)",
                 self.refreshes, st.live, st.tested)
        return st.live

    async def ensure(self, session) -> int:
        if self.size < self._floor:
            return await self.refresh(session)
        return self.size

    def get(self) -> Proxy | None:
        if not self._live:
            return None
        p = self._live[self._i % len(self._live)]
        self._i += 1
        return p

    def mark_dead(self, proxy: Proxy) -> None:
        self._live = [p for p in self._live if p.addr != proxy.addr]
