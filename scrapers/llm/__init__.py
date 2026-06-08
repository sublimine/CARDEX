"""
Local LLM decision layer (Ollama) — fuzzy micro-decisions for the pipeline.

Design contract (the reason this layer exists):
  * Deterministic heuristics run FIRST and decide the clear cases for free.
  * The local LLM (Ollama, 127.0.0.1:11434) is consulted ONLY on the ambiguous
    band — so steady-state throughput costs zero Claude tokens and near-zero
    local compute (the model is a fallback, not a replacement).
  * Every LLM path degrades gracefully: if Ollama is down/slow/garbles, the
    function returns the heuristic verdict. The pipeline never blocks on the LLM.

Public surface:
  * ``ollama_client.OllamaClient`` — thin, dependency-free (stdlib urllib) JSON client.
  * ``decisions`` — the three fuzzy decisions (is-car-dealer, field-extract, domain
    disambiguation), each heuristic-first with an LLM tie-breaker.
"""
from __future__ import annotations

from scrapers.llm.ollama_client import OllamaClient, get_client

__all__ = ["OllamaClient", "get_client"]
