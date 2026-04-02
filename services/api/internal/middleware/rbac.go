package middleware

import (
	"context"
	"net/http"

	"github.com/golang-jwt/jwt/v5"
)

// Roles disponibles en CARDEX
const (
	RoleOwner    = "OWNER"
	RoleManager  = "MANAGER"
	RoleSeller   = "SELLER"
	RoleMechanic = "MECHANIC"
	RoleViewer   = "VIEWER"
	RoleAdmin    = "ADMIN" // sistema
)

type claimsKey struct{}

// storeClaims injects JWT MapClaims into the context.
// Called internally by the Auth middleware so that RequireAdmin can inspect them.
func storeClaims(ctx context.Context, claims jwt.MapClaims) context.Context {
	return context.WithValue(ctx, claimsKey{}, map[string]any(claims))
}

// GetClaims retrieves the JWT claims map stored by the Auth middleware.
// Returns nil if no claims are present in the context.
func GetClaims(ctx context.Context) map[string]any {
	v, _ := ctx.Value(claimsKey{}).(map[string]any)
	return v
}

// RequireAdmin middleware — verifica que el JWT tenga role="ADMIN".
// Debe usarse después del middleware Auth (que valida la firma del token).
// Retorna http.HandlerFunc para ser compatible con middleware.Auth.
func RequireAdmin(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		claims := GetClaims(r.Context())
		if claims == nil {
			http.Error(w, `{"error":"unauthorized"}`, http.StatusUnauthorized)
			return
		}
		role, _ := claims["role"].(string)
		if role != RoleAdmin {
			http.Error(w, `{"error":"forbidden","message":"admin access required"}`, http.StatusForbidden)
			return
		}
		next(w, r)
	}
}
