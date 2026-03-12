// Package taxhunter implements the tax classification cascade for Phase 5 forensics.
package taxhunter

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"github.com/cardex/forensics/pkg/ahocorasick"
	"github.com/redis/go-redis/v9"
)

const (
	l1CacheKey     = "dict:l1_tax"
	viesTimeout    = 200 * time.Millisecond
	statusREBU     = "REBU"
	statusDeductible = "DEDUCTIBLE"
	statusPending   = "PENDING_VIES_OPTIMISTIC"
	statusHumanAudit = "REQUIRES_HUMAN_AUDIT"
)

// VehicleInput holds the vehicle data needed for tax classification.
type VehicleInput struct {
	VehicleULID    string
	Description    string
	SellerType     string
	SellerVATID    string
	OriginCountry  string
}

// TaxResult holds the classification result.
type TaxResult struct {
	Status     string  `json:"Status"`
	Confidence float64 `json:"Confidence"`
	Method     string  `json:"Method"`
}

// VatChecker validates VAT numbers. Implemented by vies.Client.
type VatChecker interface {
	CheckVAT(ctx context.Context, countryCode string, vatNumber string) (valid bool, name string, err error)
}

// TaxCache provides L1 cache lookup. Implemented by redis adapter.
type TaxCache interface {
	Get(ctx context.Context, vehicleULID string) (string, error)
}

// redisTaxCache adapts redis.Client to TaxCache.
type redisTaxCache struct {
	rdb *redis.Client
}

func (r *redisTaxCache) Get(ctx context.Context, vehicleULID string) (string, error) {
	return r.rdb.HGet(ctx, l1CacheKey, vehicleULID).Result()
}

// Classifier runs the tax classification cascade.
type Classifier struct {
	scanner    *ahocorasick.Scanner
	vatChecker VatChecker
	taxCache   TaxCache
}

// New creates a Classifier with the given dependencies.
func New(scanner *ahocorasick.Scanner, viesClient VatChecker, rdb *redis.Client) *Classifier {
	return NewWithCache(scanner, viesClient, &redisTaxCache{rdb: rdb})
}

// NewWithCache creates a Classifier with explicit cache (for testing).
func NewWithCache(scanner *ahocorasick.Scanner, vatChecker VatChecker, taxCache TaxCache) *Classifier {
	return &Classifier{
		scanner:    scanner,
		vatChecker: vatChecker,
		taxCache:   taxCache,
	}
}

// Classify runs the classification cascade and returns the tax result.
func (c *Classifier) Classify(ctx context.Context, vehicle VehicleInput) (TaxResult, error) {
	if strings.ToUpper(vehicle.SellerType) == "INDIVIDUAL" {
		return TaxResult{Status: statusREBU, Confidence: 1.00, Method: "ENTITY_OVERRIDE"}, nil
	}

	if matched, keyword := c.scanner.Scan(vehicle.Description); matched {
		return TaxResult{Status: statusREBU, Confidence: 1.00, Method: "AHO_CORASICK:" + keyword}, nil
	}

	cached, err := c.taxCache.Get(ctx, vehicle.VehicleULID)
	if err == nil {
		var r TaxResult
		if err := json.Unmarshal([]byte(cached), &r); err == nil {
			return r, nil
		}
	}

	if vehicle.SellerVATID != "" {
		countryCode, vatNumber := extractVATParts(vehicle.SellerVATID, vehicle.OriginCountry)
		viesCtx, cancel := context.WithTimeout(ctx, viesTimeout)
		defer cancel()

		valid, _, err := c.vatChecker.CheckVAT(viesCtx, countryCode, vatNumber)
		if err != nil {
			if strings.Contains(err.Error(), "timeout") || strings.Contains(err.Error(), "deadline") {
				return TaxResult{Status: statusPending, Confidence: 0.70, Method: "VIES_TIMEOUT"}, nil
			}
			return TaxResult{}, fmt.Errorf("vies: %w", err)
		}
		if valid {
			return TaxResult{Status: statusDeductible, Confidence: 0.98, Method: "VIES"}, nil
		}
		return TaxResult{Status: statusREBU, Confidence: 0.95, Method: "VIES_INVALID"}, nil
	}

	return TaxResult{Status: statusHumanAudit, Confidence: 0.00, Method: "NO_SIGNAL"}, nil
}

func extractVATParts(sellerVATID, originCountry string) (countryCode, vatNumber string) {
	countryCode = strings.ToUpper(strings.TrimSpace(originCountry))
	if countryCode == "" && len(sellerVATID) >= 2 {
		countryCode = strings.ToUpper(sellerVATID[:2])
		vatNumber = strings.TrimSpace(sellerVATID[2:])
		return countryCode, vatNumber
	}
	if len(sellerVATID) >= 2 && strings.ToUpper(sellerVATID[:2]) == countryCode {
		vatNumber = strings.TrimSpace(sellerVATID[2:])
		return countryCode, vatNumber
	}
	vatNumber = strings.TrimSpace(sellerVATID)
	return countryCode, vatNumber
}
