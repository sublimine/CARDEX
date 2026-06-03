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


def _bezier_points(
    start: tuple[float, float],
    end: tuple[float, float],
    steps: int,
    jitter: float,
    rng: random.Random,
) -> list[tuple[float, float]]:
    """
    Cubic Bézier path from start to end with two jittered control points.

    A straight line has zero curvature entropy — DataDome flags it instantly.
    The control points are offset off-axis by ±jitter so the path curves, giving
    non-zero velocity/acceleration variance. Endpoints are exact (t=0 → start,
    t=1 → end); the path has steps+1 points.
    """
    (x0, y0), (x3, y3) = start, end
    cx1 = x0 + (x3 - x0) / 3 + rng.uniform(-jitter, jitter)
    cy1 = y0 + (y3 - y0) / 3 + rng.uniform(-jitter, jitter)
    cx2 = x0 + 2 * (x3 - x0) / 3 + rng.uniform(-jitter, jitter)
    cy2 = y0 + 2 * (y3 - y0) / 3 + rng.uniform(-jitter, jitter)
    pts: list[tuple[float, float]] = []
    for i in range(steps + 1):
        t = i / steps
        mt = 1 - t
        x = mt**3 * x0 + 3 * mt**2 * t * cx1 + 3 * mt * t**2 * cx2 + t**3 * x3
        y = mt**3 * y0 + 3 * mt**2 * t * cy1 + 3 * mt * t**2 * cy2 + t**3 * y3
        pts.append((x, y))
    return pts


def _scroll_steps(
    distance_px: int, variance: float, rng: random.Random, n: int | None = None
) -> list[int]:
    """
    Split a scroll distance into n decelerating chunks with ±variance jitter.

    Humans scroll in bursts that slow down (momentum decay), not one constant
    sweep. Weights decrease linearly; each chunk is jittered. The signed sum is
    close to distance_px and every chunk keeps the sign of the scroll direction.
    """
    n = n or rng.randint(4, 8)
    weights = [n - i for i in range(n)]
    total = sum(weights)
    sign = 1 if distance_px >= 0 else -1
    magnitude = abs(distance_px)
    steps: list[int] = []
    for w in weights:
        base = magnitude * w / total
        chunk = int(base * (1 + rng.uniform(-variance, variance)))
        steps.append(sign * max(1, chunk))
    return steps


async def move_to_element(page: Any, selector: str, rng: random.Random | None = None) -> None:
    """
    Move mouse to element via bezier curve path.
    Speed and acceleration follow human motor control distribution.
    Not a straight line from current position.
    """
    rng = rng or random
    element = await page.query_selector(selector)
    if element is None:
        return
    box = await element.bounding_box()
    if not box:
        return
    # Land inside the element but not dead-center — real clicks scatter.
    target = (
        box["x"] + box["width"] * rng.uniform(0.3, 0.7),
        box["y"] + box["height"] * rng.uniform(0.3, 0.7),
    )
    start = (rng.uniform(0, 60), rng.uniform(0, 60))
    for x, y in _bezier_points(start, target, steps=rng.randint(18, 28), jitter=40, rng=rng):
        await page.mouse.move(x, y)
        await asyncio.sleep(rng.uniform(0.004, 0.014))


async def human_scroll(
    page: Any, distance_px: int, variance: float = 0.3, rng: random.Random | None = None
) -> None:
    """
    Scroll distance_px with ±variance randomness and natural deceleration.
    Includes micro-pauses typical of human reading.
    """
    rng = rng or random
    for delta in _scroll_steps(distance_px, variance, rng):
        await page.mouse.wheel(0, delta)
        await asyncio.sleep(rng.uniform(0.05, 0.22))


async def human_dwell(min_s: float, max_s: float) -> None:
    """
    Wait a random duration between min_s and max_s.
    Distribution is lognormal, not uniform — matches human reading behavior.
    """
    mu = (min_s + max_s) / 2
    sigma = (max_s - min_s) / 4
    duration = max(min_s, min(max_s, random.lognormvariate(mu, sigma)))
    await asyncio.sleep(duration)


async def simulate_reading(
    page: Any, dwell_s: tuple[float, float], rng: random.Random | None = None
) -> None:
    """
    Full reading simulation: scroll + micro-pauses + random mouse movement.
    Used during BROWSE step of session plan.

    Scrolls down the page in reading-sized chunks separated by pauses until the
    sampled dwell budget is spent. Total time tracks both scroll and pause cost
    so the session length matches the persona's reading distribution.
    """
    rng = rng or random
    lo, hi = dwell_s
    budget = rng.uniform(lo, hi)
    elapsed = 0.0
    while elapsed < budget:
        await human_scroll(page, rng.randint(200, 600), rng=rng)
        pause = rng.uniform(0.8, 2.5)
        await asyncio.sleep(pause)
        elapsed += pause + 0.8  # approximate scroll cost + pause
