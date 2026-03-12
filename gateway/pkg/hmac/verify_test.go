// Package hmac provides HMAC-SHA256 verification for B2B webhook payloads.
package hmac

import "testing"

func TestVerify(t *testing.T) {
	tests := []struct {
		name      string
		body      []byte
		secret    string
		signature string
		wantErr   bool
	}{
		{
			name:      "valid signature",
			body:      []byte(`{"vin":"WBA123","make":"BMW"}`),
			secret:    "partner-secret-123",
			signature: Sign([]byte(`{"vin":"WBA123","make":"BMW"}`), "partner-secret-123"),
			wantErr:   false,
		},
		{
			name:      "invalid signature wrong body",
			body:      []byte(`{"vin":"WBA123","make":"BMW"}`),
			secret:    "partner-secret-123",
			signature: Sign([]byte(`{"vin":"WBA999","make":"Audi"}`), "partner-secret-123"),
			wantErr:   true,
		},
		{
			name:      "empty secret",
			body:      []byte(`{"vin":"WBA123"}`),
			secret:    "",
			signature: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
			wantErr:   true,
		},
		{
			name:      "empty signature",
			body:      []byte(`{"vin":"WBA123"}`),
			secret:    "partner-secret-123",
			signature: "",
			wantErr:   true,
		},
		{
			name:      "tampered body",
			body:      []byte(`{"vin":"WBA123","make":"BMW","tampered":true}`),
			secret:    "partner-secret-123",
			signature: Sign([]byte(`{"vin":"WBA123","make":"BMW"}`), "partner-secret-123"),
			wantErr:   true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := Verify(tt.body, tt.secret, tt.signature)
			if tt.wantErr && err == nil {
				t.Errorf("Verify() expected error, got nil")
			}
			if !tt.wantErr && err != nil {
				t.Errorf("Verify() unexpected error: %v", err)
			}
		})
	}
}

func TestSignVerifyRoundTrip(t *testing.T) {
	body := []byte(`{"vin":"WBA123","make":"BMW","timestamp":"2026-02-27T12:00:00Z"}`)
	secret := "partner-secret-123"

	signature := Sign(body, secret)
	if err := Verify(body, secret, signature); err != nil {
		t.Errorf("Sign+Verify round-trip failed: %v", err)
	}
}
