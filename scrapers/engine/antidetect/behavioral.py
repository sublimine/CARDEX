"""
Behavioral layer — T3 únicamente. Simula comportamiento humano real.

DataDome y PerimeterX analizan:
  - Velocidad y aceleración del movimiento de ratón (entropía > 0)
  - Patrón de scroll (no lineal, con pausas)
  - Tiempo entre páginas (distribución humana, no constante)
  - Click accuracy (no exactamente en el centro del elemento)
  - Keyboard timing (si se usa búsqueda con texto)

Este módulo usa Oxymouse (o implementación equivalente) para inyectar
movimiento de ratón sintético-pero-realista en páginas Camoufox T3.

Solo activar en T3. No necesario para T1/T2 — overhead innecesario.
"""
from __future__ import annotations

import asyncio
import random
from typing import Any


async def move_to_element(page: Any, selector: str) -> None:
    """
    Move mouse to element via bezier curve path.
    Speed and acceleration follow human motor control distribution.
    Not a straight line from current position.
    """
    raise NotImplementedError


async def human_scroll(page: Any, distance_px: int, variance: float = 0.3) -> None:
    """
    Scroll distance_px with ±variance randomness and natural deceleration.
    Includes micro-pauses typical of human reading.
    """
    raise NotImplementedError


async def human_dwell(min_s: float, max_s: float) -> None:
    """
    Wait a random duration between min_s and max_s.
    Distribution is lognormal, not uniform — matches human reading behavior.
    """
    mu = (min_s + max_s) / 2
    sigma = (max_s - min_s) / 4
    duration = max(min_s, min(max_s, random.lognormvariate(mu, sigma)))
    await asyncio.sleep(duration)


async def simulate_reading(page: Any, dwell_s: tuple[float, float]) -> None:
    """
    Full reading simulation: scroll + micro-pauses + random mouse movement.
    Used during BROWSE step of session plan.
    """
    raise NotImplementedError
