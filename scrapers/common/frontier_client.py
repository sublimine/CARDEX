"""
Frontier client — reads crawl priorities from Redis, set by the frontier service.

The frontier service computes priority scores for each (platform, country, make, year) shard
based on: information gain (coverage gaps), economic value, freshness, demand, and Thompson Sampling.

Scrapers read these priorities to reorder their crawl shards — high-priority first.
If the frontier service is not running or Redis keys are empty, scrapers fall back to
the original ALL_MAKES × YEARS blind iteration.

Additionally, scrapers report crawl results back to Redis for Thompson Sampling updates:
how many NEW listings each shard produced.
"""
from __future__ import annotations

from typing import Any

import structlog

log = structlog.get_logger()


class FrontierClient:
    """Reads crawl priorities from Redis sorted sets published by the frontier service."""

    def __init__(self, redis_client: Any, platform: str, country: str) -> None:
        self._redis = redis_client
        self._platform = platform
        self._country = country
        self._key = f"frontier:priorities:{platform}"
        self._result_key = f"frontier:results:{platform}:{country}"

    async def get_ordered_shards(self) -> list[tuple[str, int, float]]:
        """
        Return [(make, year, priority_score)] ordered by priority descending.

        If the frontier service hasn't published priorities (key doesn't exist
        or is empty), returns an empty list. The caller should fall back to
        the default shard iteration.
        """
        try:
            # ZREVRANGE returns members from highest to lowest score
            results = await self._redis.zrevrange(
                self._key, 0, -1, withscores=True
            )
            if not results:
                return []

            shards = []
            for member, score in results:
                # member format: "BMW:2020"
                if isinstance(member, bytes):
                    member = member.decode("utf-8")
                parts = member.rsplit(":", 1)
                if len(parts) != 2:
                    continue
                try:
                    make = parts[0]
                    year = int(parts[1])
                    shards.append((make, year, float(score)))
                except (ValueError, TypeError):
                    continue

            if shards:
                log.info(
                    "frontier.loaded",
                    platform=self._platform,
                    shard_count=len(shards),
                    top_shard=f"{shards[0][0]}:{shards[0][1]}",
                    top_score=round(shards[0][2], 4),
                )
            return shards

        except Exception as e:
            log.warning("frontier.load_failed", error=str(e))
            return []

    async def report_result(self, make: str, year: int, new_count: int) -> None:
        """
        Report crawl outcome for Thompson Sampling update.

        The frontier service reads these results hourly to update alpha/beta
        parameters: new_count > 0 → success (alpha++), else → failure (beta++).
        """
        try:
            field = f"{make}:{year}"
            await self._redis.hset(self._result_key, field, str(new_count))
            # TTL of 24h so stale results don't accumulate
            await self._redis.expire(self._result_key, 86400)
        except Exception as e:
            log.warning("frontier.report_failed", error=str(e))
