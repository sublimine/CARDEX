# E13 — VLM Screenshot Vision

> **Sprint:** 26 | **Branch:** `sprint/26-vlm-e13`
> **Priority in cascade:** 100 (after E10 email, before E12 manual review)
> **Status:** Implemented — opt-in via `VLM_ENABLED=true`

---

## 1. Purpose

E13 is the last automated extraction strategy. It activates when all structured-data strategies (E01–E10) have failed to produce usable vehicle data for a dealer — typically because the dealer site is fully JS-rendered with no accessible JSON/HTML structure.

E13 fetches the visible listing images from the dealer's page and sends them to a Vision Language Model (VLM) with a structured JSON prompt. The model extracts vehicle fields directly from the visual content of the image.

---

## 2. Model Selection for Hetzner CX42

Target hardware: **4 vCPU, 16 GB RAM, CPU-only** (no GPU).

| Model | Size (Q4_K_M) | RAM (inferred) | Latency/image (CPU) | Verdict |
|---|---|---|---|---|
| Phi-3.5-vision-instruct | 4.2B | ~3 GB | 30–60 s | **Primary target** |
| Moondream2 | 1.9B | ~1.5 GB | 15–30 s | Fallback if Phi-3.5 OOMs |
| Florence-2-base | 0.2B | <500 MB | 5–10 s | Lightweight fallback |

**Deployment:** All models served via `ollama` on `localhost:11434`. No external API calls; no data leaves the Hetzner server.

**Concurrent E13 runs:** Maximum 1 (CPU-bound). Adjust `EXTRACTION_WORKERS=1` when `VLM_ENABLED=true` to avoid OOM.

---

## 3. Architecture

```
Orchestrator
  └── E13.Applicable(dealer) → true (universal fallback, guarded by VLM_ENABLED)
       └── E13.Extract(ctx, dealer)
            ├── 1. HTTP GET dealer.URLRoot → parse <img> tags (goquery)
            ├── 2. Filter candidate listing images (JPEG/PNG/WebP, >4 KB, not icons)
            ├── 3. For each image (up to 10):
            │    ├── Download image bytes (10 MB cap)
            │    ├── VLMClient.SendImage(ctx, bytes, vlmPrompt)   ← injectable
            │    ├── parseVLMResponse(raw) → VehicleRaw + field count
            │    └── Tag: AdditionalFields["extraction_method"] = "e13_vlm"
            │         AdditionalFields["ai_generated"] = {is_ai_generated: true, model, generated_at}
            └── 4. Return ExtractionResult; NextFallback = "E12" always set
```

### VLMClient interface

```go
type VLMClient interface {
    SendImage(ctx context.Context, image []byte, prompt string) (string, error)
}
```

| Implementation | Used in | Description |
|---|---|---|
| `OllamaClient` | Production | HTTP POST `{endpoint}/api/generate` with base64 image |
| `MockClient` | Unit tests | Returns canned response; no network I/O |

---

## 4. Extraction Prompt

```
Extract vehicle listing data from this image.
Return ONLY a JSON object with the following fields (omit fields not visible in the image):
{
  "make": "brand name",
  "model": "model name",
  "year": 2020,
  "price": 25000,
  "price_currency": "EUR",
  "mileage_km": 45000,
  "fuel_type": "diesel|gasoline|hybrid|electric|lpg|cng|hydrogen",
  "transmission": "manual|automatic|semi-automatic",
  "color": "color name",
  "vin": "VIN if visible",
  "dealer_name": "dealer company name",
  "dealer_location": "city, country"
}
Return only the JSON object. No explanation, no markdown, no code fences.
```

The parser (`parseVLMResponse`) handles model outputs that wrap JSON in markdown code fences or add a preamble sentence — both patterns observed in small open-source models.

---

## 5. AI Act Art. 50(2) Compliance

Every `VehicleRaw` produced by E13 carries:

```json
{
  "extraction_method": "e13_vlm",
  "ai_generated": {
    "is_ai_generated": true,
    "model": "phi3.5-vision:latest",
    "generated_at": "2026-04-16T12:00:00Z"
  }
}
```

These fields are stored in `VehicleRaw.AdditionalFields`. Downstream, the quality pipeline's V11 validator checks for `ai_generated.is_ai_generated=true` and enforces the `AIGeneratedMetadata` struct (see `quality/internal/nlg/aiact.go`).

---

## 6. Configuration

| Env var | Default | Description |
|---|---|---|
| `VLM_ENABLED` | `false` | Enable E13. Must be explicitly set to `true`. |
| `VLM_BACKEND` | `ollama` | Backend: `ollama` or `mock` (tests). |
| `VLM_MODEL` | `phi3.5-vision:latest` | Model tag in ollama. |
| `VLM_ENDPOINT` | `http://localhost:11434` | ollama server base URL. |
| `VLM_TIMEOUT` | `120s` | Per-image inference timeout (Go duration string). |
| `VLM_MAX_RETRIES` | `2` | Retry attempts on transient errors. |
| `EXTRACTION_SKIP_E13` | `false` | Skip E13 even if `VLM_ENABLED=true`. |
| `EXTRACTION_WORKERS` | `4` | Recommend setting to `1` when VLM is enabled. |

### ollama setup (Hetzner CX42)

```bash
# Install ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull Phi-3.5 vision (primary model, ~3 GB download)
ollama pull phi3.5-vision:latest

# Fallback models
ollama pull moondream2          # ~1.5 GB
ollama pull florence-2-base     # <500 MB

# Start ollama server (auto-started by systemd after install)
systemctl status ollama

# Verify
curl http://localhost:11434/api/tags | jq '.models[].name'
```

---

## 7. Metrics

| Metric | Type | Labels | Description |
|---|---|---|---|
| `cardex_extraction_e13_requests_total` | Counter | `status={success,error,timeout}` | Per-image VLM inference outcomes |
| `cardex_extraction_e13_latency_seconds` | Histogram | — | Per-image inference latency; buckets: 5–180 s |
| `cardex_extraction_e13_fields_extracted` | Gauge | — | Avg vehicle fields extracted per image in last run |

---

## 8. Error Handling and Fallback

| Condition | Error code | Behaviour |
|---|---|---|
| Dealer page unreachable | `HTTP_FETCH_ERROR` | Result with 0 vehicles, NextFallback=E12 |
| No images on page | `NO_IMAGES_FOUND` | Same |
| Image download failure | `IMAGE_FETCH_ERROR` | Skip image, continue with next |
| VLM context timeout | `TIMEOUT` | Skip image, `e13_requests_total{timeout}++` |
| VLM returns non-JSON | `PARSE_ERROR` | Skip image, `e13_requests_total{error}++` |
| All images fail | — | 0 vehicles, NextFallback=E12 → manual review |

**NextFallback is always set to "E12"** regardless of outcome. E13 never prevents the cascade from reaching manual review.

---

## 9. Test Coverage

| Test | Type | File |
|---|---|---|
| `TestE13_Applicable` | Unit | `e13_test.go` |
| `TestE13_ApplicableVLMRequired` | Unit | `e13_test.go` |
| `TestE13_IDPriority` | Unit | `e13_test.go` |
| `TestE13_MockNoImages` | Unit | `e13_test.go` |
| `TestE13_MockVLMTimeout` | Unit | `e13_test.go` |
| `TestStripMarkdownFence` (4 subtests) | Unit | `e13_test.go` |
| `TestParseVLMResponse_FullFields` | Unit | `e13_test.go` |
| `TestParseVLMResponse_EmptyInput` | Unit | `e13_test.go` |
| `TestParseVLMResponse_InvalidYear` | Unit | `e13_test.go` |

**Integration test** (requires running ollama):

```go
//go:build vlm
// Run with: go test -tags vlm -v ./internal/extractor/e13_vlm_vision/...
```

Not committed to CI (optional, dev-only). Create `e13_integration_test.go` when a VLM dev instance is available.

---

## 10. Operational Notes

- **Resource isolation:** E13 runs at priority 100, only when all E01–E10 strategies have returned empty results. A single E13 run on CX42 CPU takes 5–10 min for 10 images. Do not run >1 concurrent worker with VLM enabled.
- **Cost model:** ~0 EUR/request (local inference, no API keys).
- **Accuracy expectation:** Phi-3.5 extracts 5–8 fields reliably on clean listing images; VIN requires very high resolution. Partial results are acceptable — V20 composite scoring handles gaps.
- **Iframe prohibition:** E13 fetches standalone image URLs from `<img>` tags. It does NOT embed or iframe third-party dealer pages (VG Bild-Kunst C-392/19 compliance).
