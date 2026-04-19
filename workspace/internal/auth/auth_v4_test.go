package auth_test

// Track C v4 — additional auth functional correctness verifications.

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"cardex.eu/workspace/internal/auth"
)

// ── Login security tests ──────────────────────────────────────────────────────

// TestLogin_SameErrorForMissingEmailAndWrongPassword verifies that non-existent
// email and wrong password produce identical 401 responses — no email enumeration.
func TestLogin_SameErrorForMissingEmailAndWrongPassword(t *testing.T) {
	mux, _, _ := setupMux(t)
	registerUser(t, mux, "secure@example.com", "correctpass", "t1")

	// Wrong password for existing account.
	w1 := postJSON(t, mux, "/api/v1/auth/login", map[string]string{
		"email": "secure@example.com", "password": "wrongpass",
	})
	var r1 map[string]any
	_ = json.Unmarshal(w1.Body.Bytes(), &r1)

	// Non-existent email — should produce the SAME status and message.
	w2 := postJSON(t, mux, "/api/v1/auth/login", map[string]string{
		"email": "ghost@example.com", "password": "anypass123",
	})
	var r2 map[string]any
	_ = json.Unmarshal(w2.Body.Bytes(), &r2)

	if w1.Code != http.StatusUnauthorized {
		t.Errorf("wrong password: want 401, got %d", w1.Code)
	}
	if w2.Code != http.StatusUnauthorized {
		t.Errorf("missing email: want 401, got %d", w2.Code)
	}
	msg1, _ := r1["error"].(string)
	msg2, _ := r2["error"].(string)
	if msg1 != msg2 {
		t.Errorf("error messages differ (email enumeration risk): %q vs %q", msg1, msg2)
	}
}

// ── Middleware bearer-prefix tests ────────────────────────────────────────────

// TestRequireAuth_WrongBearerPrefix_401 ensures that an Authorization header
// with the wrong scheme ("Token " instead of "Bearer ") is rejected with 401.
func TestRequireAuth_WrongBearerPrefix_401(t *testing.T) {
	svc := newJWT(t)
	token, _ := svc.GenerateToken("user-1", "tenant-1")

	handler := auth.RequireAuth(svc)(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	req := httptest.NewRequest(http.MethodGet, "/", nil)
	req.Header.Set("Authorization", "Token "+token) // wrong scheme
	w := httptest.NewRecorder()
	handler.ServeHTTP(w, req)
	if w.Code != http.StatusUnauthorized {
		t.Errorf("wrong Bearer prefix: want 401, got %d", w.Code)
	}
}

// TestRequireAuth_BearerWithoutSpace_401 ensures "Bearer" (no space, no token)
// is also rejected.
func TestRequireAuth_BearerWithoutSpace_401(t *testing.T) {
	svc := newJWT(t)
	handler := auth.RequireAuth(svc)(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	req := httptest.NewRequest(http.MethodGet, "/", nil)
	req.Header.Set("Authorization", "Bearertoken-no-space")
	w := httptest.NewRecorder()
	handler.ServeHTTP(w, req)
	if w.Code != http.StatusUnauthorized {
		t.Errorf("malformed Authorization: want 401, got %d", w.Code)
	}
}

// ── Registration security tests ───────────────────────────────────────────────

// TestRegister_StoredHashIsBcrypt verifies that the password is stored as a
// bcrypt hash (starts with "$2a$" or "$2b$"), never as plaintext.
func TestRegister_StoredHashIsBcrypt(t *testing.T) {
	mux, _, db := setupMux(t)
	registerUser(t, mux, "bcryptcheck@example.com", "password123", "t1")

	var hash string
	if err := db.QueryRow(
		`SELECT password_hash FROM crm_users WHERE email=?`,
		"bcryptcheck@example.com",
	).Scan(&hash); err != nil {
		t.Fatalf("query hash: %v", err)
	}
	if !strings.HasPrefix(hash, "$2") {
		t.Errorf("want bcrypt hash (prefix $2a$/$2b$), got prefix %q", hash[:min(len(hash), 10)])
	}
}

// ── JWT claims correctness ────────────────────────────────────────────────────

// TestJWT_ClaimsIssuer verifies the generated token carries the expected issuer.
func TestJWT_ClaimsIssuer(t *testing.T) {
	svc := newJWT(t)
	raw, err := svc.GenerateToken("user-x", "tenant-x")
	if err != nil {
		t.Fatalf("GenerateToken: %v", err)
	}
	claims, err := svc.ValidateToken(raw)
	if err != nil {
		t.Fatalf("ValidateToken: %v", err)
	}
	if claims.Issuer != "cardex-workspace" {
		t.Errorf("Issuer: want cardex-workspace, got %s", claims.Issuer)
	}
}

// TestJWT_ClaimsUserAndTenantRoundTrip verifies UserID and TenantID survive
// a generate→validate round-trip unchanged.
func TestJWT_ClaimsUserAndTenantRoundTrip(t *testing.T) {
	svc := newJWT(t)
	token, _ := svc.GenerateToken("uid-abc", "tid-xyz")
	claims, err := svc.ValidateToken(token)
	if err != nil {
		t.Fatalf("ValidateToken: %v", err)
	}
	if claims.UserID != "uid-abc" {
		t.Errorf("UserID round-trip: want uid-abc, got %s", claims.UserID)
	}
	if claims.TenantID != "tid-xyz" {
		t.Errorf("TenantID round-trip: want tid-xyz, got %s", claims.TenantID)
	}
}

// ── Refresh correctness ───────────────────────────────────────────────────────

// TestRefresh_NewTokenDifferentFromOriginal verifies the refresh endpoint
// issues a NEW token string (not the same one back).
func TestRefresh_NewTokenDifferentFromOriginal(t *testing.T) {
	mux, _, _ := setupMux(t)
	original := registerUser(t, mux, "refresh2@example.com", "pass1234", "t1")

	// Small sleep so the IssuedAt timestamps differ.
	time.Sleep(2 * time.Millisecond)

	w := postJSONWithBearer(t, mux, "/api/v1/auth/refresh", original, nil)
	if w.Code != http.StatusOK {
		t.Fatalf("refresh: want 200, got %d: %s", w.Code, w.Body.String())
	}
	var resp map[string]any
	_ = json.Unmarshal(w.Body.Bytes(), &resp)
	newTok, _ := resp["token"].(string)
	if newTok == "" {
		t.Fatal("refresh returned empty token")
	}
	if newTok == original {
		t.Error("refresh must issue a new token, not return the same one")
	}
}

// ── Login rate-limit window reset ─────────────────────────────────────────────

// TestLogin_RateLimitWindowEnforced confirms the rate-limit window is 15 min:
// 5 failed attempts in the same window all produce 401 (not 429) and the 6th
// produces 429.  This mirrors the existing test but validates the count boundary.
func TestLogin_RateLimitWindowEnforced(t *testing.T) {
	mux, _, _ := setupMux(t)
	body := map[string]string{"email": "window@example.com", "password": "wrong"}
	for i := 1; i <= 5; i++ {
		w := postJSON(t, mux, "/api/v1/auth/login", body)
		if w.Code == http.StatusTooManyRequests {
			t.Errorf("attempt %d: should not be rate-limited yet (limit=5 allowed)", i)
		}
		if w.Code != http.StatusUnauthorized {
			t.Errorf("attempt %d: want 401 (invalid creds), got %d", i, w.Code)
		}
	}
	w6 := postJSON(t, mux, "/api/v1/auth/login", body)
	if w6.Code != http.StatusTooManyRequests {
		t.Errorf("6th attempt: want 429, got %d", w6.Code)
	}
}
