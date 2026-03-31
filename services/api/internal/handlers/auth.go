package handlers

import (
	"crypto/rsa"
	"encoding/json"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/oklog/ulid/v2"
	"golang.org/x/crypto/bcrypt"
)

// loadPrivateKey reads the RS256 private key from the path set in
// JWT_RS256_PRIVATE_KEY_FILE (defaults to /run/secrets/jwt_private_key).
// Returns nil if the file cannot be read (dev mode — register/login still
// work but tokens are signed with HS256 using JWT_DEV_SECRET).
func loadPrivateKey() *rsa.PrivateKey {
	path := envOrDefault("JWT_RS256_PRIVATE_KEY_FILE", "/run/secrets/jwt_private_key")
	b, err := os.ReadFile(path)
	if err != nil {
		return nil
	}
	k, err := jwt.ParseRSAPrivateKeyFromPEM(b)
	if err != nil {
		return nil
	}
	return k
}

var _privKey = loadPrivateKey() // loaded once at startup

// issueToken generates a signed JWT for the given subject (user/dealer ULID).
// Claims:
//
//	sub   — user ULID
//	role  — "DEALER" | "USER"
//	tier  — subscription tier (FREE / PRO / …)
//	iat   — issued at (Unix)
//	exp   — expiry (Unix, 24 h)
func issueToken(sub, role, tier string) (string, error) {
	now := time.Now()
	claims := jwt.MapClaims{
		"sub":  sub,
		"role": role,
		"tier": tier,
		"iat":  now.Unix(),
		"exp":  now.Add(24 * time.Hour).Unix(),
	}

	if _privKey != nil {
		tok := jwt.NewWithClaims(jwt.SigningMethodRS256, claims)
		return tok.SignedString(_privKey)
	}

	// Dev fallback: HS256 with a shared secret
	secret := envOrDefault("JWT_DEV_SECRET", "dev-secret-change-me-in-production")
	tok := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	return tok.SignedString([]byte(secret))
}

// DealerRegister POST /api/v1/auth/register
// Body: { email, password, legal_name, trade_name, country_code, vat_id }
func (d *Deps) DealerRegister(w http.ResponseWriter, r *http.Request) {
	var body struct {
		Email       string `json:"email"`
		Password    string `json:"password"`
		LegalName   string `json:"legal_name"`
		TradeName   string `json:"trade_name"`
		CountryCode string `json:"country_code"`
		VatID       string `json:"vat_id"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid_body", err.Error())
		return
	}

	body.Email = strings.ToLower(strings.TrimSpace(body.Email))
	if body.Email == "" || body.Password == "" || body.LegalName == "" || body.CountryCode == "" {
		writeError(w, http.StatusBadRequest, "missing_fields", "email, password, legal_name, country_code are required")
		return
	}
	if len(body.Password) < 10 {
		writeError(w, http.StatusBadRequest, "weak_password", "password must be at least 10 characters")
		return
	}
	if !strings.Contains(body.Email, "@") {
		writeError(w, http.StatusBadRequest, "invalid_email", "invalid email address")
		return
	}

	// Check uniqueness
	var exists bool
	d.DB.QueryRow(r.Context(), "SELECT EXISTS(SELECT 1 FROM users WHERE email = $1)", body.Email).Scan(&exists)
	if exists {
		writeError(w, http.StatusConflict, "email_taken", "an account with this email already exists")
		return
	}

	// Hash password (bcrypt cost 12)
	hash, err := bcrypt.GenerateFromPassword([]byte(body.Password), 12)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "hash_error", "failed to hash password")
		return
	}

	// Create entity + user in a single transaction
	tx, err := d.DB.Begin(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, "db_error", err.Error())
		return
	}
	defer tx.Rollback(r.Context())

	entityULID := ulid.Make().String()
	userULID := ulid.Make().String()

	// Minimal vault_dek_id — real KMS integration assigns per-entity key IDs
	vaultDEKID := "dek:" + entityULID

	_, err = tx.Exec(r.Context(), `
		INSERT INTO entities (
			entity_ulid, entity_type, legal_name, trade_name,
			country_code, vat_id, vault_dek_id, subscription_tier
		) VALUES ($1, 'DEALER', $2, $3, $4, $5, $6, 'FREE')
	`, entityULID, body.LegalName, nullableString(body.TradeName),
		strings.ToUpper(body.CountryCode), nullableString(body.VatID), vaultDEKID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "db_error", "failed to create entity: "+err.Error())
		return
	}

	_, err = tx.Exec(r.Context(), `
		INSERT INTO users (
			user_ulid, email, password_hash, full_name,
			country_code, is_dealer, entity_ulid, email_verified, vault_dek_id
		) VALUES ($1, $2, $3, $4, $5, true, $6, false, $7)
	`, userULID, body.Email, string(hash), body.LegalName,
		strings.ToUpper(body.CountryCode), entityULID, vaultDEKID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "db_error", "failed to create user: "+err.Error())
		return
	}

	if err := tx.Commit(r.Context()); err != nil {
		writeError(w, http.StatusInternalServerError, "db_error", "transaction commit failed")
		return
	}

	accessToken, err := issueToken(userULID, "DEALER", "FREE")
	if err != nil {
		writeError(w, http.StatusInternalServerError, "token_error", "failed to issue token")
		return
	}

	writeJSON(w, http.StatusCreated, map[string]any{
		"user_ulid":    userULID,
		"entity_ulid":  entityULID,
		"access_token": accessToken,
		"token_type":   "Bearer",
		"expires_in":   86400,
	})
}

// DealerLogin POST /api/v1/auth/login
// Body: { email, password }
func (d *Deps) DealerLogin(w http.ResponseWriter, r *http.Request) {
	var body struct {
		Email    string `json:"email"`
		Password string `json:"password"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid_body", err.Error())
		return
	}

	body.Email = strings.ToLower(strings.TrimSpace(body.Email))
	if body.Email == "" || body.Password == "" {
		writeError(w, http.StatusBadRequest, "missing_fields", "email and password are required")
		return
	}

	var userULID, passwordHash, entityULID string
	var isDealer bool
	var subscriptionTier string

	err := d.DB.QueryRow(r.Context(), `
		SELECT u.user_ulid, u.password_hash, u.entity_ulid, u.is_dealer,
		       COALESCE(e.subscription_tier, 'FREE')
		FROM users u
		LEFT JOIN entities e ON u.entity_ulid = e.entity_ulid
		WHERE u.email = $1
	`, body.Email).Scan(&userULID, &passwordHash, &entityULID, &isDealer, &subscriptionTier)
	if err != nil {
		// Use constant-time comparison to avoid timing oracle
		bcrypt.CompareHashAndPassword([]byte("$2a$12$dummyhashfortimingequalisation."), []byte(body.Password))
		writeError(w, http.StatusUnauthorized, "invalid_credentials", "email or password is incorrect")
		return
	}

	if err := bcrypt.CompareHashAndPassword([]byte(passwordHash), []byte(body.Password)); err != nil {
		writeError(w, http.StatusUnauthorized, "invalid_credentials", "email or password is incorrect")
		return
	}

	role := "USER"
	if isDealer {
		role = "DEALER"
	}

	accessToken, err := issueToken(userULID, role, subscriptionTier)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "token_error", "failed to issue token")
		return
	}

	// Issue refresh token
	refreshToken := ulid.Make().String() + ulid.Make().String()
	d.Redis.Set(r.Context(), "refresh:"+refreshToken, userULID, 30*24*time.Hour)

	// Update last_login_at
	d.DB.Exec(r.Context(), "UPDATE users SET last_login_at = NOW() WHERE user_ulid = $1", userULID)

	writeJSON(w, http.StatusOK, map[string]any{
		"user_ulid":     userULID,
		"entity_ulid":   entityULID,
		"access_token":  accessToken,
		"refresh_token": refreshToken,
		"token_type":    "Bearer",
		"expires_in":    86400,
		"role":          role,
		"tier":          subscriptionTier,
	})
}

// TokenRefresh POST /api/v1/auth/refresh
// Body: { refresh_token }
func (d *Deps) TokenRefresh(w http.ResponseWriter, r *http.Request) {
	var body struct {
		RefreshToken string `json:"refresh_token"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil || body.RefreshToken == "" {
		writeError(w, http.StatusBadRequest, "invalid_body", "refresh_token is required")
		return
	}

	// Look up user from refresh token
	userULID, err := d.Redis.Get(r.Context(), "refresh:"+body.RefreshToken).Result()
	if err != nil {
		writeError(w, http.StatusUnauthorized, "invalid_refresh_token", "refresh token is invalid or expired")
		return
	}

	var isDealer bool
	var entityULID, subscriptionTier string
	d.DB.QueryRow(r.Context(), `
		SELECT u.is_dealer, COALESCE(u.entity_ulid,''), COALESCE(e.subscription_tier,'FREE')
		FROM users u
		LEFT JOIN entities e ON u.entity_ulid = e.entity_ulid
		WHERE u.user_ulid = $1
	`, userULID).Scan(&isDealer, &entityULID, &subscriptionTier)

	role := "USER"
	if isDealer {
		role = "DEALER"
	}

	accessToken, err := issueToken(userULID, role, subscriptionTier)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "token_error", "failed to issue token")
		return
	}

	// Rotate refresh token (invalidate old, issue new)
	newRefreshToken := ulid.Make().String() + ulid.Make().String()
	d.Redis.Del(r.Context(), "refresh:"+body.RefreshToken)
	d.Redis.Set(r.Context(), "refresh:"+newRefreshToken, userULID, 30*24*time.Hour)

	writeJSON(w, http.StatusOK, map[string]any{
		"access_token":  accessToken,
		"refresh_token": newRefreshToken,
		"token_type":    "Bearer",
		"expires_in":    86400,
	})
}

// nullableString returns nil interface for empty strings, string otherwise.
// Used to insert NULL into optional DB fields.
func nullableString(s string) interface{} {
	if s == "" {
		return nil
	}
	return s
}
