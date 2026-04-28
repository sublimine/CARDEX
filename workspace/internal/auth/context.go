package auth

import "context"

type contextKey int

const (
	ctxKeyUserID   contextKey = iota
	ctxKeyTenantID contextKey = iota
)

// UserIDFromCtx returns the authenticated user ID stored by RequireAuth.
func UserIDFromCtx(ctx context.Context) string {
	v, _ := ctx.Value(ctxKeyUserID).(string)
	return v
}

// TenantIDFromCtx returns the tenant ID stored by RequireAuth.
// Use this instead of the X-Tenant-ID header so tenant comes from the JWT.
func TenantIDFromCtx(ctx context.Context) string {
	v, _ := ctx.Value(ctxKeyTenantID).(string)
	return v
}
