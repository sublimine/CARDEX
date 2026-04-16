"""
extractor.py — Extract structured data from Handelsregister / Kbis / Registro Mercantil PDFs.

Uses LayoutLMv3 (microsoft/layoutlmv3-base, 125M params) for token classification
(NER) over document images with spatial layout awareness.

Pipeline
--------
  PDF → pdf2image (one image per page) → pytesseract OCR (words + bboxes)
      → LayoutLMv3 processor → model.forward → NER tags
      → JSON output with confidence scores

Supported entity types
----------------------
  COMPANY_NAME        legal name of the entity
  REGISTRATION_NUMBER SIREN / HRB / NIF-CIF / KvK number
  ADDRESS             registered address
  LEGAL_REP           director / Geschäftsführer / représentant légal

Usage (subprocess, called from Go)
-----------------------------------
  python3 extractor.py --pdf /path/to/doc.pdf [--model microsoft/layoutlmv3-base]
  # → prints JSON to stdout

Usage (Python API)
------------------
  from extractor import extract_entities
  result = extract_entities("/path/to/doc.pdf")
  print(result)

Environment variables
---------------------
  LAYOUTLM_MODEL_PATH   local HuggingFace model dir or hub ID (default: microsoft/layoutlmv3-base)
  LAYOUTLM_MAX_PAGES    maximum pages to process per PDF (default: 10)
  LAYOUTLM_DEVICE       'cpu' or 'cuda' (default: cpu)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

_AVAILABLE_DEPS: dict[str, bool] = {}


def _check_dep(name: str) -> bool:
    if name in _AVAILABLE_DEPS:
        return _AVAILABLE_DEPS[name]
    try:
        __import__(name.split(".")[0])
        _AVAILABLE_DEPS[name] = True
    except ImportError:
        _AVAILABLE_DEPS[name] = False
    return _AVAILABLE_DEPS[name]


@dataclass
class ExtractedEntity:
    entity_type: str
    text: str
    confidence: float
    page: int
    bbox: list[int] = field(default_factory=list)


@dataclass
class ExtractionResult:
    pdf_path: str
    pages_processed: int
    entities: list[ExtractedEntity]
    model_used: str
    warnings: list[str] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(
            {
                "pdf_path": self.pdf_path,
                "pages_processed": self.pages_processed,
                "model_used": self.model_used,
                "warnings": self.warnings,
                "entities": [asdict(e) for e in self.entities],
            },
            ensure_ascii=False,
            indent=2,
        )


# ── LayoutLMv3 NER label schema ───────────────────────────────────────────────

# Fine-tuning target labels — in production these are learned from annotated PDFs.
# Here we provide a zero-shot heuristic using the token classification head
# pretrained on FUNSD/CORD-style tasks, remapped to our entity types.
#
# The base LayoutLMv3 model doesn't include a fine-tuned NER head for
# Handelsregister entities — in practice you'd fine-tune on 200–500 annotated pages.
# This implementation provides the scaffolding with a keyword-heuristic fallback
# that activates when the model isn't fine-tuned.

ENTITY_LABELS = {
    "B-COMPANY_NAME": "COMPANY_NAME",
    "I-COMPANY_NAME": "COMPANY_NAME",
    "B-REGISTRATION_NUMBER": "REGISTRATION_NUMBER",
    "I-REGISTRATION_NUMBER": "REGISTRATION_NUMBER",
    "B-ADDRESS": "ADDRESS",
    "I-ADDRESS": "ADDRESS",
    "B-LEGAL_REP": "LEGAL_REP",
    "I-LEGAL_REP": "LEGAL_REP",
    "O": None,
}

# Keyword heuristics for zero-shot / fallback extraction
_KEYWORD_HINTS = {
    "REGISTRATION_NUMBER": [
        "HRB", "HRA", "SIREN", "SIRET", "NIF", "CIF", "KvK",
        "registr", "Handelsregister", "Registre du commerce",
        "Registro Mercantil",
    ],
    "LEGAL_REP": [
        "Geschäftsführer", "Vorstand", "gérant", "directeur",
        "représentant", "administrador", "consejero",
        "Managing Director", "CEO",
    ],
    "ADDRESS": [
        "Straße", "str.", "Avenue", "Rue", "Calle", "Plaza",
        "GmbH-Sitz", "siège social", "domicilio",
    ],
}


def _load_layoutlmv3(model_path: str, device: str = "cpu"):
    """Load LayoutLMv3 processor and model. Returns (processor, model) or (None, None)."""
    if not (_check_dep("transformers") and _check_dep("torch")):
        log.warning(
            "transformers / torch not installed — using heuristic fallback. "
            "Install: pip install transformers torch Pillow"
        )
        return None, None
    from transformers import (
        LayoutLMv3Processor,
        LayoutLMv3ForTokenClassification,
    )
    import torch

    try:
        processor = LayoutLMv3Processor.from_pretrained(model_path)
        # Try fine-tuned NER model; fall back to base for feature extraction only
        try:
            model = LayoutLMv3ForTokenClassification.from_pretrained(model_path)
        except Exception:
            # Base model without NER head — will use heuristic post-processing
            from transformers import LayoutLMv3Model
            model = None
            log.warning(
                "LayoutLMv3 loaded without NER head (base model). "
                "Using keyword heuristics for entity classification. "
                "Fine-tune on annotated PDFs for production accuracy."
            )
        if model is not None:
            model.eval()
            model.to(device)
        return processor, model
    except Exception as exc:
        log.warning("Failed to load LayoutLMv3: %s — falling back to heuristics", exc)
        return None, None


def _pdf_to_images(pdf_path: str, max_pages: int = 10) -> list:
    """Convert PDF pages to PIL Image objects using pdf2image."""
    if not _check_dep("pdf2image"):
        raise ImportError(
            "pdf2image is required for PDF processing. "
            "Install: pip install pdf2image\n"
            "Also requires poppler: apt-get install poppler-utils"
        )
    from pdf2image import convert_from_path
    images = convert_from_path(pdf_path, first_page=1, last_page=max_pages)
    return images


def _ocr_image(image) -> tuple[list[str], list[list[int]]]:
    """Run pytesseract OCR on a PIL Image. Returns (words, bboxes in [x1,y1,x2,y2] form)."""
    if not _check_dep("pytesseract"):
        raise ImportError(
            "pytesseract is required for OCR. "
            "Install: pip install pytesseract\n"
            "Also requires tesseract: apt-get install tesseract-ocr"
        )
    import pytesseract
    from pytesseract import Output

    width, height = image.size
    data = pytesseract.image_to_data(image, output_type=Output.DICT, lang="deu+fra+spa+eng")

    words, bboxes = [], []
    for i, word in enumerate(data["text"]):
        conf = int(data["conf"][i])
        if conf < 0 or not word.strip():
            continue
        x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        # Normalise to 0–1000 range (LayoutLMv3 convention)
        bbox = [
            int(x / width * 1000),
            int(y / height * 1000),
            int((x + w) / width * 1000),
            int((y + h) / height * 1000),
        ]
        words.append(word.strip())
        bboxes.append(bbox)
    return words, bboxes


def _heuristic_entities(words: list[str], bboxes: list[list[int]], page: int) -> list[ExtractedEntity]:
    """
    Rule-based fallback when LayoutLMv3 is not available or not fine-tuned.

    Groups consecutive words into candidate spans by proximity, then applies
    keyword hints to classify the span type.
    """
    entities = []
    text_block = " ".join(words)

    import re

    # Registration numbers — strong patterns
    reg_patterns = [
        (r"\bHRB?\s*\d{3,7}\b", "REGISTRATION_NUMBER", 0.90),
        (r"\b\d{3}\s?\d{3}\s?\d{3}\b", "REGISTRATION_NUMBER", 0.75),   # SIREN
        (r"\b[A-Z]-?\d{5,9}\b", "REGISTRATION_NUMBER", 0.72),           # NIF
        (r"\bKvK\s*[-:]?\s*\d{8}\b", "REGISTRATION_NUMBER", 0.88),
        (r"\b\d{2}\s\d{3}\s\d{3}\s\d{5}\b", "REGISTRATION_NUMBER", 0.80),  # SIRET
    ]
    for pattern, etype, conf in reg_patterns:
        for m in re.finditer(pattern, text_block, re.IGNORECASE):
            entities.append(ExtractedEntity(
                entity_type=etype,
                text=m.group(0).strip(),
                confidence=conf,
                page=page,
                bbox=[],
            ))

    # GmbH / SA / SL company name heuristic
    name_pattern = r"[A-ZÄÖÜ][A-Za-zäöüÄÖÜß\-\s&,\.]{4,60}(?:GmbH|AG|SE|KGaA|OHG|SA|SAS|SARL|SL|SLU|SRL|BV|NV)\b"
    for m in re.finditer(name_pattern, text_block):
        entities.append(ExtractedEntity(
            entity_type="COMPANY_NAME",
            text=m.group(0).strip(),
            confidence=0.78,
            page=page,
            bbox=[],
        ))

    # Legal representative lines
    legal_rep_pattern = r"(?:Geschäftsführer|gérant|représentant légal|administrador|consejero|Vorstand)[:\s]+([A-ZÄÖÜ][a-zäöü]+\s[A-ZÄÖÜ][a-zäöü]+)"
    for m in re.finditer(legal_rep_pattern, text_block, re.IGNORECASE):
        entities.append(ExtractedEntity(
            entity_type="LEGAL_REP",
            text=m.group(1).strip(),
            confidence=0.82,
            page=page,
            bbox=[],
        ))

    return entities


def _layoutlmv3_entities(
    processor,
    model,
    image,
    words: list[str],
    bboxes: list[list[int]],
    page: int,
    id2label: dict[int, str],
    device: str = "cpu",
) -> list[ExtractedEntity]:
    import torch

    if not words:
        return []

    encoding = processor(
        image,
        words,
        boxes=bboxes,
        return_tensors="pt",
        truncation=True,
        max_length=512,
        padding="max_length",
    )
    encoding = {k: v.to(device) for k, v in encoding.items()}

    with torch.no_grad():
        outputs = model(**encoding)

    logits = outputs.logits.squeeze(0)
    probs = torch.softmax(logits, dim=-1)
    predicted_ids = logits.argmax(dim=-1).tolist()
    token_probs = probs.max(dim=-1).values.tolist()

    word_ids = encoding.word_ids(batch_index=0) if hasattr(encoding, "word_ids") else [None] * len(predicted_ids)

    entities, current_entity = [], None
    for token_idx, (pred_id, prob) in enumerate(zip(predicted_ids, token_probs)):
        word_idx = word_ids[token_idx] if word_ids else None
        if word_idx is None:
            continue
        label = id2label.get(pred_id, "O")
        etype = ENTITY_LABELS.get(label)

        if label.startswith("B-") and etype:
            if current_entity:
                entities.append(current_entity)
            bbox = bboxes[word_idx] if word_idx < len(bboxes) else []
            current_entity = ExtractedEntity(
                entity_type=etype,
                text=words[word_idx] if word_idx < len(words) else "",
                confidence=round(prob, 4),
                page=page,
                bbox=bbox,
            )
        elif label.startswith("I-") and current_entity and current_entity.entity_type == etype:
            if word_idx < len(words):
                current_entity.text += " " + words[word_idx]
                current_entity.confidence = round(
                    (current_entity.confidence + prob) / 2, 4
                )
        else:
            if current_entity:
                entities.append(current_entity)
                current_entity = None

    if current_entity:
        entities.append(current_entity)

    return entities


def extract_entities(
    pdf_path: str,
    model_path: Optional[str] = None,
    max_pages: int = 10,
    device: Optional[str] = None,
) -> ExtractionResult:
    """
    Extract structured entities from a PDF registry document.

    When LayoutLMv3 + OCR stack is available: uses model inference.
    When not available: falls back to regex/keyword heuristics on raw PDF text.
    """
    if model_path is None:
        model_path = os.getenv("LAYOUTLM_MODEL_PATH", "microsoft/layoutlmv3-base")
    if device is None:
        device = os.getenv("LAYOUTLM_DEVICE", "cpu")
    if max_pages is None:
        max_pages = int(os.getenv("LAYOUTLM_MAX_PAGES", "10"))

    warnings: list[str] = []
    all_entities: list[ExtractedEntity] = []

    # Try to load LayoutLMv3
    processor, model = _load_layoutlmv3(model_path, device)
    model_used = model_path

    # Determine id→label mapping for fine-tuned model
    id2label: dict[int, str] = {}
    if model is not None and hasattr(model, "config"):
        id2label = getattr(model.config, "id2label", {})

    try:
        images = _pdf_to_images(pdf_path, max_pages=max_pages)
    except ImportError as e:
        warnings.append(str(e))
        # Last resort: try PyMuPDF / pdfminer for plain text extraction
        images = []
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(pdf_path)
            for page_num, page in enumerate(doc[:max_pages]):
                text = page.get_text()
                fake_words = text.split()
                fake_bboxes = [[0, 0, 100, 20]] * len(fake_words)
                if processor and model:
                    pass  # Can't use LayoutLMv3 without images
                ents = _heuristic_entities(fake_words, fake_bboxes, page_num + 1)
                all_entities.extend(ents)
            return ExtractionResult(
                pdf_path=pdf_path,
                pages_processed=min(len(doc), max_pages),
                entities=all_entities,
                model_used="heuristic-pymupdf",
                warnings=warnings,
            )
        except ImportError:
            warnings.append("pdf2image and PyMuPDF both unavailable — cannot process PDF")
            return ExtractionResult(
                pdf_path=pdf_path,
                pages_processed=0,
                entities=[],
                model_used="none",
                warnings=warnings,
            )

    pages_processed = len(images)
    for page_num, image in enumerate(images, start=1):
        try:
            words, bboxes = _ocr_image(image)
        except ImportError as e:
            warnings.append(f"OCR unavailable on page {page_num}: {e}")
            continue

        if not words:
            continue

        if processor is not None and model is not None and id2label:
            try:
                page_ents = _layoutlmv3_entities(
                    processor, model, image, words, bboxes, page_num, id2label, device
                )
            except Exception as exc:
                warnings.append(f"LayoutLMv3 inference failed on page {page_num}: {exc}")
                page_ents = _heuristic_entities(words, bboxes, page_num)
        else:
            if not warnings:
                warnings.append(
                    "LayoutLMv3 not fine-tuned for registry NER — using heuristic fallback. "
                    "Fine-tune on annotated Handelsregister/Kbis/Nota Simple pages for best results."
                )
            page_ents = _heuristic_entities(words, bboxes, page_num)

        all_entities.extend(page_ents)

    # Deduplicate entities with identical text+type
    seen = set()
    deduped = []
    for e in all_entities:
        key = (e.entity_type, e.text.strip())
        if key not in seen:
            seen.add(key)
            deduped.append(e)

    return ExtractionResult(
        pdf_path=pdf_path,
        pages_processed=pages_processed,
        entities=deduped,
        model_used=model_used,
        warnings=warnings,
    )


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stderr,
    )
    p = argparse.ArgumentParser(
        description="Extract entities from registry PDFs using LayoutLMv3"
    )
    p.add_argument("--pdf", required=True, help="Path to PDF file")
    p.add_argument("--model", default=None, help="LayoutLMv3 model path or HF hub ID")
    p.add_argument("--max-pages", type=int, default=10)
    p.add_argument("--device", default="cpu")
    args = p.parse_args()

    if not Path(args.pdf).exists():
        log.error("PDF not found: %s", args.pdf)
        sys.exit(1)

    result = extract_entities(
        pdf_path=args.pdf,
        model_path=args.model,
        max_pages=args.max_pages,
        device=args.device,
    )
    # JSON → stdout (consumed by Go caller via os/exec)
    print(result.to_json())


if __name__ == "__main__":
    main()
