// Package vies provides a client for the EU VIES VAT validation SOAP service.
package vies

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"io"
	"net/http"
	"regexp"
	"strings"
	"time"
)

const viesURL = "https://ec.europa.eu/taxation_customs/vies/services/checkVatService"

// Client calls the EU VIES SOAP service for VAT validation.
type Client struct {
	BaseURL    string
	httpClient *http.Client
	timeout    time.Duration
}

// New creates a VIES client with the given timeout.
func New(timeout time.Duration) *Client {
	return &Client{
		BaseURL:    viesURL,
		httpClient: &http.Client{Timeout: timeout},
		timeout:    timeout,
	}
}

// CheckVAT validates a VAT number via the EU VIES service.
// Returns (valid, name, nil) on success, or (false, "", error) on failure.
func (c *Client) CheckVAT(ctx context.Context, countryCode string, vatNumber string) (valid bool, name string, err error) {
	reqBody := buildCheckVatRequest(countryCode, vatNumber)
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.BaseURL, bytes.NewReader([]byte(reqBody)))
	if err != nil {
		return false, "", fmt.Errorf("vies: request: %w", err)
	}
	req.Header.Set("Content-Type", "text/xml; charset=utf-8")
	req.Header.Set("SOAPAction", "checkVat")

	resp, err := c.httpClient.Do(req)
	if err != nil {
		if ctx.Err() != nil || strings.Contains(err.Error(), "timeout") || strings.Contains(err.Error(), "deadline") {
			return false, "", fmt.Errorf("vies: timeout after %v for %s%s", c.timeout, countryCode, vatNumber)
		}
		return false, "", fmt.Errorf("vies: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return false, "", fmt.Errorf("vies: http %d: %w", resp.StatusCode, errors.New(string(body)))
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return false, "", fmt.Errorf("vies: read body: %w", err)
	}

	return parseCheckVatResponse(string(body))
}

func buildCheckVatRequest(countryCode, vatNumber string) string {
	return `<?xml version="1.0" encoding="UTF-8"?>` +
		`<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:urn="urn:ec.europa.eu:taxud:vies:services:checkVat:types">` +
		`<soapenv:Header/>` +
		`<soapenv:Body>` +
		`<urn:checkVat>` +
		`<urn:countryCode>` + escapeXML(countryCode) + `</urn:countryCode>` +
		`<urn:vatNumber>` + escapeXML(vatNumber) + `</urn:vatNumber>` +
		`</urn:checkVat>` +
		`</soapenv:Body>` +
		`</soapenv:Envelope>`
}

func escapeXML(s string) string {
	s = strings.ReplaceAll(s, "&", "&amp;")
	s = strings.ReplaceAll(s, "<", "&lt;")
	s = strings.ReplaceAll(s, ">", "&gt;")
	s = strings.ReplaceAll(s, "\"", "&quot;")
	s = strings.ReplaceAll(s, "'", "&apos;")
	return s
}

var validRe = regexp.MustCompile(`<valid>\s*(true|false)\s*</valid>`)
var nameRe = regexp.MustCompile(`<name>\s*([^<]*)\s*</name>`)

func parseCheckVatResponse(body string) (valid bool, name string, err error) {
	validMatch := validRe.FindStringSubmatch(body)
	if len(validMatch) < 2 {
		return false, "", fmt.Errorf("vies: could not parse valid from response")
	}
	valid = strings.EqualFold(validMatch[1], "true")

	nameMatch := nameRe.FindStringSubmatch(body)
	if len(nameMatch) >= 2 {
		name = strings.TrimSpace(nameMatch[1])
	}
	return valid, name, nil
}
