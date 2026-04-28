package auth_test

import (
	"bytes"
	"database/sql"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	_ "modernc.org/sqlite"

	"cardex.eu/workspace/internal/auth"
)

// ── helpers ───────────────────────────────────────────────────────────────────

func openDB(t *testing.T) *sql.DB {
	t.Helper()
	db, err := sql.Open("sqlite", ":memory:")
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	db.SetMaxOpenConns(1)
	t.Cleanup(func() { db.Close() })
	if err := auth.EnsureSchema(db); err != nil {
		t.Fatalf("EnsureSchema: %v", err)
	}
	return db
}

func newJWT(t *testing.T) *auth.JWTService {
	t.Helper()
	return auth.NewJWTService([]byte("test-secret-must-be-32-bytes-000"), 24*time.Hour)
}

func newShortJWT(t *testing.T) *auth.JWTService {
	t.Helper()
	return auth.NewJWTService([]byte("test-secret-must-be-32-bytes-000"), 1*time.Millisecond)
}

const testRegisterToken = "test-register-token-for-unit-tests"

func newHandler(t *testing.T) (*auth.Handler, *sql.DB) {
	t.Helper()
	db := openDB(t)
	return auth.NewHandlerForTest(db, newJWT(t), testRegisterToken), db
}

func postJSON(t *testing.T, handler http.Handler, path string, body any) *httptest.ResponseRecorder {
	t.Helper()
	b, _ := json.Marshal(body)
	req := httptest.NewRequest(http.MethodPost, path, bytes.NewReader(b))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	handler.ServeHTTP(w, req)
	return w
}

func postRegister(t *testing.T, handler http.Handler, body any) *httptest.ResponseRecorder {
	t.Helper()
	b, _ := json.Marshal(body)
	req := httptest.NewRequest(http.MethodPost, "/api/v1/auth/register", bytes.NewReader(b))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Register-Token", testRegisterToken)
	w := httptest.NewRecorder()
	handler.ServeHTTP(w, req)
	return w
}

func postJSONWithBearer(t *testing.T, handler http.Handler, path, token string, body any) *httptest.ResponseRecorder {
	t.Helper()
	b, _ := json.Marshal(body)
	req := httptest.NewRequest(http.MethodPost, path, bytes.NewReader(b))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+token)
	w := httptest.NewRecorder()
	handler.ServeHTTP(w, req)
	return w
}

func setupMux(t *testing.T) (*http.ServeMux, *auth.Handler, *sql.DB) {
	t.Helper()
	h, db := newHandler(t)
	mux := http.NewServeMux()
	h.Register(mux)
	return mux, h, db
}

func registerUser(t *testing.T, mux http.Handler, email, password, tenantID string) string {
	t.Helper()
	b, _ := json.Marshal(map[string]string{
		"email":     email,
		"password":  password,
		"tenant_id": tenantID,
		"name":      "Test User",
	})
	req := httptest.NewRequest(http.MethodPost, "/api/v1/auth/register", bytes.NewReader(b))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Register-Token", testRegisterToken)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)
	if w.Code != http.StatusCreated {
		t.Fatalf("registerUser: want 201, got %d: %s", w.Code, w.Body.String())
	}
	var resp map[string]any
	_ = json.Unmarshal(w.Body.Bytes(), &resp)
	return resp["token"].(string)
}

// ── JWT tests ─────────────────────────────────────────────────────────────────

func TestJWT_GenerateAndValidate(t *testing.T) {
	svc := newJWT(t)
	token, err := svc.GenerateToken("user-1", "tenant-1")
	if err != nil {
		t.Fatalf("GenerateToken: %v", err)
	}
	if token == "" {
		t.Fatal("GenerateToken returned empty string")
	}
	claims, err := svc.ValidateToken(token)
	if err != nil {
		t.Fatalf("ValidateToken: %v", err)
	}
	if claims.UserID != "user-1" {
		t.Errorf("UserID: want user-1, got %s", claims.UserID)
	}
	if claims.TenantID != "tenant-1" {
		t.Errorf("TenantID: want tenant-1, got %s", claims.TenantID)
	}
}

func TestJWT_ExpiredToken(t *testing.T) {
	svc := newShortJWT(t)
	token, err := svc.GenerateToken("user-1", "tenant-1")
	if err != nil {
		t.Fatalf("GenerateToken: %v", err)
	}
	time.Sleep(5 * time.Millisecond)
	_, err = svc.ValidateToken(token)
	if err != auth.ErrTokenExpired {
		t.Errorf("want ErrTokenExpired, got %v", err)
	}
}

func TestJWT_InvalidSignature(t *testing.T) {
	svc1 := auth.NewJWTService([]byte("secret-one-32-bytes-padding-here"), 24*time.Hour)
	svc2 := auth.NewJWTService([]byte("secret-two-32-bytes-padding-here"), 24*time.Hour)
	token, _ := svc1.GenerateToken("user-1", "tenant-1")
	_, err := svc2.ValidateToken(token)
	if err != auth.ErrTokenInvalid {
		t.Errorf("want ErrTokenInvalid, got %v", err)
	}
}

func TestJWT_MalformedToken(t *testing.T) {
	svc := newJWT(t)
	_, err := svc.ValidateToken("not.a.jwt.at.all")
	if err != auth.ErrTokenInvalid {
		t.Errorf("want ErrTokenInvalid, got %v", err)
	}
}

func TestJWT_EmptyToken(t *testing.T) {
	svc := newJWT(t)
	_, err := svc.ValidateToken("")
	if err != auth.ErrTokenInvalid {
		t.Errorf("want ErrTokenInvalid, got %v", err)
	}
}

func TestJWT_Expiry(t *testing.T) {
	svc := auth.NewJWTService([]byte("test-secret-must-be-32-bytes-000"), 7*24*time.Hour)
	if svc.Expiry() != 7*24*time.Hour {
		t.Errorf("Expiry: want 168h, got %v", svc.Expiry())
	}
}

// ── Register tests ────────────────────────────────────────────────────────────

func TestRegister_DisabledWhenNoToken(t *testing.T) {
	db := openDB(t)
	h := auth.NewHandlerForTest(db, newJWT(t), "") // empty token = disabled
	mux := http.NewServeMux()
	h.Register(mux)
	w := postRegister(t, mux, map[string]string{
		"email": "any@example.com", "password": "password123", "tenant_id": "t1",
	})
	if w.Code != http.StatusForbidden {
		t.Errorf("want 403 when disabled, got %d", w.Code)
	}
}

func TestRegister_WrongToken(t *testing.T) {
	mux, _, _ := setupMux(t)
	b, _ := json.Marshal(map[string]string{
		"email": "any@example.com", "password": "password123", "tenant_id": "t1",
	})
	req := httptest.NewRequest(http.MethodPost, "/api/v1/auth/register", bytes.NewReader(b))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Register-Token", "wrong-token")
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)
	if w.Code != http.StatusForbidden {
		t.Errorf("want 403 for wrong token, got %d", w.Code)
	}
}

func TestRegister_Success(t *testing.T) {
	mux, _, _ := setupMux(t)
	w := postRegister(t, mux, map[string]string{
		"email":     "alice@example.com",
		"password":  "password123",
		"tenant_id": "t1",
		"name":      "Alice",
	})
	if w.Code != http.StatusCreated {
		t.Fatalf("want 201, got %d: %s", w.Code, w.Body.String())
	}
	var resp map[string]any
	_ = json.Unmarshal(w.Body.Bytes(), &resp)
	if resp["token"] == nil || resp["token"].(string) == "" {
		t.Error("response missing token")
	}
	if resp["tenant_id"] != "t1" {
		t.Errorf("tenant_id: want t1, got %v", resp["tenant_id"])
	}
	user := resp["user"].(map[string]any)
	if user["email"] != "alice@example.com" {
		t.Errorf("user.email: want alice@example.com, got %v", user["email"])
	}
	if user["role"] != "dealer" {
		t.Errorf("user.role: want dealer, got %v", user["role"])
	}
}

func TestRegister_DuplicateEmail(t *testing.T) {
	mux, _, _ := setupMux(t)
	body := map[string]string{"email": "dup@example.com", "password": "password123", "tenant_id": "t1", "name": "X"}
	postRegister(t, mux, body)
	w := postRegister(t, mux, body)
	if w.Code != http.StatusConflict {
		t.Errorf("want 409, got %d", w.Code)
	}
}

func TestRegister_PasswordTooShort(t *testing.T) {
	mux, _, _ := setupMux(t)
	w := postRegister(t, mux, map[string]string{
		"email": "short@example.com", "password": "abc", "tenant_id": "t1",
	})
	if w.Code != http.StatusBadRequest {
		t.Errorf("want 400, got %d", w.Code)
	}
}

func TestRegister_MissingEmail(t *testing.T) {
	mux, _, _ := setupMux(t)
	w := postRegister(t, mux, map[string]string{
		"password": "password123", "tenant_id": "t1",
	})
	if w.Code != http.StatusBadRequest {
		t.Errorf("want 400, got %d", w.Code)
	}
}

func TestRegister_MissingTenantID(t *testing.T) {
	mux, _, _ := setupMux(t)
	w := postRegister(t, mux, map[string]string{
		"email": "notenant@example.com", "password": "password123",
	})
	if w.Code != http.StatusBadRequest {
		t.Errorf("want 400, got %d", w.Code)
	}
}

func TestRegister_InvalidJSON(t *testing.T) {
	mux, _, _ := setupMux(t)
	req := httptest.NewRequest(http.MethodPost, "/api/v1/auth/register", strings.NewReader("{bad json"))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Register-Token", testRegisterToken)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)
	if w.Code != http.StatusBadRequest {
		t.Errorf("want 400, got %d", w.Code)
	}
}

// ── Login tests ───────────────────────────────────────────────────────────────

func TestLogin_Success(t *testing.T) {
	mux, _, _ := setupMux(t)
	registerUser(t, mux, "bob@example.com", "mypassword", "t1")

	w := postJSON(t, mux, "/api/v1/auth/login", map[string]string{
		"email": "bob@example.com", "password": "mypassword",
	})
	if w.Code != http.StatusOK {
		t.Fatalf("want 200, got %d: %s", w.Code, w.Body.String())
	}
	var resp map[string]any
	_ = json.Unmarshal(w.Body.Bytes(), &resp)
	if resp["token"] == nil || resp["token"].(string) == "" {
		t.Error("response missing token")
	}
}

func TestLogin_WrongPassword(t *testing.T) {
	mux, _, _ := setupMux(t)
	registerUser(t, mux, "carol@example.com", "correctpass", "t1")

	w := postJSON(t, mux, "/api/v1/auth/login", map[string]string{
		"email": "carol@example.com", "password": "wrongpass",
	})
	if w.Code != http.StatusUnauthorized {
		t.Errorf("want 401, got %d", w.Code)
	}
}

func TestLogin_UserNotFound(t *testing.T) {
	mux, _, _ := setupMux(t)
	w := postJSON(t, mux, "/api/v1/auth/login", map[string]string{
		"email": "nobody@example.com", "password": "somepass",
	})
	if w.Code != http.StatusUnauthorized {
		t.Errorf("want 401, got %d", w.Code)
	}
}

func TestLogin_MissingFields(t *testing.T) {
	mux, _, _ := setupMux(t)
	w := postJSON(t, mux, "/api/v1/auth/login", map[string]string{"email": "x@x.com"})
	if w.Code != http.StatusBadRequest {
		t.Errorf("want 400, got %d", w.Code)
	}
}

func TestLogin_RateLimitBlocks6thAttempt(t *testing.T) {
	mux, _, _ := setupMux(t)
	// Exhaust 5 allowed attempts with wrong credentials.
	body := map[string]string{"email": "victim@example.com", "password": "wrong"}
	for i := 0; i < 5; i++ {
		w := postJSON(t, mux, "/api/v1/auth/login", body)
		if w.Code != http.StatusUnauthorized {
			t.Fatalf("attempt %d: want 401, got %d", i+1, w.Code)
		}
	}
	// 6th attempt must be rate-limited.
	w := postJSON(t, mux, "/api/v1/auth/login", body)
	if w.Code != http.StatusTooManyRequests {
		t.Errorf("6th attempt: want 429, got %d: %s", w.Code, w.Body.String())
	}
}

func TestLogin_SuccessResetsRateLimit(t *testing.T) {
	mux, _, _ := setupMux(t)
	email := "dave@example.com"
	registerUser(t, mux, email, "rightpass", "t1")

	// 3 failed attempts.
	for i := 0; i < 3; i++ {
		postJSON(t, mux, "/api/v1/auth/login", map[string]string{"email": email, "password": "wrong"})
	}
	// Successful login resets counter.
	w := postJSON(t, mux, "/api/v1/auth/login", map[string]string{"email": email, "password": "rightpass"})
	if w.Code != http.StatusOK {
		t.Fatalf("want 200 after success, got %d", w.Code)
	}
	// Should be able to fail again without being rate-limited.
	for i := 0; i < 5; i++ {
		w := postJSON(t, mux, "/api/v1/auth/login", map[string]string{"email": email, "password": "wrong"})
		if w.Code == http.StatusTooManyRequests {
			t.Errorf("attempt %d after reset: unexpectedly rate-limited", i+1)
		}
	}
}

func TestLogin_EmailCaseInsensitive(t *testing.T) {
	mux, _, _ := setupMux(t)
	registerUser(t, mux, "eve@example.com", "mypassword", "t1")

	w := postJSON(t, mux, "/api/v1/auth/login", map[string]string{
		"email": "EVE@EXAMPLE.COM", "password": "mypassword",
	})
	if w.Code != http.StatusOK {
		t.Errorf("want 200, got %d", w.Code)
	}
}

// ── Refresh tests ─────────────────────────────────────────────────────────────

func TestRefresh_Success(t *testing.T) {
	mux, _, _ := setupMux(t)
	token := registerUser(t, mux, "frank@example.com", "mypassword", "t1")

	w := postJSONWithBearer(t, mux, "/api/v1/auth/refresh", token, nil)
	if w.Code != http.StatusOK {
		t.Fatalf("want 200, got %d: %s", w.Code, w.Body.String())
	}
	var resp map[string]any
	_ = json.Unmarshal(w.Body.Bytes(), &resp)
	newToken, _ := resp["token"].(string)
	if newToken == "" {
		t.Error("response missing new token")
	}
}

func TestRefresh_MissingToken(t *testing.T) {
	mux, _, _ := setupMux(t)
	req := httptest.NewRequest(http.MethodPost, "/api/v1/auth/refresh", nil)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)
	if w.Code != http.StatusUnauthorized {
		t.Errorf("want 401, got %d", w.Code)
	}
}

func TestRefresh_ExpiredToken(t *testing.T) {
	db := openDB(t)
	shortJWT := newShortJWT(t)
	h := auth.NewHandlerForTest(db, shortJWT, testRegisterToken)
	mux := http.NewServeMux()
	h.Register(mux)

	// Register with short-lived token.
	w := postRegister(t, mux, map[string]string{
		"email": "g@g.com", "password": "password1", "tenant_id": "t1",
	})
	if w.Code != http.StatusCreated {
		t.Fatalf("register: want 201, got %d: %s", w.Code, w.Body.String())
	}
	var resp map[string]any
	_ = json.Unmarshal(w.Body.Bytes(), &resp)
	token, _ := resp["token"].(string)

	time.Sleep(5 * time.Millisecond) // let token expire

	w2 := postJSONWithBearer(t, mux, "/api/v1/auth/refresh", token, nil)
	if w2.Code != http.StatusUnauthorized {
		t.Errorf("want 401 for expired token, got %d", w2.Code)
	}
}

func TestRefresh_InvalidToken(t *testing.T) {
	mux, _, _ := setupMux(t)
	w := postJSONWithBearer(t, mux, "/api/v1/auth/refresh", "invalid.token.here", nil)
	if w.Code != http.StatusUnauthorized {
		t.Errorf("want 401, got %d", w.Code)
	}
}

// ── Middleware tests ──────────────────────────────────────────────────────────

func TestRequireAuth_ValidToken(t *testing.T) {
	svc := newJWT(t)
	token, _ := svc.GenerateToken("user-99", "tenant-99")

	sentinel := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})
	handler := auth.RequireAuth(svc)(sentinel)

	req := httptest.NewRequest(http.MethodGet, "/", nil)
	req.Header.Set("Authorization", "Bearer "+token)
	w := httptest.NewRecorder()
	handler.ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Errorf("want 200, got %d", w.Code)
	}
}

func TestRequireAuth_MissingToken(t *testing.T) {
	svc := newJWT(t)
	handler := auth.RequireAuth(svc)(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	req := httptest.NewRequest(http.MethodGet, "/", nil)
	w := httptest.NewRecorder()
	handler.ServeHTTP(w, req)
	if w.Code != http.StatusUnauthorized {
		t.Errorf("want 401, got %d", w.Code)
	}
}

func TestRequireAuth_ExpiredToken(t *testing.T) {
	svc := newShortJWT(t)
	token, _ := svc.GenerateToken("user-1", "tenant-1")
	time.Sleep(5 * time.Millisecond)

	handler := auth.RequireAuth(svc)(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	req := httptest.NewRequest(http.MethodGet, "/", nil)
	req.Header.Set("Authorization", "Bearer "+token)
	w := httptest.NewRecorder()
	handler.ServeHTTP(w, req)
	if w.Code != http.StatusUnauthorized {
		t.Errorf("want 401, got %d", w.Code)
	}
}

func TestRequireAuth_UserIDInContext(t *testing.T) {
	svc := newJWT(t)
	token, _ := svc.GenerateToken("user-abc", "tenant-xyz")

	var gotUserID, gotTenantID string
	handler := auth.RequireAuth(svc)(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotUserID = auth.UserIDFromCtx(r.Context())
		gotTenantID = auth.TenantIDFromCtx(r.Context())
		w.WriteHeader(http.StatusOK)
	}))

	req := httptest.NewRequest(http.MethodGet, "/", nil)
	req.Header.Set("Authorization", "Bearer "+token)
	w := httptest.NewRecorder()
	handler.ServeHTTP(w, req)

	if gotUserID != "user-abc" {
		t.Errorf("UserIDFromCtx: want user-abc, got %s", gotUserID)
	}
	if gotTenantID != "tenant-xyz" {
		t.Errorf("TenantIDFromCtx: want tenant-xyz, got %s", gotTenantID)
	}
}

func TestRequireAuth_InvalidAlgorithmRejected(t *testing.T) {
	svc := newJWT(t)
	// Pass a structurally invalid token (none alg or garbage).
	handler := auth.RequireAuth(svc)(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	req := httptest.NewRequest(http.MethodGet, "/", nil)
	req.Header.Set("Authorization", "Bearer eyJhbGciOiJub25lIn0.e30.")
	w := httptest.NewRecorder()
	handler.ServeHTTP(w, req)
	if w.Code != http.StatusUnauthorized {
		t.Errorf("want 401, got %d", w.Code)
	}
}

// ── Context helpers tests ─────────────────────────────────────────────────────

func TestContextHelpers_EmptyContext(t *testing.T) {
	h := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		uid := auth.UserIDFromCtx(r.Context())
		tid := auth.TenantIDFromCtx(r.Context())
		if uid != "" {
			t.Errorf("UserIDFromCtx with no value: want empty, got %s", uid)
		}
		if tid != "" {
			t.Errorf("TenantIDFromCtx with no value: want empty, got %s", tid)
		}
	})
	req := httptest.NewRequest(http.MethodGet, "/", nil)
	h.ServeHTTP(httptest.NewRecorder(), req)
}

// ── Response shape tests ──────────────────────────────────────────────────────

func TestLogin_ResponseShape(t *testing.T) {
	mux, _, _ := setupMux(t)
	registerUser(t, mux, "shape@example.com", "testpass1", "t1")
	w := postJSON(t, mux, "/api/v1/auth/login", map[string]string{
		"email": "shape@example.com", "password": "testpass1",
	})
	var resp map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	for _, field := range []string{"token", "expires_in", "tenant_id", "user"} {
		if resp[field] == nil {
			t.Errorf("response missing field %q", field)
		}
	}
	user, _ := resp["user"].(map[string]any)
	for _, field := range []string{"id", "email", "name", "role", "tenant_id"} {
		if user[field] == nil {
			t.Errorf("user missing field %q", field)
		}
	}
}

func TestRegister_ContentTypeJSON(t *testing.T) {
	mux, _, _ := setupMux(t)
	w := postJSON(t, mux, "/api/v1/auth/register", map[string]string{
		"email": "ct@example.com", "password": "testpass1", "tenant_id": "t1",
	})
	ct := w.Header().Get("Content-Type")
	if !strings.HasPrefix(ct, "application/json") {
		t.Errorf("Content-Type: want application/json, got %s", ct)
	}
}
