"""
CaptchaSolver — optional CAPTCHA resolution layer.

Activated only when env var CAPTCHA_API_KEY is set.
Backend: 2captcha (supports reCAPTCHA v2/v3, hCaptcha, Cloudflare Turnstile).

Without an API key, the solver logs a warning and returns None,
allowing the caller to decide whether to skip or retry the page later.

Usage:
    solver = CaptchaSolver()
    token = await solver.solve_recaptcha(sitekey="xxx", url="https://...")
    if token:
        # inject token into form or JS
"""
from __future__ import annotations

import asyncio
import os
from typing import Optional

import structlog

log = structlog.get_logger()

_POLL_INTERVAL = 5   # seconds between 2captcha result polls
_MAX_WAIT = 120      # max seconds to wait for solve


class CaptchaSolver:
    """
    Async CAPTCHA solver backed by 2captcha.
    All methods return None gracefully if no API key is configured.
    """

    def __init__(self) -> None:
        self._api_key = os.environ.get("CAPTCHA_API_KEY", "")
        self._base = "https://2captcha.com"
        self._enabled = bool(self._api_key)
        if not self._enabled:
            log.warning(
                "captcha_solver.disabled",
                reason="CAPTCHA_API_KEY not set — CAPTCHAs will not be solved automatically",
            )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def solve_recaptcha_v2(self, sitekey: str, url: str) -> Optional[str]:
        """Solve Google reCAPTCHA v2 invisible/checkbox. Returns g-recaptcha-response token."""
        if not self._enabled:
            return None
        task_id = await self._submit({
            "method": "userrecaptcha",
            "googlekey": sitekey,
            "pageurl": url,
        })
        return await self._wait_result(task_id, "recaptcha_v2")

    async def solve_recaptcha_v3(
        self, sitekey: str, url: str, action: str = "verify", min_score: float = 0.3
    ) -> Optional[str]:
        """Solve Google reCAPTCHA v3. Returns token."""
        if not self._enabled:
            return None
        task_id = await self._submit({
            "method": "userrecaptcha",
            "version": "v3",
            "googlekey": sitekey,
            "pageurl": url,
            "action": action,
            "min_score": min_score,
        })
        return await self._wait_result(task_id, "recaptcha_v3")

    async def solve_hcaptcha(self, sitekey: str, url: str) -> Optional[str]:
        """Solve hCaptcha. Returns h-captcha-response token."""
        if not self._enabled:
            return None
        task_id = await self._submit({
            "method": "hcaptcha",
            "sitekey": sitekey,
            "pageurl": url,
        })
        return await self._wait_result(task_id, "hcaptcha")

    async def solve_turnstile(self, sitekey: str, url: str) -> Optional[str]:
        """Solve Cloudflare Turnstile. Returns cf-turnstile-response token."""
        if not self._enabled:
            return None
        task_id = await self._submit({
            "method": "turnstile",
            "sitekey": sitekey,
            "pageurl": url,
        })
        return await self._wait_result(task_id, "turnstile")

    # ------------------------------------------------------------------
    # Internal helpers (httpx-free to avoid circular dep with http_client)
    # ------------------------------------------------------------------

    async def _submit(self, params: dict) -> str:
        """Submit a CAPTCHA task to 2captcha. Returns task ID."""
        import urllib.parse
        import urllib.request

        data = {**params, "key": self._api_key, "json": 1}
        body = urllib.parse.urlencode(data).encode()

        loop = asyncio.get_event_loop()
        response_bytes = await loop.run_in_executor(
            None,
            lambda: urllib.request.urlopen(
                f"{self._base}/in.php", data=body, timeout=30
            ).read()
        )
        import json
        result = json.loads(response_bytes)
        if result.get("status") != 1:
            raise RuntimeError(f"2captcha submit error: {result.get('error_text', result)}")
        task_id = str(result["request"])
        log.debug("captcha_solver.submitted", task_id=task_id)
        return task_id

    async def _wait_result(self, task_id: str, captcha_type: str) -> Optional[str]:
        """Poll 2captcha for the solved token. Returns None on timeout."""
        import urllib.request
        import json

        url = (
            f"{self._base}/res.php"
            f"?key={self._api_key}&action=get&id={task_id}&json=1"
        )
        loop = asyncio.get_event_loop()
        elapsed = 0

        # Initial wait — 2captcha needs at least 15s to start working
        await asyncio.sleep(15)
        elapsed += 15

        while elapsed < _MAX_WAIT:
            await asyncio.sleep(_POLL_INTERVAL)
            elapsed += _POLL_INTERVAL

            response_bytes = await loop.run_in_executor(
                None,
                lambda: urllib.request.urlopen(url, timeout=15).read()
            )
            result = json.loads(response_bytes)

            if result.get("status") == 1:
                token = result["request"]
                log.info(
                    "captcha_solver.solved",
                    task_id=task_id,
                    type=captcha_type,
                    elapsed_s=elapsed,
                )
                return token

            if result.get("request") != "CAPCHA_NOT_READY":
                log.error(
                    "captcha_solver.error",
                    task_id=task_id,
                    error=result.get("request"),
                )
                return None

        log.warning("captcha_solver.timeout", task_id=task_id, elapsed_s=elapsed)
        return None
