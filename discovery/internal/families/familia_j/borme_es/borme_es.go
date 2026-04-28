// Package borme_es implements sub-technique J.ES.1 — BORME provincial PDF
// parsing for Spanish sub-jurisdiction coverage.
//
// # STATUS: DEFERRED — PDF OCR + structured parsing complexity
//
// # What BORME offers
//
// The Boletín Oficial del Registro Mercantil (BORME) is Spain's official
// commercial registry gazette, published daily by the Registradores de España.
// It covers all 52 provincial Registros Mercantiles and includes:
//   - New company registrations (Sección A)
//   - Capital changes, governance changes, dissolutions (Sección B)
//
// Free access via: https://www.boe.es/diario_borme/
// API: https://boe.es/datosabiertos/api/borme/sumario/{YYYY}/{MM}/{DD}
//
// # Why deferred
//
// The BORME gazette is distributed as:
//   1. PDF documents (main format) — require OCR for structured data extraction
//   2. XML summaries — contain only announcement metadata, not full company data
//   3. HTML pages — individual entries accessible but require JS rendering for
//      the interactive registry (not the gazette itself)
//
// Structured parsing requires:
//   - Layout-aware PDF parser (pdftotext loses column structure)
//   - Named-entity recognition for company name, address, NIF extraction
//   - LayoutLMv3 or equivalent document-intelligence model for reliable extraction
//
// This overlaps with the extraction pipeline innovation roadmap (document
// intelligence sprint, tentatively Sprint 20+).
//
// # Alternative coverage
//
// A.ES.1 (BORME XML daily scraper) already captures new dealer registrations
// for NACE 4511 from the Sección A XML summaries. J.ES would add historical
// coverage from PDF archives (2003-present) but the incremental yield vs.
// processing cost is unfavourable at current team size.
//
// # Activation path
//
// 1. Integrate LayoutLMv3 (or Docling) document parser in the ML pipeline.
// 2. Implement BORME PDF download + layout extraction per province per day.
// 3. Parse NIF + company name + address from structured output.
// 4. Cross-validate against A.ES.1 BORME XML to avoid duplicates.
// Estimated activation sprint: Sprint 21+ (post ML pipeline Sprint 20).
package borme_es

import (
	"context"
	"log/slog"

	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/runner"
)

const (
	subTechID   = "J.ES.1"
	subTechName = "ES BORME provincial PDF parsing (DEFERRED -- OCR + LayoutLMv3 required)"
)

// BormeES is the J.ES.1 stub.
type BormeES struct {
	graph kg.KnowledgeGraph
	log   *slog.Logger
}

// New constructs a BormeES stub.
func New(graph kg.KnowledgeGraph) *BormeES {
	return &BormeES{
		graph: graph,
		log:   slog.Default().With("sub_technique", subTechID),
	}
}

// ID returns the sub-technique identifier.
func (b *BormeES) ID() string { return subTechID }

// Name returns the human-readable sub-technique label.
func (b *BormeES) Name() string { return subTechName }

// Run logs the deferral reason and returns an empty result.
func (b *BormeES) Run(_ context.Context) (*runner.SubTechniqueResult, error) {
	b.log.Info("J.ES.1 BORME PDF: DEFERRED",
		"reason", "PDF gazette requires OCR + LayoutLMv3 for structured extraction; A.ES.1 XML covers new registrations",
		"activation", "Sprint 21+ post ML pipeline; integrate Docling/LayoutLMv3 document parser",
	)
	return &runner.SubTechniqueResult{SubTechniqueID: subTechID, Country: "ES"}, nil
}
