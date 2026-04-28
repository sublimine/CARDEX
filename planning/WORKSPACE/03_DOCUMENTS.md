# CARDEX Workspace — Document Generator

**Sprint:** 43  
**Branch:** `sprint/43-documents`  
**Module:** `workspace/internal/documents/`  
**Status:** Implemented

---

## Overview

The document generator produces PDF files for the four core document types used in CARDEX Workspace:

| Type | File | Description |
|------|------|-------------|
| `contract` | `contract.go` | Purchase/sale contracts for DE/FR/ES/NL |
| `invoice` | `invoice.go` | EU-compliant invoices with VAT scheme support |
| `vehicle_sheet` | `vehicle_sheet.go` | 1-page vehicle technical sheet |
| `transport_doc` | `transport_doc.go` | Simplified CMR-like transport accompaniment |

All PDFs are generated in-process (no external binary, no CGO) using `github.com/go-pdf/fpdf` (pure-Go, active fork of jung-kurt/gofpdf).

---

## Library Decision

**Chosen: `github.com/go-pdf/fpdf v0.9.0`**

| Library | Verdict | Reason |
|---------|---------|--------|
| go-pdf/fpdf | ✅ Chosen | Pure Go, no CGO, Latin-1 fonts (Helvetica) cover DE/FR/ES/NL, 5k+ stars, actively maintained |
| jung-kurt/gofpdf | ❌ | Archived; go-pdf/fpdf is its active fork |
| pdfcpu | ❌ | Focused on manipulation (merge/split/encrypt), not generation |
| maroto | ❌ | Higher-level but adds complexity and diverges from standard fpdf API |
| wkhtmltopdf/Chromium | ❌ | Requires external binary; not suitable for containerised deployment |

Latin-1 encoding via built-in Helvetica covers all required characters for DE/FR/ES/NL without loading external TTF fonts.

---

## Architecture

```
workspace/internal/documents/
├── model.go          — Request/response types, DocType constants
├── schema.go         — SQLite schema (crm_documents, crm_invoice_seq), DB functions
├── template.go       — PDF primitives: newPDF, drawHeader, drawPartyBox, drawSectionTitle, etc.
├── contract.go       — GenerateContract (DE/FR/ES/NL locale map)
├── invoice.go        — GenerateInvoice (standard/reverse_charge/margin VAT schemes)
├── vehicle_sheet.go  — GenerateVehicleSheet (1-page technical sheet)
├── transport_doc.go  — GenerateTransportDoc (CMR-like accompaniment)
├── service.go        — Service struct orchestrating generation + disk + DB persistence
├── handler.go        — HTTP handler (5 endpoints)
└── documents_test.go — 26 tests
```

---

## Storage Layout

```
{baseDir}/
└── {tenant_id}/
    └── documents/
        ├── contract_{id}.pdf
        ├── invoice_{id}.pdf
        ├── vehicle_sheet_{id}.pdf
        └── transport_doc_{id}.pdf
```

`baseDir` defaults to `media/` in the workspace service binary.

### DB Tables

**`crm_documents`** — one row per generated PDF:
```sql
CREATE TABLE crm_documents (
    id          TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL,
    type        TEXT NOT NULL,                -- "contract"|"invoice"|"vehicle_sheet"|"transport_doc"
    vehicle_id  TEXT,
    deal_id     TEXT,
    file_path   TEXT NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

**`crm_invoice_seq`** — per-tenant per-year invoice counter:
```sql
CREATE TABLE crm_invoice_seq (
    tenant_id  TEXT NOT NULL,
    year       INTEGER NOT NULL,
    last_seq   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, year)
);
```

Invoice number format: `{tenantPrefix}-{year}-{seq:05d}` (e.g., `DLR-2026-00001`).  
Increment is atomic via SQLite transaction with `ON CONFLICT DO UPDATE SET last_seq = last_seq + 1`.

---

## Contracts — Country Locales

| Country | Title | Legal Basis |
|---------|-------|-------------|
| DE | Kaufvertrag für Gebrauchtwagen | § 476 BGB — 12-month warranty for B2C used vehicles |
| FR | Bon de Commande — Véhicule d'Occasion | Art. L.217-1 Code consommation — 12 months |
| ES | Contrato de Compraventa de Vehículo Usado | RDL 1/2007 art. 136 — 12 months |
| NL | Koopovereenkomst Gebruikte Auto | art. 7:23 BW — 12 months (consumentenkoop) |

Each locale carries 5 localised clauses covering: sold-as-seen, legal warranty, title transfer at full payment, key/document handover, written-form requirement for amendments.

---

## Invoices — VAT Schemes

| Scheme | VAT Line | Legal Reference |
|--------|----------|-----------------|
| `standard` | `VAT {rate}%` + calculated amount | National legislation |
| `reverse_charge` | `VAT — Reverse charge, Art. 196 Directive 2006/112/EC` at 0% | Intra-EU B2B |
| `margin` | `Margin scheme — Art. 313 Directive 2006/112/EC` | Used goods margin scheme |

The invoice footer renders the appropriate legal notice for each scheme.

---

## Vehicle Sheet Layout

1. Coloured title banner (dark blue): `{Make} {Model} ({Year})`
2. Dealer sub-banner (medium blue): dealer name, phone, email
3. Two-column technical specifications grid (make/model/year/mileage/fuel/VIN/color/power/body/registration)
4. Equipment & Features in 3-column list
5. Price box (dark blue, large font): `Price: {amount} (incl. VAT)`
6. QR placeholder box (right of price): listing URL or "QR" placeholder
7. Footer legal note (7pt grey): prices subject to change + VIN
8. Dealer branding bar (dark blue): name + phone + email in all-caps

---

## Transport Document Layout

1. Transport banner (blue) + CMR disclaimer sub-line
2. Document Reference section: ID = `TRANSPORT-{vehicleID}`, date
3. Transport Route: origin, destination, carrier
4. Vehicle Details: make/model/year/VIN/registration/mileage/color
5. Parties: Sender (Expéditeur) + Recipient (Destinataire) side-by-side
6. Notes/Remarks (optional)
7. Vehicle Condition checklist: 5 checkboxes (damage, tyres, keys, documents, fuel level)
8. Double signature block: Sender + Recipient, then Carrier + Date of receipt

Note: This is an **internal transport accompaniment document**, NOT an official CMR under the Convention on the Contract for the International Carriage of Goods by Road. Official CMR requires a homologated printed form.

---

## HTTP API

All endpoints are mounted by `documents.Handler(svc)` and prefixed with `/api/v1/documents/`.

| Method | Path | Body / Params | Response |
|--------|------|---------------|----------|
| POST | `/api/v1/documents/contract` | `ContractRequest` JSON | `GenerateResult` (201) |
| POST | `/api/v1/documents/invoice` | `InvoiceRequest` JSON | `GenerateResult` (201) |
| POST | `/api/v1/documents/vehicle-sheet` | `VehicleSheetRequest` JSON | `GenerateResult` (201) |
| POST | `/api/v1/documents/transport` | `TransportRequest` JSON | `GenerateResult` (201) |
| GET  | `/api/v1/documents/{id}/download` | — | PDF file (200, `Content-Type: application/pdf`) |

`GenerateResult`:
```json
{
  "document_id": "1745000000000000000",
  "file_path": "media/tenant1/documents/contract_1745000000000000000.pdf",
  "download_url": "/api/v1/documents/1745000000000000000/download"
}
```

---

## Tests (26 total)

| Test | What it verifies |
|------|-----------------|
| `TestGenerateContract_DE` | DE PDF is valid (`%PDF` magic), non-empty |
| `TestGenerateContract_FR` | FR PDF generated without error |
| `TestGenerateContract_ES` | ES PDF generated without error |
| `TestGenerateContract_NL` | NL PDF generated without error |
| `TestGenerateContract_UnsupportedCountry` | Error returned for unknown country code |
| `TestGenerateInvoice_Standard` | Standard VAT invoice is a valid PDF |
| `TestGenerateInvoice_ReverseCharge` | Reverse-charge intra-EU invoice (0% VAT) |
| `TestGenerateInvoice_MarginScheme` | Margin scheme invoice |
| `TestGenerateVehicleSheet` | Full sheet with features + listing URL |
| `TestGenerateVehicleSheet_MinimalFields` | Sheet with no optional fields |
| `TestGenerateTransportDoc` | Transport doc with notes, full parties |
| `TestGenerateTransportDoc_NoNotes` | Transport doc without optional notes |
| `TestService_GenerateContract_StoresFile` | PDF written to disk, DocumentID/DownloadURL set |
| `TestService_GetDocumentFile` | Retrieve stored doc record by ID |
| `TestService_GetDocumentFile_NotFound` | Error on missing ID |
| `TestNextInvoiceNumber_Unique` | 10 sequential calls produce 10 distinct numbers |
| `TestNextInvoiceNumber_Format` | First number is `{prefix}-{year}-00001` |
| `TestNextInvoiceNumber_MultiTenant` | Sequences are per-tenant, independent |
| `TestHandlerContract_Created` | POST contract → 201 + valid JSON body |
| `TestHandlerContract_MissingCountry` | POST without country → 400 |
| `TestHandlerDownload_ServesFile` | Full round-trip: generate then download |
| `TestHandlerDownload_NotFound` | GET nonexistent ID → 404 |
| `TestEnsureSchema_Idempotent` | EnsureSchema can be called 3× without error |
| `TestService_FilesStoredUnderTenantDir` | File path contains `{tenantID}/documents` |

All tests pass `go test -race`.

---

## Dependencies

- `github.com/go-pdf/fpdf v0.9.0` — PDF generation
- `modernc.org/sqlite v1.48.2` — SQLite driver (test + production)
- Standard library only for HTTP, JSON, file I/O
