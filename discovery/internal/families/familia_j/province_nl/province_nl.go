// Package province_nl implements sub-technique J.NL.1 — Dutch province
// classification from postal codes.
//
// The Netherlands uses 4-digit postal codes (1000-9999). Each range maps to
// one of the 12 provinces. This classifier runs as a post-process over existing
// KG dealer entities in NL: it reads their primary location postal code and
// writes the derived province name into dealer_location.region.
//
// No external API call is required. The mapping is a static lookup table.
//
// Province codes (ISO 3166-2:NL):
//
//	NL-DR  Drenthe
//	NL-FL  Flevoland
//	NL-FR  Friesland (Fryslân)
//	NL-GE  Gelderland
//	NL-GR  Groningen
//	NL-LI  Limburg
//	NL-NB  Noord-Brabant
//	NL-NH  Noord-Holland
//	NL-OV  Overijssel
//	NL-UT  Utrecht
//	NL-ZE  Zeeland
//	NL-ZH  Zuid-Holland
//
// BaseWeights["J"] = 0.05.
package province_nl

import (
	"context"
	"log/slog"
	"sort"
	"strconv"
	"time"

	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/runner"
)

const (
	familyID    = "J"
	subTechID   = "J.NL.1"
	subTechName = "NL postal code -> province classifier"
)

// provinceRange maps a postal-code range [lo, hi] to a province ISO code.
type provinceRange struct {
	lo       int
	hi       int
	province string
}

// nlProvinceRanges is the ordered list of NL postal code -> province mappings.
// Derived from the Dutch PTT / PostNL segmentation (public domain).
var nlProvinceRanges = []provinceRange{
	{1000, 1099, "NL-NH"}, // Amsterdam
	{1100, 1299, "NL-NH"},
	{1300, 1399, "NL-FL"}, // Flevoland (Almere)
	{1400, 1499, "NL-NH"},
	{1500, 1599, "NL-NH"},
	{1600, 1699, "NL-NH"},
	{1700, 1799, "NL-NH"},
	{1800, 1899, "NL-NH"},
	{1900, 1999, "NL-NH"},
	{2000, 2099, "NL-ZH"},
	{2100, 2299, "NL-ZH"},
	{2300, 2399, "NL-ZH"}, // Leiden area
	{2400, 2499, "NL-ZH"},
	{2500, 2599, "NL-ZH"}, // Den Haag
	{2600, 2799, "NL-ZH"},
	{2800, 2899, "NL-ZH"},
	{2900, 2999, "NL-ZH"},
	{3000, 3099, "NL-ZH"}, // Rotterdam
	{3100, 3299, "NL-ZH"},
	{3300, 3399, "NL-ZH"},
	{3400, 3499, "NL-UT"},
	{3500, 3599, "NL-UT"}, // Utrecht
	{3600, 3699, "NL-UT"},
	{3700, 3799, "NL-UT"},
	{3800, 3899, "NL-UT"},
	{3900, 3999, "NL-UT"},
	{4000, 4099, "NL-GE"},
	{4100, 4199, "NL-GE"},
	{4200, 4299, "NL-ZH"},
	{4300, 4499, "NL-ZE"}, // Zeeland
	{4500, 4599, "NL-ZE"},
	{4600, 4799, "NL-ZE"},
	{4800, 4999, "NL-NB"}, // Noord-Brabant
	{5000, 5099, "NL-NB"},
	{5100, 5299, "NL-NB"},
	{5300, 5399, "NL-GE"},
	{5400, 5599, "NL-NB"},
	{5600, 5799, "NL-NB"}, // Eindhoven
	{5800, 5999, "NL-LI"},
	{6000, 6099, "NL-LI"}, // Limburg
	{6100, 6299, "NL-LI"},
	{6300, 6499, "NL-LI"},
	{6500, 6599, "NL-GE"}, // Nijmegen
	{6600, 6699, "NL-GE"},
	{6700, 6799, "NL-GE"},
	{6800, 6899, "NL-GE"},
	{6900, 6999, "NL-GE"},
	{7000, 7099, "NL-GE"},
	{7100, 7299, "NL-GE"},
	{7300, 7499, "NL-GE"},
	{7500, 7599, "NL-OV"}, // Overijssel / Enschede
	{7600, 7699, "NL-OV"},
	{7700, 7799, "NL-OV"},
	{7800, 7899, "NL-DR"}, // Drenthe
	{7900, 7999, "NL-DR"},
	{8000, 8099, "NL-OV"},
	{8100, 8199, "NL-OV"},
	{8200, 8299, "NL-FL"}, // Lelystad (Flevoland)
	{8300, 8399, "NL-FL"},
	{8400, 8499, "NL-FR"}, // Friesland
	{8500, 8599, "NL-FR"},
	{8600, 8699, "NL-FR"},
	{8700, 8799, "NL-FR"},
	{8800, 8899, "NL-FR"},
	{8900, 8999, "NL-FR"}, // Leeuwarden
	{9000, 9099, "NL-GR"}, // Groningen
	{9100, 9199, "NL-FR"},
	{9200, 9299, "NL-FR"},
	{9300, 9399, "NL-GR"},
	{9400, 9499, "NL-DR"},
	{9500, 9599, "NL-GR"},
	{9600, 9699, "NL-GR"},
	{9700, 9799, "NL-GR"},
	{9800, 9899, "NL-GR"},
	{9900, 9999, "NL-GR"},
}

// init sorts the range table by lo so binary search works.
func init() {
	sort.Slice(nlProvinceRanges, func(i, j int) bool {
		return nlProvinceRanges[i].lo < nlProvinceRanges[j].lo
	})
}

// ProvinceForPostalCode returns the ISO 3166-2:NL province code for a given
// 4-digit postal code string, or "" if not found.
func ProvinceForPostalCode(postalCode string) string {
	if len(postalCode) < 4 {
		return ""
	}
	n, err := strconv.Atoi(postalCode[:4])
	if err != nil {
		return ""
	}
	// Binary search.
	lo, hi := 0, len(nlProvinceRanges)-1
	for lo <= hi {
		mid := (lo + hi) / 2
		r := nlProvinceRanges[mid]
		if n < r.lo {
			hi = mid - 1
		} else if n > r.hi {
			lo = mid + 1
		} else {
			return r.province
		}
	}
	return ""
}

// ProvinceClassifier classifies NL dealers by province using postal codes.
type ProvinceClassifier struct {
	graph kg.KnowledgeGraph
	log   *slog.Logger
}

// New returns a ProvinceClassifier.
func New(graph kg.KnowledgeGraph) *ProvinceClassifier {
	return &ProvinceClassifier{
		graph: graph,
		log:   slog.Default().With("sub_technique", subTechID),
	}
}

// ID returns the sub-technique identifier.
func (c *ProvinceClassifier) ID() string { return subTechID }

// Name returns the human-readable sub-technique label.
func (c *ProvinceClassifier) Name() string { return subTechName }

// Run classifies all NL dealers in the KG that are missing a province.
func (c *ProvinceClassifier) Run(ctx context.Context) (*runner.SubTechniqueResult, error) {
	start := time.Now()
	result := &runner.SubTechniqueResult{SubTechniqueID: subTechID, Country: "NL"}

	candidates, err := c.graph.ListDealersByCountry(ctx, "NL")
	if err != nil {
		result.Errors++
		result.Duration = time.Since(start)
		return result, err
	}

	for _, d := range candidates {
		if ctx.Err() != nil {
			break
		}
		if d.PostalCode == nil || *d.PostalCode == "" {
			continue
		}
		province := ProvinceForPostalCode(*d.PostalCode)
		if province == "" {
			continue
		}
		if err := c.graph.UpdateDealerSubRegion(ctx, d.DealerID, province); err != nil {
			c.log.Warn("province_nl: update error", "dealer", d.DealerID, "err", err)
			result.Errors++
			continue
		}
		result.Discovered++
	}

	result.Duration = time.Since(start)
	c.log.Info("province_nl: done", "classified", result.Discovered, "errors", result.Errors)
	return result, nil
}
