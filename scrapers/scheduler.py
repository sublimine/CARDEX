"""
Scheduler — decide qué portal scrape cuándo y con qué parámetros.

Responsabilidades:
  1. Leer domain_tier_state de engine.db para saber tier efectivo por portal
  2. Leer vehicle_index PG para calcular next_scrape_at por portal/país
     (scheduling adaptativo: C1 Delta Engine — next_scrape /= 2 si cambio, *= 1.5 si estático)
  3. Escribir work_queue entries con priority + scheduled_at
  4. Respetar circuit breaker state (no encolar si circuit=OPEN)
  5. Gestionar cuota de identidades premium (no asignar T3 si premium_pool < 3)

Scheduling adaptativo (§C1):
  Con cambio reciente:   next_scrape_at = now + 1h
  Sin cambio 7 días:     next_scrape_interval *= 1.5 (máx 30 días)
  Con cambio detectado:  next_scrape_interval /= 2   (mínimo 1h)
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class SchedulerConfig:
    db_path: str = "scrapers/engine.db"
    database_url: str = "postgres://cardex:cardex_dev_only@localhost:5432/cardex"
    min_interval_h: float = 1.0
    max_interval_h: float = 720.0    # 30 días


async def run(config: SchedulerConfig) -> None:
    """Scheduler loop. Runs alongside coordinator."""
    raise NotImplementedError
