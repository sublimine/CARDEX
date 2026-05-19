"""
mitmproxy interceptor — captura de tráfico de apps móviles para RE.

Proceso (SCRAPING_ENGINE.md §A7):
  1. Lanzar mitmproxy en modo transparente
  2. Conectar emulador Android con certificado mitmproxy instalado
  3. Usar frida-gadget para bypass de certificate pinning
  4. Capturar tráfico de la app objetivo
  5. Exportar a formato HAR → mapper.py genera spec OpenAPI

Este módulo automatiza pasos 1 + 5.
Pasos 2-4 son manuales (one-time per portal).

Resultado: archivo .har en mobile_re/captures/{portal}.har
           luego procesado por mapper.py
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

log = logging.getLogger(__name__)

_CAPTURE_DIR = Path(__file__).parent / "captures"


async def capture(
    portal: str,
    duration_s: int = 120,
    output_path: Path | None = None,
) -> Path:
    """
    Start mitmproxy, wait duration_s, save HAR to output_path.
    Requires mitmproxy installed and Android emulator connected.
    Returns path to .har file.
    """
    raise NotImplementedError


def frida_unpin_script(package_name: str) -> str:
    """
    Return Frida JS script for certificate unpinning on the given Android package.
    Universal unpinner covers OkHttp, TrustManager, and SSLPinning patterns.
    """
    raise NotImplementedError
