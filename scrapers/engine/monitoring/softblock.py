"""
Soft-block detection — el bloqueo silencioso que mata sistemas de scraping.

Un soft block es un 200 OK sin datos útiles: el WAF sirve una página válida pero
vacía (o envenenada) en lugar de un 403. No hay señal HTTP; la única evidencia es
estadística. Dos detectores cubren los dos vectores de SCRAPING_ENGINE.md §F:

  NullFieldTracker  — "Soft block (200 sin datos)": null_field_rate > 15% en una
                      ventana deslizante de 10 requests. Cada request aporta un
                      booleano (¿le faltan campos críticos?). Hasta no llenar la
                      ventana no se dispara: con < 10 muestras el ratio no es
                      estadísticamente fiable y un único fallo daría 100%.

  ZeroUrlTracker    — "Zero-URL soft block": 3 ciclos de listado consecutivos que
                      devuelven 0 URLs. Un solo ciclo vacío puede ser una página
                      legítimamente sin resultados (filtro muy estrecho); tres
                      seguidos en un portal que siempre tiene stock = bloqueo.

Ambos son máquinas de estado puras y sin efectos: no tocan la red, la DB ni
Prometheus. El coordinator lee `is_soft_blocked` / `rate` y decide la respuesta
(quarantine + rotación de identidad) y publica el ratio en metrics.
"""
from __future__ import annotations

from collections import deque

# Umbrales [VERIFICADO] SCRAPING_ENGINE.md §F (matriz de fallos) y §E (alert expr).
SOFT_BLOCK_RATE = 0.15  # null_field_rate por encima de esto = soft block
SOFT_BLOCK_WINDOW = 10  # tamaño de la ventana deslizante de requests
ZERO_URL_CYCLES = 3  # ciclos de listado vacíos consecutivos que disparan el bloqueo


class NullFieldTracker:
    """
    Ventana deslizante de los últimos `window` requests para un portal.

    Cada `record(missing_critical)` empuja un booleano: True si al record le
    faltaban campos críticos (precio/VIN/etc.), False si vino completo. El ratio
    es la fracción de True en la ventana. `is_soft_blocked` solo es True cuando la
    ventana está llena Y el ratio supera el umbral.
    """

    def __init__(self, window: int = SOFT_BLOCK_WINDOW, threshold: float = SOFT_BLOCK_RATE) -> None:
        if window <= 0:
            raise ValueError("window must be positive")
        self._window = window
        self._threshold = threshold
        self._samples: deque[bool] = deque(maxlen=window)

    def record(self, missing_critical: bool) -> None:
        """Add one request outcome (True = record was missing critical fields)."""
        self._samples.append(bool(missing_critical))

    @property
    def sample_count(self) -> int:
        return len(self._samples)

    @property
    def is_full(self) -> bool:
        return len(self._samples) >= self._window

    @property
    def rate(self) -> float:
        """Fraction of recorded requests missing critical fields (0.0 when empty)."""
        if not self._samples:
            return 0.0
        return sum(self._samples) / len(self._samples)

    @property
    def is_soft_blocked(self) -> bool:
        """True once the window is full and the null-field rate exceeds the threshold."""
        return self.is_full and self.rate > self._threshold

    def reset(self) -> None:
        """Clear the window — call after rotating to a fresh identity."""
        self._samples.clear()


class ZeroUrlTracker:
    """
    Counts consecutive listing cycles that collected zero URLs for a portal.

    A single empty cycle is noise; `cycles` consecutive empties on a portal that
    normally has inventory is a soft block. Any non-empty cycle resets the run.
    """

    def __init__(self, cycles: int = ZERO_URL_CYCLES) -> None:
        if cycles <= 0:
            raise ValueError("cycles must be positive")
        self._cycles = cycles
        self._consecutive = 0

    def record(self, url_count: int) -> None:
        """Record a listing cycle's URL count; 0 extends the empty run, >0 resets it."""
        if url_count <= 0:
            self._consecutive += 1
        else:
            self._consecutive = 0

    @property
    def consecutive_empty(self) -> int:
        return self._consecutive

    @property
    def is_soft_blocked(self) -> bool:
        return self._consecutive >= self._cycles

    def reset(self) -> None:
        """Clear the empty-cycle run — call after rotating to a fresh identity."""
        self._consecutive = 0
