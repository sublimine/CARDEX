"""
CARDEX document converter — MarkItDown wrapper.

Converts dealer documents (PDF, Excel, Word) and raw HTML to clean Markdown
before sending to the LLM pipeline (llama.cpp fiscal classifier or enrich_worker).

Usage patterns:
  - html_to_markdown(html)   : strip boilerplate from scraped HTML before LLM
  - file_to_markdown(path)   : process PDF/Excel/Word inventory sheets
  - bytes_to_markdown(data, suffix) : process in-memory downloads without disk I/O

All functions are synchronous (MarkItDown is sync-only). Call from sync context
or wrap with asyncio.to_thread() inside async consumers.

Supported extras installed: [pdf, docx, xlsx]
Not installed: [audio-transcription, youtube-transcription, llm-client]
"""
from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from pathlib import Path
from typing import Literal

log = logging.getLogger(__name__)

# Lazy singleton — avoid paying import cost when the module is not used.
_md_instance = None


def _get_md():
    global _md_instance
    if _md_instance is None:
        from markitdown import MarkItDown
        _md_instance = MarkItDown(enable_plugins=False)
    return _md_instance


SupportedSuffix = Literal[".pdf", ".docx", ".doc", ".xlsx", ".xls", ".csv", ".html", ".htm"]


def html_to_markdown(html: str, *, url: str = "") -> str:
    """Convert raw HTML string to clean Markdown.

    Args:
        html: Raw HTML content (bytes accepted too — will be decoded).
        url:  Optional source URL logged on failure.

    Returns:
        Markdown string. Empty string on failure (caller decides to skip or retry).
    """
    if isinstance(html, bytes):
        try:
            html = html.decode("utf-8", errors="replace")
        except Exception:
            pass

    tmp = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", encoding="utf-8", delete=False
        ) as f:
            f.write(html)
            tmp = f.name

        result = _get_md().convert(tmp)
        return result.text_content or ""
    except Exception as exc:
        log.warning("html_to_markdown failed", extra={"url": url, "error": str(exc)})
        return ""
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)


def file_to_markdown(path: str | Path) -> str:
    """Convert a file on disk (PDF, Excel, Word, CSV, HTML) to Markdown.

    Args:
        path: Absolute or relative path to the file.

    Returns:
        Markdown string. Empty string on failure.
    """
    path = str(path)
    try:
        result = _get_md().convert(path)
        return result.text_content or ""
    except Exception as exc:
        log.warning("file_to_markdown failed", extra={"path": path, "error": str(exc)})
        return ""


def bytes_to_markdown(data: bytes, suffix: SupportedSuffix) -> str:
    """Convert in-memory bytes to Markdown without touching disk permanently.

    Useful for processing PDF/Excel responses downloaded with curl_cffi or aiohttp
    without saving to a permanent path.

    Args:
        data:   Raw file bytes.
        suffix: File extension including the dot, e.g. ".pdf" or ".xlsx".
                Required so MarkItDown picks the right converter.

    Returns:
        Markdown string. Empty string on failure.
    """
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(data)
            tmp = f.name

        result = _get_md().convert(tmp)
        return result.text_content or ""
    except Exception as exc:
        log.warning(
            "bytes_to_markdown failed",
            extra={"suffix": suffix, "size": len(data), "error": str(exc)},
        )
        return ""
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)


async def html_to_markdown_async(html: str, *, url: str = "") -> str:
    """Async wrapper for html_to_markdown — runs in a thread pool."""
    return await asyncio.to_thread(html_to_markdown, html, url=url)


async def file_to_markdown_async(path: str | Path) -> str:
    """Async wrapper for file_to_markdown — runs in a thread pool."""
    return await asyncio.to_thread(file_to_markdown, path)


async def bytes_to_markdown_async(data: bytes, suffix: SupportedSuffix) -> str:
    """Async wrapper for bytes_to_markdown — runs in a thread pool."""
    return await asyncio.to_thread(bytes_to_markdown, data, suffix)
