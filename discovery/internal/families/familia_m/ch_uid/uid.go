// Package ch_uid implements sub-technique M.2 — Swiss UID-Register validation (CH).
//
// The Swiss Unternehmens-Identifikationsregister (UID-Register) is managed by the
// Federal Statistical Office (BFS). It validates Swiss company UIDs in the format
// "CHE-NNN.NNN.NNN".
//
// # API
//
// There is no public REST/JSON API. The only official programmatic interface is
// SOAP/WSDL (research confirmed 2026-04-15):
//
//	SOAP endpoint: https://www.uid-wse-a.admin.ch/V3.0/PublicServices.svc
//	WSDL:          https://www.uid-wse-a.admin.ch/V3.0/PublicServices.svc?wsdl
//	Namespace:     http://www.uid-wse.admin.ch/V3.0/
//	Authentication: none (public)
//
// # Request format
//
// SOAPAction: http://www.uid-wse.admin.ch/V3.0/IPublicServices/GetByUID
//
//	<soap12:Envelope xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">
//	  <soap12:Body>
//	    <GetByUID xmlns="http://www.uid-wse.admin.ch/V3.0/">
//	      <uid>CHE-123.456.789</uid>
//	    </GetByUID>
//	  </soap12:Body>
//	</soap12:Envelope>
//
// # Response (abridged)
//
//	<GetByUIDResponse>
//	  <GetByUIDResult>
//	    <organisation>
//	      <uid><uidOrganisationId>123456789</uidOrganisationId></uid>
//	      <nameData><name>ACME AG</name></nameData>
//	      <address><street>Bahnhofstrasse</street><houseNumber>1</houseNumber>
//	               <swissZipCode>8001</swissZipCode><town>Zürich</town></address>
//	      <uidEntityStatus>1</uidEntityStatus>  <!-- 1=ACTIVE -->
//	    </organisation>
//	  </GetByUIDResult>
//	</GetByUIDResponse>
//
// uidEntityStatus values: 1=Active, 2=Under liquidation, 3=Cancelled.
//
// Rate limiting: 1 req / 1 s.
// Stale threshold: 30 days.
// Country: CH only.
package ch_uid

import (
	"bytes"
	"context"
	"encoding/xml"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"strings"
	"time"

	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/metrics"
	"cardex.eu/discovery/internal/runner"
)

const (
	familyID    = "M"
	subTechID   = "M.2"
	subTechName = "Swiss UID-Register validation (CH)"
	countryCH   = "CH"

	defaultEndpointURL = "https://www.uid-wse-a.admin.ch/V3.0/PublicServices.svc"
	defaultReqInterval = time.Second
	staleDays          = 30
	uidNamespace       = "http://www.uid-wse.admin.ch/V3.0/"
	soapNS             = "http://www.w3.org/2003/05/soap-envelope"
	soapAction         = "http://www.uid-wse.admin.ch/V3.0/IPublicServices/GetByUID"

	confidenceBump = 0.10

	cardexUA = "CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu)"
)

// UIDStatus holds the parsed UID-Register response for a single UID lookup.
type UIDStatus struct {
	Valid       bool
	Active      bool   // uidEntityStatus == 1
	Name        string
	Street      string
	ZipCode     string
	City        string
	ValidatedAt time.Time
}

// ── SOAP request / response structures ───────────────────────────────────────

type soapEnvelope struct {
	XMLName xml.Name   `xml:"http://www.w3.org/2003/05/soap-envelope Envelope"`
	Body    soapBody   `xml:"http://www.w3.org/2003/05/soap-envelope Body"`
}

type soapBody struct {
	GetByUID *getByUIDRequest  `xml:",omitempty"`
	Response *getByUIDResponse `xml:",omitempty"`
}

type getByUIDRequest struct {
	XMLName xml.Name `xml:"http://www.uid-wse.admin.ch/V3.0/ GetByUID"`
	UID     string   `xml:"uid"`
}

// getByUIDResponse mirrors the relevant subset of the UID SOAP response.
type getByUIDResponse struct {
	XMLName xml.Name      `xml:"GetByUIDResponse"`
	Result  uidOrgWrapper `xml:"GetByUIDResult"`
}

type uidOrgWrapper struct {
	Organisation *uidOrganisation `xml:"organisation"`
}

type uidOrganisation struct {
	UID      struct {
		OrgID string `xml:"uidOrganisationId"`
	} `xml:"uid"`
	NameData struct {
		Name string `xml:"name"`
	} `xml:"nameData"`
	Address struct {
		Street      string `xml:"street"`
		HouseNumber string `xml:"houseNumber"`
		ZipCode     string `xml:"swissZipCode"`
		Town        string `xml:"town"`
	} `xml:"address"`
	EntityStatus string `xml:"uidEntityStatus"`
}

// ChUID executes the M.2 sub-technique UID validation batch.
type ChUID struct {
	graph       kg.KnowledgeGraph
	client      *http.Client
	endpointURL string
	reqInterval time.Duration
	log         *slog.Logger
}

// New returns a ChUID executor with the production UID-Register endpoint.
func New(graph kg.KnowledgeGraph) *ChUID {
	return NewWithEndpoint(graph, defaultEndpointURL, defaultReqInterval)
}

// NewWithEndpoint returns a ChUID executor with a custom SOAP endpoint and interval
// (use interval=0 in tests).
func NewWithEndpoint(graph kg.KnowledgeGraph, endpointURL string, reqInterval time.Duration) *ChUID {
	return &ChUID{
		graph:       graph,
		client:      &http.Client{Timeout: 20 * time.Second},
		endpointURL: endpointURL,
		reqInterval: reqInterval,
		log:         slog.Default().With("sub_technique", subTechID),
	}
}

// ID returns the sub-technique identifier.
func (c *ChUID) ID() string { return subTechID }

// Name returns the human-readable sub-technique label.
func (c *ChUID) Name() string { return subTechName }

// ValidateUID performs a single UID-Register lookup via SOAP.
func (c *ChUID) ValidateUID(ctx context.Context, uid string) (*UIDStatus, error) {
	uid = normalizeUID(uid)

	reqBody, err := buildSOAPRequest(uid)
	if err != nil {
		return nil, fmt.Errorf("ch_uid.ValidateUID: build SOAP: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.endpointURL, bytes.NewReader(reqBody))
	if err != nil {
		return nil, fmt.Errorf("ch_uid.ValidateUID: build req: %w", err)
	}
	req.Header.Set("Content-Type", "application/soap+xml; charset=utf-8")
	req.Header.Set("SOAPAction", soapAction)
	req.Header.Set("User-Agent", cardexUA)

	resp, err := c.client.Do(req)
	if err != nil {
		metrics.SubTechniqueRequests.WithLabelValues(subTechID, "err").Inc()
		return nil, fmt.Errorf("ch_uid.ValidateUID: http: %w", err)
	}
	defer resp.Body.Close()

	metrics.SubTechniqueRequests.WithLabelValues(subTechID,
		fmt.Sprintf("%dxx", resp.StatusCode/100)).Inc()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("ch_uid.ValidateUID: read body: %w", err)
	}

	if resp.StatusCode != http.StatusOK {
		return &UIDStatus{Valid: false, ValidatedAt: time.Now().UTC()}, nil
	}

	return parseSOAPResponse(body)
}

// Run fetches all CH dealers with unvalidated or stale UIDs and validates them.
func (c *ChUID) Run(ctx context.Context) (*runner.SubTechniqueResult, error) {
	start := time.Now()
	result := &runner.SubTechniqueResult{SubTechniqueID: subTechID, Country: countryCH}

	candidates, err := c.graph.FindDealersForVATValidation(ctx, []string{countryCH}, staleDays)
	if err != nil {
		result.Errors++
		result.Duration = time.Since(start)
		return result, fmt.Errorf("ch_uid.Run: find candidates: %w", err)
	}

	c.log.Info("ch_uid: validation batch started", "candidates", len(candidates))

	for _, cand := range candidates {
		if ctx.Err() != nil {
			break
		}

		if c.reqInterval > 0 {
			select {
			case <-ctx.Done():
				goto done
			case <-time.After(c.reqInterval):
			}
		}

		status, err := c.ValidateUID(ctx, cand.PrimaryVAT)
		if err != nil {
			c.log.Warn("ch_uid: lookup error",
				"dealer", cand.DealerID, "uid", cand.PrimaryVAT, "err", err)
			result.Errors++
			_ = c.graph.UpdateVATValidation(ctx, cand.DealerID, time.Now().UTC(), "ERROR")
			continue
		}

		validStatus := "INACTIVE"
		if !status.Valid {
			validStatus = "NOT_FOUND"
		} else if status.Active {
			validStatus = "VALID"
		}

		if err := c.graph.UpdateVATValidation(ctx, cand.DealerID, status.ValidatedAt, validStatus); err != nil {
			c.log.Warn("ch_uid: UpdateVATValidation error", "dealer", cand.DealerID, "err", err)
			result.Errors++
			continue
		}

		if status.Active {
			result.Confirmed++
			if nameMatch(status.Name, cand.CanonicalName) {
				newScore := cand.ConfidenceScore + confidenceBump
				if newScore > 1.0 {
					newScore = 1.0
				}
				_ = c.graph.UpdateConfidenceScore(ctx, cand.DealerID, newScore)
			}
		}
	}

done:
	result.Duration = time.Since(start)
	metrics.CycleDuration.WithLabelValues(familyID, countryCH).Observe(result.Duration.Seconds())
	c.log.Info("ch_uid: done",
		"confirmed", result.Confirmed,
		"errors", result.Errors,
	)
	return result, nil
}

// ── SOAP helpers ──────────────────────────────────────────────────────────────

// buildSOAPRequest constructs the SOAP XML body for a GetByUID call.
func buildSOAPRequest(uid string) ([]byte, error) {
	env := soapEnvelope{
		Body: soapBody{
			GetByUID: &getByUIDRequest{UID: uid},
		},
	}
	out, err := xml.Marshal(env)
	if err != nil {
		return nil, err
	}
	return append([]byte(xml.Header), out...), nil
}

// parseSOAPResponse parses the SOAP XML response into a UIDStatus.
func parseSOAPResponse(body []byte) (*UIDStatus, error) {
	// The SOAP response wraps the result in a soap12:Body/GetByUIDResponse element.
	// We use a lenient parser that ignores namespace prefixes by searching for
	// the key elements by local name.
	type uidResult struct {
		OrgName     string `xml:"GetByUIDResult>organisation>nameData>name"`
		Street      string `xml:"GetByUIDResult>organisation>address>street"`
		HouseNumber string `xml:"GetByUIDResult>organisation>address>houseNumber"`
		ZipCode     string `xml:"GetByUIDResult>organisation>address>swissZipCode"`
		Town        string `xml:"GetByUIDResult>organisation>address>town"`
		Status      string `xml:"GetByUIDResult>organisation>uidEntityStatus"`
	}

	// Strip SOAP envelope — find the Body content between start/end Body tags.
	bodyContent := extractSOAPBodyContent(body)
	if len(bodyContent) == 0 {
		return &UIDStatus{Valid: false, ValidatedAt: time.Now().UTC()}, nil
	}

	var r uidResult
	if err := xml.Unmarshal(bodyContent, &r); err != nil {
		return nil, fmt.Errorf("ch_uid.parseSOAPResponse: %w", err)
	}

	if r.OrgName == "" {
		return &UIDStatus{Valid: false, ValidatedAt: time.Now().UTC()}, nil
	}

	street := strings.TrimSpace(r.Street + " " + r.HouseNumber)
	return &UIDStatus{
		Valid:       true,
		Active:      r.Status == "1",
		Name:        r.OrgName,
		Street:      street,
		ZipCode:     r.ZipCode,
		City:        r.Town,
		ValidatedAt: time.Now().UTC(),
	}, nil
}

// extractSOAPBodyContent returns the content inside the first <*:Body> element.
func extractSOAPBodyContent(envelope []byte) []byte {
	s := string(envelope)
	// Find the content between SOAP Body tags (ignoring namespace prefix).
	start := findTagEnd(s, "Body")
	if start < 0 {
		return nil
	}
	// Find closing body tag.
	end := strings.LastIndex(s, "</")
	closingIdx := strings.LastIndex(s[:end], "</")
	if closingIdx < 0 {
		return nil
	}
	inner := strings.TrimSpace(s[start:closingIdx])
	if inner == "" {
		return nil
	}
	return []byte(inner)
}

// findTagEnd returns the index after the closing `>` of the first opening tag
// matching localName (ignoring namespace prefix).
func findTagEnd(s, localName string) int {
	for i := 0; i < len(s); i++ {
		if s[i] != '<' {
			continue
		}
		rest := s[i+1:]
		// Skip '/' (closing) and '!' (comments/CDATA).
		if len(rest) == 0 || rest[0] == '/' || rest[0] == '!' {
			continue
		}
		// Get tag name (possibly prefixed).
		end := strings.IndexAny(rest, " \t\n\r>")
		if end < 0 {
			continue
		}
		tagName := rest[:end]
		if idx := strings.LastIndex(tagName, ":"); idx >= 0 {
			tagName = tagName[idx+1:]
		}
		if tagName == localName {
			// Return the index just after the closing >.
			closeIdx := strings.Index(rest, ">")
			if closeIdx < 0 {
				return -1
			}
			return i + 1 + closeIdx + 1
		}
	}
	return -1
}

// normalizeUID strips dashes and dots from a UID, ensuring the format expected
// by the SOAP service. Both "CHE-123.456.789" and "CHE123456789" are accepted.
func normalizeUID(uid string) string {
	// The SOAP service typically accepts "CHE-NNN.NNN.NNN".
	// If the input lacks the CHE prefix, keep it as-is.
	uid = strings.TrimSpace(uid)
	if !strings.HasPrefix(strings.ToUpper(uid), "CHE") {
		return uid
	}
	// Normalize to CHE-NNN.NNN.NNN format.
	digits := strings.Map(func(r rune) rune {
		if r >= '0' && r <= '9' {
			return r
		}
		return -1
	}, uid[3:]) // strip "CHE" prefix
	if len(digits) != 9 {
		return uid // return original if unexpected length
	}
	return fmt.Sprintf("CHE-%s.%s.%s", digits[:3], digits[3:6], digits[6:])
}

// nameMatch returns true if uidName contains kgName as a substring (case-insensitive).
func nameMatch(uidName, kgName string) bool {
	if uidName == "" || kgName == "" {
		return false
	}
	u := strings.ToLower(strings.TrimSpace(uidName))
	k := strings.ToLower(strings.TrimSpace(kgName))
	return strings.Contains(u, k) || strings.Contains(k, u)
}
