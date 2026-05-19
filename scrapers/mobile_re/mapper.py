"""
HAR → OpenAPI mapper — genera spec de la API móvil a partir del tráfico capturado.

Proceso:
  1. Leer archivo .har de mobile_re/captures/{portal}.har
  2. Ejecutar mitmproxy2swagger para generar spec OpenAPI preliminar
  3. Post-proceso: filtrar endpoints relevantes (search, listing, auth)
  4. Guardar spec en mobile_re/specs/{portal}.yaml

La spec generada es la base para implementar el client en portals/{portal}.py.
Actualizar la spec si la app actualiza su API (detectado por 401/schema changes).
"""
from __future__ import annotations

from pathlib import Path


_SPECS_DIR = Path(__file__).parent / "specs"
_CAPTURE_DIR = Path(__file__).parent / "captures"


def generate_spec(portal: str, har_path: Path | None = None) -> Path:
    """
    Run mitmproxy2swagger on the portal's HAR file.
    Returns path to generated OpenAPI spec YAML.
    """
    raise NotImplementedError


def extract_search_endpoints(spec_path: Path) -> list[dict]:
    """
    Parse OpenAPI spec and return only search + listing endpoints.
    Filters out analytics, auth-internal, and CDN endpoints.
    """
    raise NotImplementedError
