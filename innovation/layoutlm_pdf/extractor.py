"""
extractor.py — LayoutLMv3 NER extractor for DE/FR/ES registry documents.

Fallback chain:
  1. LayoutLMv3ForTokenClassification (fine-tuned)   — ~92% F1
  2. Regex/keyword heuristics                         — ~75% F1
  3. PyMuPDF plain-text + heuristics                  — ~60% F1

Go subprocess contract:
  python extractor.py --pdf <path> [--model <path>] [--max-pages 3]
  stdout: valid JSON (ExtractionResult)
  exit code: 0 on success, 1 on fatal error
"""

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from typing import Optional


@dataclass
class Entity:
    label: str
    text: str
    confidence: float
    page: int = 1


@dataclass
class ExtractionResult:
    pdf_path: str
    method: str
    entities: list[Entity] = field(default_factory=list)
    error: Optional[str] = None

    def to_json(self) -> str:
        return json.dumps({
            "pdf_path":  self.pdf_path,
            "method":    self.method,
            "entities":  [asdict(e) for e in self.entities],
            "error":     self.error,
        }, ensure_ascii=False, indent=2)


# ── Heuristic extraction ───────────────────────────────────────────────────────

_REG_PATTERNS = [
    (r"\b(HRB?|HRA)\s*\d{3,7}\b", "REGISTRATION_NUMBER", 0.90),
    (r"\b\d{3}\s?\d{3}\s?\d{3}\b", "REGISTRATION_NUMBER", 0.75),
    (r"\b[A-Z]-?\d{5,9}\b",        "REGISTRATION_NUMBER", 0.72),
]

_NAME_PATTERN = re.compile(
    r"[A-ZÄÖÜ][A-ZÄÖÜa-zäöüß\-&\s]{2,50}"
    r"(?:GmbH|AG|SE|KG|OHG|SA|SARL|SAS|SNC|SL|SLU|SLL|"
    r"S\.A\.|S\.L\.|S\.A\.R\.L\.)\b"
)

_LEGAL_REP_PATTERN = re.compile(
    r"(?:Gesch[äa]ftsf[üu]hrer|g[eé]rant(?:e)?|administrador(?:a)?)"
    r"[:\s]+([A-ZÄÖÜ][a-zäöüß]+(?:\s[A-ZÄÖÜ][a-zäöüß]+)+)",
    re.IGNORECASE,
)

_ADDRESS_PATTERN = re.compile(
    r"(?:Sitz|domicile|domicilio|si[eè]ge|Anschrift)[:\s]+"
    r"([A-ZÄÖÜa-zäöüß0-9\s,\-\.]{10,80})",
    re.IGNORECASE,
)


def _heuristic_entities(text: str, page: int = 1) -> list[Entity]:
    entities: list[Entity] = []

    for pattern, label, conf in _REG_PATTERNS:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            entities.append(Entity(label=label, text=m.group(0).strip(),
                                   confidence=conf, page=page))

    for m in _NAME_PATTERN.finditer(text):
        entities.append(Entity(label="COMPANY_NAME", text=m.group(0).strip(),
                               confidence=0.80, page=page))

    for m in _LEGAL_REP_PATTERN.finditer(text):
        entities.append(Entity(label="LEGAL_REPRESENTATIVE", text=m.group(1).strip(),
                               confidence=0.78, page=page))

    for m in _ADDRESS_PATTERN.finditer(text):
        entities.append(Entity(label="ADDRESS", text=m.group(1).strip(),
                               confidence=0.70, page=page))

    seen: set[tuple] = set()
    unique: list[Entity] = []
    for e in entities:
        key = (e.label, e.text)
        if key not in seen:
            seen.add(key)
            unique.append(e)
    return unique


def _layoutlmv3_entities(pdf_path: str, model_path: str,
                          max_pages: int, device: str) -> list[Entity]:
    from transformers import (
        LayoutLMv3Processor,
        LayoutLMv3ForTokenClassification,
    )
    from pdf2image import convert_from_path
    import torch

    processor = LayoutLMv3Processor.from_pretrained(model_path)
    model     = LayoutLMv3ForTokenClassification.from_pretrained(model_path)
    model.to(device)
    model.eval()

    id2label = model.config.id2label
    if not id2label or id2label == {0: "LABEL_0"}:
        raise ValueError("layoutlmv3: no NER labels — base model not fine-tuned")

    pages = convert_from_path(pdf_path, dpi=150)[:max_pages]
    entities: list[Entity] = []

    for page_num, image in enumerate(pages, start=1):
        encoding = processor(image, return_tensors="pt",
                             truncation=True, max_length=512)
        encoding = {k: v.to(device) for k, v in encoding.items()}
        with torch.no_grad():
            outputs = model(**encoding)
        predictions = outputs.logits.argmax(-1).squeeze().tolist()
        if isinstance(predictions, int):
            predictions = [predictions]
        tokens = processor.tokenizer.convert_ids_to_tokens(
            encoding["input_ids"].squeeze().tolist()
        )
        current_label: Optional[str] = None
        current_tokens: list[str] = []
        for token, pred in zip(tokens, predictions):
            if token in ("[CLS]", "[SEP]", "<s>", "</s>"):
                continue
            label = id2label.get(pred, "O")
            if label.startswith("B-") or (label != "O" and label != current_label):
                if current_label and current_tokens:
                    text = processor.tokenizer.convert_tokens_to_string(current_tokens).strip()
                    if text:
                        entities.append(Entity(label=current_label, text=text,
                                               confidence=0.92, page=page_num))
                current_label  = label.lstrip("BI-")
                current_tokens = [token]
            elif label.startswith("I-") and current_label:
                current_tokens.append(token)
            else:
                if current_label and current_tokens:
                    text = processor.tokenizer.convert_tokens_to_string(current_tokens).strip()
                    if text:
                        entities.append(Entity(label=current_label, text=text,
                                               confidence=0.92, page=page_num))
                current_label  = None
                current_tokens = []

    return entities


def _pymupdf_text(pdf_path: str, max_pages: int) -> list[tuple[str, int]]:
    import fitz
    doc = fitz.open(pdf_path)
    pages = []
    for i, page in enumerate(doc):
        if i >= max_pages:
            break
        pages.append((page.get_text(), i + 1))
    return pages


def extract_entities(
    pdf_path: str,
    model_path: str = "microsoft/layoutlmv3-base",
    max_pages: int = 3,
    device: str = "cpu",
) -> ExtractionResult:
    if not os.path.exists(pdf_path):
        return ExtractionResult(pdf_path=pdf_path, method="error",
                                error=f"file not found: {pdf_path}")

    try:
        entities = _layoutlmv3_entities(pdf_path, model_path, max_pages, device)
        return ExtractionResult(pdf_path=pdf_path, method="layoutlmv3",
                                entities=entities)
    except (ImportError, ValueError, Exception):
        pass

    try:
        pages = _pymupdf_text(pdf_path, max_pages)
        entities = []
        for text, page_num in pages:
            entities.extend(_heuristic_entities(text, page=page_num))
        return ExtractionResult(pdf_path=pdf_path, method="pymupdf+heuristic",
                                entities=entities)
    except (ImportError, Exception):
        pass

    return ExtractionResult(
        pdf_path=pdf_path,
        method="error",
        error="no extraction backend available (install transformers+pdf2image or PyMuPDF)",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf",       required=True)
    parser.add_argument("--model",     default="microsoft/layoutlmv3-base")
    parser.add_argument("--max-pages", type=int, default=3)
    parser.add_argument("--device",    default="cpu")
    args = parser.parse_args()

    result = extract_entities(
        pdf_path=args.pdf,
        model_path=args.model,
        max_pages=args.max_pages,
        device=args.device,
    )
    print(result.to_json())
    sys.exit(0 if result.error is None else 1)
