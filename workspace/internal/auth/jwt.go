package auth

import (
	"errors"
	"fmt"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

// Claims holds the application-specific JWT payload.
type Claims struct {
	UserID   string `json:"sub"`
	TenantID string `json:"tenant_id"`
	jwt.RegisteredClaims
}

// JWTService signs and validates HS256 JWTs.
type JWTService struct {
	secret []byte
	expiry time.Duration
}

// NewJWTService creates a JWTService.
// secret must be at least 32 bytes in production.
// expiry is the token lifetime (e.g. 24*time.Hour).
func NewJWTService(secret []byte, expiry time.Duration) *JWTService {
	return &JWTService{secret: secret, expiry: expiry}
}

// GenerateToken creates a signed HS256 JWT for the given user and tenant.
func (s *JWTService) GenerateToken(userID, tenantID string) (string, error) {
	now := time.Now().UTC()
	claims := Claims{
		UserID:   userID,
		TenantID: tenantID,
		RegisteredClaims: jwt.RegisteredClaims{
			Subject:   userID,
			IssuedAt:  jwt.NewNumericDate(now),
			ExpiresAt: jwt.NewNumericDate(now.Add(s.expiry)),
			Issuer:    "cardex-workspace",
		},
	}
	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	signed, err := token.SignedString(s.secret)
	if err != nil {
		return "", fmt.Errorf("jwt sign: %w", err)
	}
	return signed, nil
}

// ValidateToken parses and validates a JWT string.
// Returns ErrTokenExpired, ErrTokenInvalid, or nil on success.
func (s *JWTService) ValidateToken(tokenString string) (*Claims, error) {
	token, err := jwt.ParseWithClaims(tokenString, &Claims{}, func(t *jwt.Token) (any, error) {
		if _, ok := t.Method.(*jwt.SigningMethodHMAC); !ok {
			return nil, fmt.Errorf("unexpected signing method: %v", t.Header["alg"])
		}
		return s.secret, nil
	})
	if err != nil {
		if errors.Is(err, jwt.ErrTokenExpired) {
			return nil, ErrTokenExpired
		}
		return nil, ErrTokenInvalid
	}
	claims, ok := token.Claims.(*Claims)
	if !ok || !token.Valid {
		return nil, ErrTokenInvalid
	}
	if claims.UserID == "" || claims.TenantID == "" {
		return nil, ErrTokenInvalid
	}
	return claims, nil
}

// Expiry returns the configured token lifetime.
func (s *JWTService) Expiry() time.Duration { return s.expiry }

// Sentinel errors returned by ValidateToken.
var (
	ErrTokenExpired = errors.New("token expired")
	ErrTokenInvalid = errors.New("token invalid")
)
