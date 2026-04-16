package e13_vlm_vision

import "cardex.eu/extraction/internal/pipeline"

// ParseVLMResponseExported is an exported wrapper around parseVLMResponse
// for use in external (black-box) test files in package e13_vlm_vision_test.
func ParseVLMResponseExported(raw string) (*pipeline.VehicleRaw, int) {
	return parseVLMResponse(raw)
}
