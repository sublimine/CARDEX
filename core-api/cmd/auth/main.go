package main

import (
	"database/sql"
	"encoding/json"
	"log/slog"
	"net/http"
	"os"
	"time"

	"github.com/golang-jwt/jwt/v5"
	_ "github.com/lib/pq"
	"golang.org/x/crypto/bcrypt"
)

var db *sql.DB

type AuthRequest struct {
	Email    string `json:"email"`
	Password string `json:"password"`
}

type AuthResponse struct {
	Token        string  `json:"token"`
	TokenBalance int     `json:"token_balance"`
	TrustScore   float64 `json:"trust_score"`
}

func init() {
	connStr := os.Getenv("DATABASE_URL")
	if connStr == "" {
		connStr = "postgres://cardex_admin:alpha_secure_99@127.0.0.1:5432/cardex_core?sslmode=disable"
	}

	var err error
	db, err = sql.Open("postgres", connStr)
	if err != nil {
		slog.Error("phase:auth postgres connection failed", "error", err)
		os.Exit(1)
	}

	if err := db.Ping(); err != nil {
		slog.Error("phase:auth postgres ping failed", "error", err)
		os.Exit(1)
	}
}

func jwtSecret() []byte {
	secret := os.Getenv("JWT_SECRET")
	if secret == "" {
		secret = "alpha_cardex_super_secret_99"
	}
	return []byte(secret)
}

func hashPassword(password string) (string, error) {
	bytes, err := bcrypt.GenerateFromPassword([]byte(password), 14)
	return string(bytes), err
}

func checkPasswordHash(password, hash string) bool {
	err := bcrypt.CompareHashAndPassword([]byte(hash), []byte(password))
	return err == nil
}

func registerHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, `{"error":"method not allowed"}`, http.StatusMethodNotAllowed)
		return
	}

	var req AuthRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, `{"error":"invalid JSON"}`, http.StatusBadRequest)
		return
	}

	if req.Email == "" || req.Password == "" {
		http.Error(w, `{"error":"email and password required"}`, http.StatusBadRequest)
		return
	}

	hash, err := hashPassword(req.Password)
	if err != nil {
		slog.Error("phase:auth hash failed", "error", err)
		http.Error(w, `{"error":"internal error"}`, http.StatusInternalServerError)
		return
	}

	_, err = db.Exec(`INSERT INTO dealers (email, password_hash, token_balance) VALUES ($1, $2, 100)`, req.Email, hash)
	if err != nil {
		http.Error(w, `{"error":"email already registered or SQL error"}`, http.StatusConflict)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusCreated)
	json.NewEncoder(w).Encode(map[string]interface{}{
		"status":          "DEALER_CREATED",
		"initial_balance": 100,
	})
	slog.Info("phase:auth dealer registered", "email", req.Email)
}

func loginHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, `{"error":"method not allowed"}`, http.StatusMethodNotAllowed)
		return
	}

	var req AuthRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, `{"error":"invalid JSON"}`, http.StatusBadRequest)
		return
	}

	if req.Email == "" || req.Password == "" {
		http.Error(w, `{"error":"email and password required"}`, http.StatusBadRequest)
		return
	}

	var id, storedHash string
	var balance int
	var trust float64

	err := db.QueryRow(`SELECT id, password_hash, token_balance, trust_score FROM dealers WHERE email = $1`, req.Email).
		Scan(&id, &storedHash, &balance, &trust)

	if err == sql.ErrNoRows || !checkPasswordHash(req.Password, storedHash) {
		http.Error(w, `{"error":"invalid B2B credentials"}`, http.StatusUnauthorized)
		return
	}
	if err != nil {
		slog.Error("phase:auth query failed", "error", err)
		http.Error(w, `{"error":"internal error"}`, http.StatusInternalServerError)
		return
	}

	token := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.MapClaims{
		"dealer_id": id,
		"exp":       time.Now().Add(time.Hour * 24).Unix(),
	})
	tokenString, err := token.SignedString(jwtSecret())
	if err != nil {
		slog.Error("phase:auth jwt sign failed", "error", err)
		http.Error(w, `{"error":"internal error"}`, http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(AuthResponse{
		Token:        tokenString,
		TokenBalance: balance,
		TrustScore:   trust,
	})
	slog.Info("phase:auth session granted", "dealer_id", id, "balance", balance)
}

func main() {
	http.HandleFunc("/api/auth/register", registerHandler)
	http.HandleFunc("/api/auth/login", loginHandler)

	slog.Info("phase:auth gateway online", "port", 8085)
	if err := http.ListenAndServe(":8085", nil); err != nil {
		slog.Error("phase:auth listen failed", "error", err)
		os.Exit(1)
	}
}
