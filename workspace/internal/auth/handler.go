package auth

import (
	"crypto/rand"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"strings"
	"time"

	"golang.org/x/crypto/bcrypt"
)

// Handler exposes the auth HTTP endpoints.
type Handler struct {
	db     *sql.DB
	jwtSvc *JWTService
	rl     *loginRateLimiter
}

// NewHandler creates a Handler.
func NewHandler(db *sql.DB, jwtSvc *JWTService) *Handler {
	return &Handler{db: db, jwtSvc: jwtSvc, rl: newLoginRateLimiter()}
}

// Register mounts auth routes on mux (all public — no auth middleware).
//
//	POST /api/v1/auth/login
//	POST /api/v1/auth/register
//	POST /api/v1/auth/refresh
func (h *Handler) Register(mux *http.ServeMux) {
	mux.HandleFunc("POST /api/v1/auth/login", h.login)
	mux.HandleFunc("POST /api/v1/auth/register", h.register)
	mux.HandleFunc("POST /api/v1/auth/refresh", h.refresh)
}

// ── Request / response types ──────────────────────────────────────────────────

type loginRequest struct {
	Email    string `json:"email"`
	Password string `json:"password"`
}

type registerRequest struct {
	Email    string `json:"email"`
	Password string `json:"password"`
	Name     string `json:"name"`
	TenantID string `json:"tenant_id"`
}

type tokenResponse struct {
	Token     string   `json:"token"`
	ExpiresIn int      `json:"expires_in"` // seconds
	TenantID  string   `json:"tenant_id"`
	User      userView `json:"user"`
}

type userView struct {
	ID       string `json:"id"`
	Email    string `json:"email"`
	Name     string `json:"name"`
	Role     string `json:"role"`
	TenantID string `json:"tenant_id"`
}

// ── Handlers ──────────────────────────────────────────────────────────────────

// POST /api/v1/auth/login
func (h *Handler) login(w http.ResponseWriter, r *http.Request) {
	ip := clientIP(r)
	if !h.rl.Allow(ip) {
		jsonAuthErr(w, http.StatusTooManyRequests, "too many login attempts — try again in 15 minutes")
		return
	}

	var req loginRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		jsonAuthErr(w, http.StatusBadRequest, "invalid JSON")
		return
	}
	req.Email = strings.ToLower(strings.TrimSpace(req.Email))
	if req.Email == "" || req.Password == "" {
		jsonAuthErr(w, http.StatusBadRequest, "email and password required")
		return
	}

	var u userView
	var hash string
	err := h.db.QueryRowContext(r.Context(),
		`SELECT id, email, name, role, tenant_id, password_hash
		 FROM crm_users WHERE email=? LIMIT 1`, req.Email).
		Scan(&u.ID, &u.Email, &u.Name, &u.Role, &u.TenantID, &hash)
	if err == sql.ErrNoRows {
		jsonAuthErr(w, http.StatusUnauthorized, "invalid email or password")
		return
	}
	if err != nil {
		jsonAuthErr(w, http.StatusInternalServerError, "internal error")
		return
	}

	if err := bcrypt.CompareHashAndPassword([]byte(hash), []byte(req.Password)); err != nil {
		jsonAuthErr(w, http.StatusUnauthorized, "invalid email or password")
		return
	}

	h.rl.Reset(ip)

	token, err := h.jwtSvc.GenerateToken(u.ID, u.TenantID)
	if err != nil {
		jsonAuthErr(w, http.StatusInternalServerError, "token generation failed")
		return
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(w).Encode(tokenResponse{
		Token:     token,
		ExpiresIn: int(h.jwtSvc.Expiry().Seconds()),
		TenantID:  u.TenantID,
		User:      u,
	})
}

// POST /api/v1/auth/register
func (h *Handler) register(w http.ResponseWriter, r *http.Request) {
	var req registerRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		jsonAuthErr(w, http.StatusBadRequest, "invalid JSON")
		return
	}
	req.Email = strings.ToLower(strings.TrimSpace(req.Email))
	if req.Email == "" || req.Password == "" || req.TenantID == "" {
		jsonAuthErr(w, http.StatusBadRequest, "email, password, and tenant_id required")
		return
	}
	if len(req.Password) < 8 {
		jsonAuthErr(w, http.StatusBadRequest, "password must be at least 8 characters")
		return
	}

	hash, err := bcrypt.GenerateFromPassword([]byte(req.Password), bcrypt.DefaultCost)
	if err != nil {
		jsonAuthErr(w, http.StatusInternalServerError, "internal error")
		return
	}

	id := newUserID()
	now := time.Now().UTC().Format(time.RFC3339)
	_, err = h.db.ExecContext(r.Context(),
		`INSERT INTO crm_users(id,tenant_id,email,password_hash,name,role,created_at,updated_at)
		 VALUES(?,?,?,?,?,?,?,?)`,
		id, req.TenantID, req.Email, string(hash),
		req.Name, "dealer", now, now)
	if err != nil {
		if strings.Contains(err.Error(), "UNIQUE") {
			jsonAuthErr(w, http.StatusConflict, "email already registered for this tenant")
			return
		}
		jsonAuthErr(w, http.StatusInternalServerError, "internal error")
		return
	}

	token, err := h.jwtSvc.GenerateToken(id, req.TenantID)
	if err != nil {
		jsonAuthErr(w, http.StatusInternalServerError, "token generation failed")
		return
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusCreated)
	_ = json.NewEncoder(w).Encode(tokenResponse{
		Token:     token,
		ExpiresIn: int(h.jwtSvc.Expiry().Seconds()),
		TenantID:  req.TenantID,
		User: userView{
			ID:       id,
			Email:    req.Email,
			Name:     req.Name,
			Role:     "dealer",
			TenantID: req.TenantID,
		},
	})
}

// POST /api/v1/auth/refresh — B-08
// Accepts a valid (not necessarily fresh) token and issues a new one.
// Tokens that have already expired are rejected.
func (h *Handler) refresh(w http.ResponseWriter, r *http.Request) {
	token := extractBearer(r)
	if token == "" {
		jsonAuthErr(w, http.StatusUnauthorized, "authorization header required")
		return
	}
	claims, err := h.jwtSvc.ValidateToken(token)
	if err != nil {
		msg := "invalid token"
		if err == ErrTokenExpired {
			msg = "token expired — please log in again"
		}
		jsonAuthErr(w, http.StatusUnauthorized, msg)
		return
	}

	// Verify user still exists in DB.
	var u userView
	dbErr := h.db.QueryRowContext(r.Context(),
		`SELECT id, email, name, role, tenant_id FROM crm_users WHERE id=?`, claims.UserID).
		Scan(&u.ID, &u.Email, &u.Name, &u.Role, &u.TenantID)
	if dbErr == sql.ErrNoRows {
		jsonAuthErr(w, http.StatusUnauthorized, "user no longer exists")
		return
	}
	if dbErr != nil {
		jsonAuthErr(w, http.StatusInternalServerError, "internal error")
		return
	}

	newToken, err := h.jwtSvc.GenerateToken(u.ID, u.TenantID)
	if err != nil {
		jsonAuthErr(w, http.StatusInternalServerError, "token generation failed")
		return
	}

	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(tokenResponse{
		Token:     newToken,
		ExpiresIn: int(h.jwtSvc.Expiry().Seconds()),
		TenantID:  u.TenantID,
		User:      u,
	})
}

// ── helpers ───────────────────────────────────────────────────────────────────

func clientIP(r *http.Request) string {
	if xff := r.Header.Get("X-Forwarded-For"); xff != "" {
		return strings.SplitN(xff, ",", 2)[0]
	}
	ip := r.RemoteAddr
	if idx := strings.LastIndex(ip, ":"); idx != -1 {
		return ip[:idx]
	}
	return ip
}

func newUserID() string {
	b := make([]byte, 16)
	_, _ = rand.Read(b)
	return hex.EncodeToString(b)
}
