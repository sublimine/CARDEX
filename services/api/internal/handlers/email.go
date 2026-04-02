package handlers

// email.go — password reset, email verification, SMTP mailer.
// Configuration via env:
//   SMTP_HOST   (default: localhost)
//   SMTP_PORT   (default: 587)
//   SMTP_USER
//   SMTP_PASS
//   SMTP_FROM   (default: noreply@cardex.eu)
//   APP_URL     (default: http://localhost:3001)

import (
	"bytes"
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"net/smtp"
	"strings"
	"time"

	"golang.org/x/crypto/bcrypt"
)

// ── Mailer ────────────────────────────────────────────────────────────────────

type mailer struct {
	host string
	port string
	user string
	pass string
	from string
}

func newMailer() *mailer {
	return &mailer{
		host: envOrDefault("SMTP_HOST", "localhost"),
		port: envOrDefault("SMTP_PORT", "587"),
		user: envOrDefault("SMTP_USER", ""),
		pass: envOrDefault("SMTP_PASS", ""),
		from: envOrDefault("SMTP_FROM", "noreply@cardex.eu"),
	}
}

func (m *mailer) send(to, subject, htmlBody string) error {
	if m.user == "" {
		// SMTP not configured — print to stdout (dev mode)
		fmt.Printf("[MAIL dev] to=%s subject=%s\n  body: %s...\n", to, subject, truncate(htmlBody, 120))
		return nil
	}
	addr := net.JoinHostPort(m.host, m.port)
	auth := smtp.PlainAuth("", m.user, m.pass, m.host)
	var b bytes.Buffer
	b.WriteString("From: CARDEX <" + m.from + ">\r\n")
	b.WriteString("To: " + to + "\r\n")
	b.WriteString("Subject: " + subject + "\r\n")
	b.WriteString("MIME-Version: 1.0\r\n")
	b.WriteString("Content-Type: text/html; charset=UTF-8\r\n")
	b.WriteString("\r\n")
	b.WriteString(htmlBody)
	return smtp.SendMail(addr, auth, m.from, []string{to}, b.Bytes())
}

func truncate(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n] + "..."
}

// ── Secure token ──────────────────────────────────────────────────────────────

func secureToken(n int) string {
	b := make([]byte, n)
	rand.Read(b)
	return hex.EncodeToString(b)
}

// ── ForgotPassword POST /api/v1/auth/forgot-password ─────────────────────────
func (d *Deps) ForgotPassword(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Email string `json:"email"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid_body", err.Error())
		return
	}
	req.Email = strings.ToLower(strings.TrimSpace(req.Email))
	if req.Email == "" {
		writeError(w, http.StatusBadRequest, "missing_field", "email is required")
		return
	}

	// Respond 200 immediately — never reveal whether email exists
	writeJSON(w, http.StatusOK, map[string]string{
		"message": "Si ese email existe, recibirás un enlace en los próximos minutos.",
	})

	go func() {
		ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
		defer cancel()

		var userULID, fullName string
		if err := d.DB.QueryRow(ctx,
			"SELECT user_ulid, full_name FROM users WHERE email=$1", req.Email).
			Scan(&userULID, &fullName); err != nil {
			return // user not found — silent
		}

		token := secureToken(32)
		d.Redis.Set(ctx, "pwd_reset:"+token, userULID, time.Hour)

		appURL := envOrDefault("APP_URL", "http://localhost:3001")
		resetURL := appURL + "/dashboard/reset-password?token=" + token
		newMailer().send(req.Email, "Restablecer tu contraseña — CARDEX",
			passwordResetEmailHTML(fullName, resetURL))
	}()
}

// ── ResetPassword POST /api/v1/auth/reset-password ───────────────────────────
func (d *Deps) ResetPassword(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Token    string `json:"token"`
		Password string `json:"password"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid_body", err.Error())
		return
	}
	if req.Token == "" || req.Password == "" {
		writeError(w, http.StatusBadRequest, "missing_fields", "token and password are required")
		return
	}
	if len(req.Password) < 10 {
		writeError(w, http.StatusBadRequest, "weak_password", "la contraseña debe tener al menos 10 caracteres")
		return
	}

	ctx := r.Context()
	userULID, err := d.Redis.Get(ctx, "pwd_reset:"+req.Token).Result()
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid_token", "el enlace de recuperación es inválido o ha expirado")
		return
	}

	hash, err := bcrypt.GenerateFromPassword([]byte(req.Password), 12)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "hash_error", "failed to process password")
		return
	}

	if _, err := d.DB.Exec(ctx,
		"UPDATE users SET password_hash=$1, updated_at=NOW() WHERE user_ulid=$2",
		string(hash), userULID); err != nil {
		writeError(w, http.StatusInternalServerError, "db_error", err.Error())
		return
	}

	d.Redis.Del(ctx, "pwd_reset:"+req.Token)
	writeJSON(w, http.StatusOK, map[string]string{"message": "Contraseña actualizada correctamente."})
}

// ── VerifyEmail GET /api/v1/auth/verify-email?token=xxx ──────────────────────
func (d *Deps) VerifyEmail(w http.ResponseWriter, r *http.Request) {
	token := r.URL.Query().Get("token")
	if token == "" {
		writeError(w, http.StatusBadRequest, "missing_token", "token is required")
		return
	}

	ctx := r.Context()
	userULID, err := d.Redis.Get(ctx, "email_verify:"+token).Result()
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid_token", "el enlace de verificación es inválido o ha expirado")
		return
	}

	if _, err := d.DB.Exec(ctx,
		"UPDATE users SET email_verified=TRUE, email_verified_at=NOW(), updated_at=NOW() WHERE user_ulid=$1",
		userULID); err != nil {
		writeError(w, http.StatusInternalServerError, "db_error", err.Error())
		return
	}

	d.Redis.Del(ctx, "email_verify:"+token)

	appURL := envOrDefault("APP_URL", "http://localhost:3001")
	http.Redirect(w, r, appURL+"/dashboard?verified=1", http.StatusFound)
}

// ── sendVerificationEmail — called after register ─────────────────────────────
func (d *Deps) sendVerificationEmail(userULID, email, fullName string) {
	go func() {
		ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
		defer cancel()

		token := secureToken(32)
		d.Redis.Set(ctx, "email_verify:"+token, userULID, 72*time.Hour)

		appURL := envOrDefault("APP_URL", "http://localhost:3001")
		verifyURL := appURL + "/api/v1/auth/verify-email?token=" + token
		newMailer().send(email, "Verifica tu cuenta CARDEX", emailVerifyHTML(fullName, verifyURL))
	}()
}

// ── HTML email templates ───────────────────────────────────────────────────────

func passwordResetEmailHTML(name, url string) string {
	return `<!DOCTYPE html><html><head><meta charset="UTF-8"></head>
<body style="font-family:sans-serif;background:#0f0f0f;color:#e5e7eb;padding:40px">
<div style="max-width:520px;margin:0 auto;background:#1a1a1a;border-radius:12px;padding:40px;border:1px solid #2d2d2d">
  <div style="margin-bottom:32px"><span style="background:#7c3aed;color:white;padding:6px 14px;border-radius:8px;font-weight:700;font-size:14px">CARDEX</span></div>
  <h1 style="color:white;font-size:22px;margin:0 0 16px">Restablecer contraseña</h1>
  <p style="color:#9ca3af;line-height:1.6">Hola <strong style="color:white">` + name + `</strong>,<br><br>Hemos recibido una solicitud para restablecer tu contraseña. El enlace expira en <strong style="color:white">1 hora</strong>.</p>
  <div style="text-align:center;margin:32px 0">
    <a href="` + url + `" style="background:#7c3aed;color:white;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:600;display:inline-block">Restablecer contraseña →</a>
  </div>
  <p style="color:#6b7280;font-size:13px">Si no solicitaste este cambio, ignora este email.<br>Enlace directo: <a href="` + url + `" style="color:#7c3aed">` + url + `</a></p>
  <hr style="border:none;border-top:1px solid #2d2d2d;margin:24px 0">
  <p style="color:#4b5563;font-size:12px;text-align:center">© CARDEX · Pan-European Used Car Intelligence</p>
</div></body></html>`
}

func emailVerifyHTML(name, url string) string {
	return `<!DOCTYPE html><html><head><meta charset="UTF-8"></head>
<body style="font-family:sans-serif;background:#0f0f0f;color:#e5e7eb;padding:40px">
<div style="max-width:520px;margin:0 auto;background:#1a1a1a;border-radius:12px;padding:40px;border:1px solid #2d2d2d">
  <div style="margin-bottom:32px"><span style="background:#7c3aed;color:white;padding:6px 14px;border-radius:8px;font-weight:700;font-size:14px">CARDEX</span></div>
  <h1 style="color:white;font-size:22px;margin:0 0 16px">Verifica tu cuenta</h1>
  <p style="color:#9ca3af;line-height:1.6">Hola <strong style="color:white">` + name + `</strong>,<br><br>Gracias por registrarte en CARDEX. Haz clic abajo para verificar tu email.</p>
  <div style="text-align:center;margin:32px 0">
    <a href="` + url + `" style="background:#7c3aed;color:white;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:600;display:inline-block">Verificar email →</a>
  </div>
  <p style="color:#6b7280;font-size:13px">El enlace expira en 72 horas.</p>
  <hr style="border:none;border-top:1px solid #2d2d2d;margin:24px 0">
  <p style="color:#4b5563;font-size:12px;text-align:center">© CARDEX · Pan-European Used Car Intelligence</p>
</div></body></html>`
}
