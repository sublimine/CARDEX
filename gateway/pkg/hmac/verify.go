// Package hmac provides HMAC-SHA256 verification for B2B webhook payloads.
package hmac

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
)

// Verify computes HMAC-SHA256 of body using secret and compares
// against the provided signature using constant-time comparison.
// Returns nil if valid, error if mismatch or invalid encoding.
func Verify(body []byte, secret string, signature string) error {
	if len(secret) == 0 {
		return fmt.Errorf("hmac: empty secret")
	}
	if len(signature) == 0 {
		return fmt.Errorf("hmac: empty signature")
	}

	expectedSig, err := hex.DecodeString(signature)
	if err != nil {
		return fmt.Errorf("hmac: invalid hex signature: %w", err)
	}

	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write(body)
	computedSig := mac.Sum(nil)

	if !hmac.Equal(computedSig, expectedSig) {
		return fmt.Errorf("hmac: signature mismatch")
	}

	return nil
}

// Sign computes HMAC-SHA256 of body using secret and returns hex-encoded signature.
func Sign(body []byte, secret string) string {
	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write(body)
	return hex.EncodeToString(mac.Sum(nil))
}
