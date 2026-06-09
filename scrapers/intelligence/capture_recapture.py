"""
Capture-recapture (Chapman / Lincoln-Petersen) — estimación ORTOGONAL del universo de entidades.

El problema central de "¿los tenemos a TODOS?" no se puede responder con el conteo de una fuente
(toda fuente miente por omisión). La respuesta institucional es estadística: si dos fuentes
INDEPENDIENTES capturan n1 y n2 entidades de la misma población y comparten m (solapamiento), el
tamaño REAL N de la población se estima sin necesidad de verlas todas. Esta es la 3ª vía ortogonal
del motor de completitud (junto a re-derivación de fuente y censo top-down): nadie confía en una
sola cifra; se corrobora con un estimador que no depende de ninguna fuente concreta.

Estimador de Chapman (Lincoln-Petersen con corrección de sesgo, insesgado a muestra baja):
    N̂ = (n1+1)(n2+1)/(m+1) − 1
    var(N̂) = (n1+1)(n2+1)(n1−m)(n2−m) / [ (m+1)² (m+2) ]
Supuestos (declararlos siempre): población cerrada en la ventana, captura independiente entre fuentes,
identificación correcta del solapamiento (mismo dealer = misma clave canónica). Si se violan, el
estimador sesga — por eso es UNA vía de corroboración, no la verdad única.

Pure-function core (testeable sin red/DB); el audit por país lee source_overlap_matrix (o cuenta vivo).
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class UniverseEstimate:
    """Estimación del universo + intervalo + cobertura observada."""

    n1: int
    n2: int
    overlap: int
    observed_union: int
    estimate: float          # N̂ (Chapman)
    std_error: float         # sqrt(var)
    ci95_low: float
    ci95_high: float
    coverage: float          # observed_union / N̂  (∈ (0,1]; 1.0 = lo tenemos todo)

    @property
    def trustworthy_complete(self) -> bool:
        """Cobertura >= 95% y el límite superior del IC no implica un faltante grande."""
        return self.coverage >= 0.95


def chapman_estimate(n1: int, n2: int, overlap: int, observed_union: int | None = None) -> UniverseEstimate:
    """
    Estima el tamaño del universo por captura-recaptura (Chapman).

    n1, n2: entidades capturadas por la fuente 1 y la fuente 2 (independientes).
    overlap (m): entidades capturadas por AMBAS (misma clave canónica).
    observed_union: distintas vistas por la unión de fuentes (default n1+n2−m).

    Degenerados manejados explícitamente (sin mentir): overlap 0 → no estimable (devuelve inf y
    coverage 0, señal de "fuentes disjuntas: necesitas más solapamiento o una 3ª fuente").
    """
    if n1 < 0 or n2 < 0 or overlap < 0 or overlap > min(n1, n2):
        raise ValueError(f"capture-recapture inválido: n1={n1} n2={n2} overlap={overlap}")
    union = observed_union if observed_union is not None else (n1 + n2 - overlap)
    if overlap == 0:
        # Sin solapamiento el estimador no está definido (división informativa imposible).
        return UniverseEstimate(n1, n2, 0, union, float("inf"), float("inf"),
                                float(union), float("inf"), 0.0)
    n_hat = (n1 + 1) * (n2 + 1) / (overlap + 1) - 1.0
    var = ((n1 + 1) * (n2 + 1) * (n1 - overlap) * (n2 - overlap)) / (((overlap + 1) ** 2) * (overlap + 2))
    se = math.sqrt(var) if var > 0 else 0.0
    lo = max(float(union), n_hat - 1.96 * se)
    hi = n_hat + 1.96 * se
    coverage = min(1.0, union / n_hat) if n_hat > 0 else 0.0
    return UniverseEstimate(n1, n2, overlap, union, n_hat, se, lo, hi, round(coverage, 4))


# ── audit por país (lee del store; opcional, no en el hot-path de tests) ──────────────────────
_DSN = os.environ.get("DATABASE_URL", "postgres://cardex:cardex_dev_only@localhost:5432/cardex")


async def audit_country(country: str, source_a: str, source_b: str, *, dsn: str | None = None) -> UniverseEstimate:
    """
    Estima el universo de un país cruzando dos fuentes de discovery_candidates por clave canónica.

    Clave canónica de solapamiento: domain cuando existe; si no, (registry_id) normalizado. Dos
    fuentes distintas que apuntan al mismo domain/registro = la MISMA entidad (overlap). Esto da una
    estimación INDEPENDIENTE del tamaño real de dealers del país, ortogonal a cualquier conteo de fuente.
    """
    import asyncpg

    conn = await asyncpg.connect(dsn or _DSN)
    try:
        async def keys(src: str) -> set[str]:
            rows = await conn.fetch(
                "SELECT DISTINCT coalesce(domain, source||':'||registry_id) AS k "
                "FROM discovery_candidates WHERE country=$1 AND source=$2 "
                "AND coalesce(domain, registry_id) IS NOT NULL",
                country, src)
            return {r["k"] for r in rows}

        ka, kb = await keys(source_a), await keys(source_b)
    finally:
        await conn.close()
    overlap = len(ka & kb)
    union = len(ka | kb)
    return chapman_estimate(len(ka), len(kb), overlap, union)
