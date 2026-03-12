"""
CARDEX Sovereign AI Worker (Phase 2)
Consumes stream:l3_pending, runs Qwen2.5-Coder-7B Q5_K_M with GBNF grammar,
injects results into dict:l1_tax.

Execution: Single-threaded, pinned to cores 30-31 via taskset.
  taskset -c 30,31 python worker.py

Environment:
  OMP_NUM_THREADS=2
  GGML_CUDA=0 (CPU-only, no GPU dependency)
"""

import json
import logging
import os
import signal
import sys
import time
from pathlib import Path
from typing import Optional

import redis

# Configure structured JSON logging
logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","phase":"2","msg":"%(message)s"}',
    stream=sys.stdout,
)
log = logging.getLogger("cardex.ai")

# Enforce thread limits BEFORE importing llama_cpp
os.environ["OMP_NUM_THREADS"] = "2"
os.environ["GGML_NTHREAD"] = "2"

from llama_cpp import Llama  # noqa: E402


# GBNF Grammar: forces LLM to emit exactly {tax_status, confidence} JSON
GRAMMAR_PATH = Path(__file__).parent / "grammar" / "tax_status.gbnf"

SYSTEM_PROMPT = """You are a tax classification engine for European used vehicle trade.
Given the vehicle listing text, determine the VAT/margin tax status.

Rules:
- If the listing mentions margin scheme, §25a, Differenzbesteuerung, or similar → REBU
- If the seller is clearly a VAT-registered dealer selling with invoice → DEDUCTIBLE
- If you cannot determine with high confidence → REQUIRES_HUMAN_AUDIT

Respond ONLY with the JSON object. No explanation."""

USER_TEMPLATE = """Classify this vehicle listing:

Source: {source}
Description: {description}
Seller Type: {seller_type}
Seller VAT: {seller_vat}
Country: {country}"""


class AIWorker:
    """Single-threaded Qwen2.5-Coder-7B worker with GBNF grammar enforcement."""

    def __init__(self, model_path: str, redis_url: str) -> None:
        self.running = True
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

        log.info("loading model: %s", model_path)
        grammar_text = GRAMMAR_PATH.read_text() if GRAMMAR_PATH.exists() else None

        self.llm = Llama(
            model_path=model_path,
            n_ctx=2048,
            n_threads=2,
            n_gpu_layers=0,  # CPU only — no GPU dependency
            verbose=False,
            use_mlock=True,  # Prevent paging to disk
        )
        self.grammar_text = grammar_text

        self.rdb = redis.Redis.from_url(redis_url, decode_responses=True)
        self.rdb.ping()
        log.info("redis connected, worker ready")

    def _shutdown(self, signum: int, frame: Optional[object]) -> None:
        log.info("shutdown signal received")
        self.running = False

    def run(self) -> None:
        """Main consumer loop on stream:l3_pending."""
        consumer_group = "cg_qwen_workers"
        consumer_name = f"qwen-{os.getpid()}"
        stream = "stream:l3_pending"

        while self.running:
            try:
                messages = self.rdb.xreadgroup(
                    groupname=consumer_group,
                    consumername=consumer_name,
                    streams={stream: ">"},
                    count=1,
                    block=5000,  # 5s block
                )
            except redis.ConnectionError:
                log.error("redis connection lost, retrying in 5s")
                time.sleep(5)
                continue

            if not messages:
                continue

            for _, entries in messages:
                for msg_id, data in entries:
                    self._process(msg_id, data, stream, consumer_group)

    def _process(self, msg_id: str, data: dict, stream: str, cg: str) -> None:
        start = time.monotonic()
        vehicle_ulid = data.get("vehicle_ulid", "unknown")

        try:
            prompt = USER_TEMPLATE.format(
                source=data.get("source", ""),
                description=data.get("description", "")[:500],  # Truncate for context
                seller_type=data.get("seller_type", ""),
                seller_vat=data.get("seller_vat", ""),
                country=data.get("country", ""),
            )

            response = self.llm.create_chat_completion(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=100,
                temperature=0.0,  # Deterministic
                grammar=self._load_grammar(),
            )

            text = response["choices"][0]["message"]["content"]
            result = json.loads(text)

            tax_status = result.get("tax_status", "REQUIRES_HUMAN_AUDIT")
            confidence = float(result.get("confidence", 0.0))

            # FAIL-CLOSED: confidence < 0.95 → force human audit
            if confidence < 0.95:
                tax_status = "REQUIRES_HUMAN_AUDIT"

            # Inject into L1 cache
            self.rdb.hset(
                f"dict:l1_tax",
                vehicle_ulid,
                json.dumps({"tax_status": tax_status, "confidence": confidence}),
            )

            latency_ms = (time.monotonic() - start) * 1000
            log.info(
                "classified vehicle=%s status=%s confidence=%.2f latency_ms=%.0f",
                vehicle_ulid, tax_status, confidence, latency_ms,
            )

            # ACK
            self.rdb.xack(stream, cg, msg_id)

        except Exception:
            log.exception("classification failed for vehicle=%s", vehicle_ulid)
            # Do NOT ack — message will be retried via XPENDING claim

    def _load_grammar(self):
        """Load GBNF grammar if available."""
        # TODO: Integrate with llama_cpp.LlamaGrammar
        return None


def main() -> None:
    model_path = os.environ.get("QWEN_MODEL_PATH", "C:/cardex-models/Qwen2.5-Coder-7B-Instruct-Q5_K_M.gguf")
    redis_url = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")

    worker = AIWorker(model_path, redis_url)
    worker.run()


if __name__ == "__main__":
    main()
