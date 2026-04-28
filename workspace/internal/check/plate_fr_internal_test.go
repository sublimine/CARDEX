package check

import (
	"context"
	"net/http"
	"os"
	"testing"
	"time"
)

// Real SSR snippet captured 2026-04-20 from
// https://www.immatriculation-auto.info/vehicle/FX055SH
// (astro-island for the Report component).
const frSSRSnippet = `` +
	`<astro-island uid="zl1Owc" prefix="r0" ` +
	`component-url="/_astro/Report.abc.js" ` +
	`renderer-url="/_astro/client.def.js" ` +
	`props="{&quot;input&quot;:[0,&quot;FX055SH&quot;],` +
	`&quot;locale&quot;:[0,&quot;fr&quot;],` +
	`&quot;brandModelYear&quot;:[0,{&quot;brand&quot;:[0,&quot;DACIA&quot;],` +
	`&quot;model&quot;:[0,&quot;SANDERO III&quot;],` +
	`&quot;year&quot;:[0,&quot;2021&quot;]}],` +
	`&quot;isBot&quot;:[0,false]}"></astro-island>`

func TestParseFRAstroIslandProps(t *testing.T) {
	r := &PlateResult{}
	parseFRAstroIslandProps(frSSRSnippet, r)
	if r.Make != "DACIA" {
		t.Errorf("Make = %q, want DACIA", r.Make)
	}
	if r.Model != "SANDERO III" {
		t.Errorf("Model = %q, want SANDERO III", r.Model)
	}
	if r.FirstRegistration == nil || r.FirstRegistration.Year() != 2021 {
		t.Errorf("FirstRegistration = %v, want year 2021", r.FirstRegistration)
	}
}

func TestParseFRAstroIslandProps_NoProps(t *testing.T) {
	r := &PlateResult{}
	parseFRAstroIslandProps(`<html><title>FX055SH - </title></html>`, r)
	if r.Make != "" || r.Model != "" || r.FirstRegistration != nil {
		t.Errorf("expected no-op when brandModelYear absent, got %+v", r)
	}
}

// TestFRPlateResolver_Live hits the real SSR page. Skipped by default because
// CI should not depend on network. Enable with CARDEX_LIVE=1.
func TestFRPlateResolver_Live(t *testing.T) {
	if os.Getenv("CARDEX_LIVE") == "" {
		t.Skip("set CARDEX_LIVE=1 to run live FR plate lookup")
	}
	const plate = "FX055SH"
	r := newFRPlateResolver(&http.Client{Timeout: 20 * time.Second})
	result, err := r.Resolve(context.Background(), plate)
	if err != nil {
		t.Fatalf("live lookup: %v", err)
	}
	if result.Make != "DACIA" {
		t.Errorf("Make = %q, want DACIA", result.Make)
	}
	if result.Model == "" {
		t.Error("expected non-empty Model")
	}
	if result.FirstRegistration == nil || result.FirstRegistration.Year() != 2021 {
		t.Errorf("FirstRegistration = %v, want year 2021", result.FirstRegistration)
	}
}

func TestParseFRMetaDesc_FuelAndCC(t *testing.T) {
	r := &PlateResult{Make: "DACIA"}
	desc := `DACIA SANDERO III immatriculée en France sous le numéro de plaque ` +
		`d'immatriculation FX055SH en 2021. Découvrez son carburant Essence, ` +
		`sa Manuelle et sa capacité de 999 cm³`
	parseFRMetaDesc(desc, r)
	if r.Model != "SANDERO III" {
		t.Errorf("Model = %q, want SANDERO III", r.Model)
	}
	if r.FuelType != "Essence" {
		t.Errorf("FuelType = %q, want Essence", r.FuelType)
	}
	if r.DisplacementCC != 999 {
		t.Errorf("DisplacementCC = %d, want 999", r.DisplacementCC)
	}
}
