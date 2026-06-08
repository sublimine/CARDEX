"""
Ollama client — thin, dependency-free, fail-open.

Talks to a local Ollama server (default ``127.0.0.1:11434``) over stdlib
``urllib`` (no new third-party dependency — the scraper fleet already pins its
deps and this layer must not widen them). Every call is best-effort: on ANY
fault (server down, timeout, non-200, malformed JSON) it returns ``None`` so the
caller falls back to its deterministic heuristic. The pipeline must never block
or crash because the optional LLM layer is unavailable.

RAM discipline (the host is low-RAM and OOM-prone):
  * ``keep_alive`` is short by default so the model unloads after a quiet spell,
    returning its ~2 GB to the host between bursts.
  * ``num_ctx`` is small (the prompts are short, the inputs are truncated).
  * A process-wide semaphore caps concurrent generations at 1 — the server runs
    ``OLLAMA_NUM_PARALLEL=1`` and a second loaded context would crater the host.
  * ``temperature=0`` for deterministic, idempotent classification/extraction.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request

log = logging.getLogger(__name__)

# ── config (env-overridable) ────────────────────────────────────────────────────
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")
OLLAMA_TIMEOUT = float(os.environ.get("OLLAMA_TIMEOUT", "45"))  # covers a cold model load (~25s)
OLLAMA_KEEP_ALIVE = os.environ.get("OLLAMA_KEEP_ALIVE", "120s")
OLLAMA_NUM_CTX = int(os.environ.get("OLLAMA_NUM_CTX", "2048"))
# Health probe is cached for this long so a down server is not re-probed per call.
_HEALTH_TTL_S = float(os.environ.get("OLLAMA_HEALTH_TTL", "30"))

# One generation at a time, process-wide (RAM ceiling — never two loaded contexts).
_GEN_LOCK = threading.Semaphore(1)


class OllamaClient:
    """Minimal Ollama JSON client. Fail-open: faults surface as ``None``."""

    def __init__(
        self,
        *,
        url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        keep_alive: str | None = None,
        num_ctx: int | None = None,
    ) -> None:
        self.url = (url or OLLAMA_URL).rstrip("/")
        self.model = model or OLLAMA_MODEL
        self.timeout = timeout if timeout is not None else OLLAMA_TIMEOUT
        self.keep_alive = keep_alive or OLLAMA_KEEP_ALIVE
        self.num_ctx = num_ctx or OLLAMA_NUM_CTX
        self._health: tuple[float, bool] | None = None  # (checked_at, ok)

    # ── health ──────────────────────────────────────────────────────────────────
    def available(self) -> bool:
        """True if the server answered /api/version recently (cached ``_HEALTH_TTL_S``)."""
        now = time.monotonic()
        if self._health is not None and (now - self._health[0]) < _HEALTH_TTL_S:
            return self._health[1]
        ok = False
        try:
            req = urllib.request.Request(f"{self.url}/api/version", method="GET")
            with urllib.request.urlopen(req, timeout=min(self.timeout, 5)) as resp:
                ok = resp.status == 200
        except (urllib.error.URLError, OSError, ValueError):
            ok = False
        self._health = (now, ok)
        return ok

    def model_present(self) -> bool:
        """True if ``self.model`` is pulled locally (via /api/tags)."""
        try:
            req = urllib.request.Request(f"{self.url}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=min(self.timeout, 5)) as resp:
                tags = json.loads(resp.read().decode("utf-8", "replace"))
        except (urllib.error.URLError, OSError, ValueError):
            return False
        names = {m.get("name", "") for m in (tags.get("models") or [])}
        # match "qwen2.5:3b" against "qwen2.5:3b" or a ":latest"-suffixed form
        return any(n == self.model or n.split(":")[0] == self.model.split(":")[0] for n in names)

    # ── generation ────────────────────────────────────────────────────────────────
    def generate_json(
        self,
        prompt: str,
        *,
        system: str | None = None,
        schema: dict | None = None,
        max_tokens: int = 256,
    ) -> dict | None:
        """
        Run one prompt with ``format=json`` (or a JSON schema) and parse the reply.

        Returns the parsed object, or ``None`` on any fault (caller falls back to
        its heuristic). Deterministic: ``temperature=0``. Serialised by the
        process-wide semaphore so only one context is ever loaded.
        """
        body: dict = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": schema if schema is not None else "json",
            "keep_alive": self.keep_alive,
            "options": {"temperature": 0, "num_ctx": self.num_ctx, "num_predict": max_tokens},
        }
        if system:
            body["system"] = system
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            f"{self.url}/api/generate", data=data,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        acquired = _GEN_LOCK.acquire(timeout=self.timeout)
        if not acquired:
            log.warning("ollama: generation lock busy > %.0fs — skipping (fall back)", self.timeout)
            return None
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8", "replace"))
        except (urllib.error.URLError, OSError, ValueError, TimeoutError) as exc:
            log.warning("ollama generate failed (%s) — falling back to heuristic", type(exc).__name__)
            self._health = (time.monotonic(), False)  # poison health so we stop hammering a dead server
            return None
        finally:
            _GEN_LOCK.release()
        text = (payload or {}).get("response", "")
        if not text:
            return None
        try:
            return json.loads(text)
        except (ValueError, TypeError):
            # Some models wrap JSON in prose despite format=json — salvage the first object.
            start, end = text.find("{"), text.rfind("}")
            if 0 <= start < end:
                try:
                    return json.loads(text[start : end + 1])
                except ValueError:
                    return None
            return None


# Process-wide singleton (one health cache, one model handle).
_CLIENT: OllamaClient | None = None
_CLIENT_LOCK = threading.Lock()


def get_client() -> OllamaClient:
    """Return the shared :class:`OllamaClient` (built once)."""
    global _CLIENT
    if _CLIENT is None:
        with _CLIENT_LOCK:
            if _CLIENT is None:
                _CLIENT = OllamaClient()
    return _CLIENT
