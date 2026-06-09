"""
cdx_code — código único e INMUTABLE por entidad CARDEX (institucional, portable).

Cada dealer/plataforma tiene un código estable `CDX-<ISO2>-<8>` que NO cambia entre re-consolidaciones
ni al migrar a otra herramienta (Codex u otra): es la clave humana+canónica de la entidad. Se DERIVA de
la identidad ESTABLE de la entidad (no de un autoincrement), así la misma entidad física siempre obtiene
el mismo código aunque se redescubra por otra fuente.

Prioridad de identidad (la primera no vacía):
  1. dominio normalizado          (la web propia = identidad más fuerte)
  2. país + registro              (siret/registry_id: identidad legal estable)
  3. país + nombre + ciudad       (fallback para entidades sin web ni registro)

Código = CDX-<ISO2>-<base32(blake2b(identity, 5 bytes))>  → 8 chars base32, estable y legible.
Determinista y puro (sin red/DB) → testeable y reproducible en cualquier herramienta.
"""
from __future__ import annotations

import base64
import hashlib
import re

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^a-z0-9]+")


def _norm(s: str | None) -> str:
    return _WS.sub(" ", (s or "").strip().lower())


def _norm_domain(domain: str | None) -> str:
    d = _norm(domain)
    d = re.sub(r"^https?://", "", d)
    d = re.sub(r"^www\.", "", d)
    return d.rstrip("/")


def _norm_name(name: str | None) -> str:
    return _PUNCT.sub("", _norm(name))  # alfa-num, sin espacios ni puntuación


def entity_identity(country: str, *, domain: str | None = None, registry_id: str | None = None,
                    name: str | None = None, city: str | None = None) -> str:
    """Cadena de identidad canónica y estable (prioridad dominio > registro > nombre+ciudad)."""
    cc = (country or "").strip().upper()[:2]
    dom = _norm_domain(domain)
    if dom:
        return f"d:{dom}"                      # dominio es global; no se prefija país (puede ser .com)
    reg = _norm(registry_id)
    if reg:
        return f"r:{cc}:{reg}"
    nm = _norm_name(name)
    if nm:
        return f"n:{cc}:{nm}:{_norm_name(city)}"
    return ""  # sin identidad estable → el caller debe descartar (no se le asigna cdx_code)


def cdx_code(country: str, *, domain: str | None = None, registry_id: str | None = None,
             name: str | None = None, city: str | None = None) -> str | None:
    """
    Devuelve el cdx_code inmutable o None si no hay identidad estable.

    El prefijo de país es el del argumento (la ubicación de la entidad), aunque la identidad sea por
    dominio global — así CDX-FR-xxxx vive en FR aunque su web sea .com. El hash garantiza unicidad y
    estabilidad: misma identidad → mismo código siempre.
    """
    ident = entity_identity(country, domain=domain, registry_id=registry_id, name=name, city=city)
    if not ident:
        return None
    cc = (country or "").strip().upper()[:2] or "XX"
    digest = hashlib.blake2b(ident.encode("utf-8"), digest_size=5).digest()
    code = base64.b32encode(digest).decode("ascii").rstrip("=")  # 8 chars
    return f"CDX-{cc}-{code}"
