package inbox

import (
	"bytes"
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	_ "modernc.org/sqlite"
)

// ── fixture helpers ────────────────────────────────────────────────────────────

func newTestDB(t *testing.T) *sql.DB {
	t.Helper()
	db, err := sql.Open("sqlite", fmt.Sprintf("file:%s?mode=memory&cache=shared", t.Name()))
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	db.SetMaxOpenConns(1)
	if err := EnsureSchema(db); err != nil {
		t.Fatalf("schema: %v", err)
	}
	if err := SeedSystemTemplates(db); err != nil {
		t.Fatalf("seed templates: %v", err)
	}
	t.Cleanup(func() { db.Close() })
	return db
}

const testTenant = "tenant-test"

func seedVehicle(t *testing.T, db *sql.DB, externalID, vin, make_, model string, year int, status string) string {
	t.Helper()
	id := newID()
	now := time.Now().UTC().Format(time.RFC3339)
	_, err := db.Exec(
		`INSERT INTO crm_vehicles(id,tenant_id,external_id,vin,make,model,year,status,created_at,updated_at)
		 VALUES(?,?,?,?,?,?,?,?,?,?)`,
		id, testTenant, externalID, vin, make_, model, year, status, now, now)
	if err != nil {
		t.Fatalf("seed vehicle: %v", err)
	}
	return id
}

func rawInquiry(platform, extID, vehicleRef, name, email, phone, body string) RawInquiry {
	return RawInquiry{
		SourcePlatform: platform,
		ExternalID:     extID,
		VehicleRef:     vehicleRef,
		SenderName:     name,
		SenderEmail:    email,
		SenderPhone:    phone,
		Subject:        "Interesse an " + vehicleRef,
		Body:           body,
		ReceivedAt:     time.Now().UTC(),
	}
}

// ── 1. Process creates contact ────────────────────────────────────────────────

func TestProcessCreatesContact(t *testing.T) {
	db := newTestDB(t)
	proc := NewProcessor(db)
	raw := rawInquiry("mobile_de", "ext-001", "BMW 320d", "Alice", "alice@example.com", "", "Interested")
	_, err := proc.Process(context.Background(), testTenant, raw)
	if err != nil {
		t.Fatalf("process: %v", err)
	}
	var count int
	db.QueryRow(`SELECT COUNT(*) FROM crm_contacts WHERE tenant_id=? AND email=?`, testTenant, "alice@example.com").Scan(&count)
	if count != 1 {
		t.Fatalf("expected 1 contact, got %d", count)
	}
}

// ── 2. Process creates deal ───────────────────────────────────────────────────

func TestProcessCreatesDeal(t *testing.T) {
	db := newTestDB(t)
	proc := NewProcessor(db)
	raw := rawInquiry("mobile_de", "ext-002", "BMW 320d", "Bob", "bob@example.com", "", "Interested")
	if _, err := proc.Process(context.Background(), testTenant, raw); err != nil {
		t.Fatalf("process: %v", err)
	}
	var stage string
	db.QueryRow(`SELECT stage FROM crm_deals WHERE tenant_id=?`, testTenant).Scan(&stage)
	if stage != "lead" {
		t.Fatalf("expected stage=lead, got %q", stage)
	}
}

// ── 3. Process creates conversation ──────────────────────────────────────────

func TestProcessCreatesConversation(t *testing.T) {
	db := newTestDB(t)
	proc := NewProcessor(db)
	raw := rawInquiry("autoscout24", "as-001", "Audi A4", "Carol", "carol@example.com", "", "Hi")
	conv, err := proc.Process(context.Background(), testTenant, raw)
	if err != nil {
		t.Fatalf("process: %v", err)
	}
	if conv.ID == "" {
		t.Fatal("expected conversation ID")
	}
	if conv.SourcePlatform != "autoscout24" {
		t.Fatalf("expected autoscout24, got %q", conv.SourcePlatform)
	}
	if conv.Status != "open" {
		t.Fatalf("expected open, got %q", conv.Status)
	}
}

// ── 4. Process creates activity ───────────────────────────────────────────────

func TestProcessCreatesActivity(t *testing.T) {
	db := newTestDB(t)
	proc := NewProcessor(db)
	raw := rawInquiry("web", "w-001", "VW Golf", "Dave", "dave@example.com", "", "Is it available?")
	if _, err := proc.Process(context.Background(), testTenant, raw); err != nil {
		t.Fatalf("process: %v", err)
	}
	var actType string
	db.QueryRow(`SELECT type FROM crm_activities WHERE tenant_id=?`, testTenant).Scan(&actType)
	if actType != "inquiry" {
		t.Fatalf("expected inquiry activity, got %q", actType)
	}
}

// ── 5. Process creates inbound message ───────────────────────────────────────

func TestProcessCreatesInboundMessage(t *testing.T) {
	db := newTestDB(t)
	proc := NewProcessor(db)
	raw := rawInquiry("email", "em-001", "Mercedes C200", "Eve", "eve@example.com", "", "Test body")
	conv, err := proc.Process(context.Background(), testTenant, raw)
	if err != nil {
		t.Fatalf("process: %v", err)
	}
	var dir, body string
	db.QueryRow(`SELECT direction, body FROM crm_messages WHERE conversation_id=?`, conv.ID).Scan(&dir, &body)
	if dir != "inbound" {
		t.Fatalf("expected inbound, got %q", dir)
	}
	if body != "Test body" {
		t.Fatalf("unexpected body: %q", body)
	}
}

// ── 6. Dedup: same external_id + platform → one conversation ─────────────────

func TestDedupSameInquiry(t *testing.T) {
	db := newTestDB(t)
	proc := NewProcessor(db)
	raw := rawInquiry("mobile_de", "dup-001", "BMW 530d", "Frank", "frank@example.com", "", "First")
	if _, err := proc.Process(context.Background(), testTenant, raw); err != nil {
		t.Fatalf("first process: %v", err)
	}
	raw.Body = "Second (dup)"
	if _, err := proc.Process(context.Background(), testTenant, raw); err != nil {
		t.Fatalf("second process: %v", err)
	}
	var convCount int
	db.QueryRow(`SELECT COUNT(*) FROM crm_conversations WHERE tenant_id=?`, testTenant).Scan(&convCount)
	if convCount != 1 {
		t.Fatalf("expected 1 conversation (dedup), got %d", convCount)
	}
	var msgCount int
	db.QueryRow(`SELECT COUNT(*) FROM crm_messages WHERE conversation_id IN (SELECT id FROM crm_conversations WHERE tenant_id=?)`, testTenant).Scan(&msgCount)
	if msgCount != 2 {
		t.Fatalf("expected 2 messages after dup, got %d", msgCount)
	}
}

// ── 7. Multi-platform same contact → 2 conversations ─────────────────────────

func TestMultiPlatformSameVehicle(t *testing.T) {
	db := newTestDB(t)
	proc := NewProcessor(db)
	raw1 := rawInquiry("mobile_de", "mp-001", "VW Tiguan", "Grace", "grace@example.com", "", "platform 1")
	raw2 := rawInquiry("autoscout24", "mp-002", "VW Tiguan", "Grace", "grace@example.com", "", "platform 2")
	if _, err := proc.Process(context.Background(), testTenant, raw1); err != nil {
		t.Fatalf("p1: %v", err)
	}
	if _, err := proc.Process(context.Background(), testTenant, raw2); err != nil {
		t.Fatalf("p2: %v", err)
	}
	var count int
	db.QueryRow(`SELECT COUNT(*) FROM crm_conversations WHERE tenant_id=?`, testTenant).Scan(&count)
	if count != 2 {
		t.Fatalf("expected 2 conversations (different platforms), got %d", count)
	}
}

// ── 8. Contact match by email ─────────────────────────────────────────────────

func TestContactMatchByEmail(t *testing.T) {
	db := newTestDB(t)
	proc := NewProcessor(db)
	r1 := rawInquiry("mobile_de", "e1-001", "Ford Focus", "Henry", "henry@example.com", "", "q1")
	r2 := rawInquiry("autoscout24", "e1-002", "Ford Focus", "Henry H.", "henry@example.com", "", "q2")
	if _, err := proc.Process(context.Background(), testTenant, r1); err != nil {
		t.Fatal(err)
	}
	if _, err := proc.Process(context.Background(), testTenant, r2); err != nil {
		t.Fatal(err)
	}
	var count int
	db.QueryRow(`SELECT COUNT(*) FROM crm_contacts WHERE tenant_id=? AND email=?`, testTenant, "henry@example.com").Scan(&count)
	if count != 1 {
		t.Fatalf("expected 1 contact (email dedup), got %d", count)
	}
}

// ── 9. Contact match by phone ─────────────────────────────────────────────────

func TestContactMatchByPhone(t *testing.T) {
	db := newTestDB(t)
	proc := NewProcessor(db)
	r1 := rawInquiry("mobile_de", "ph-001", "Seat Leon", "Iris", "", "+34600000001", "call 1")
	r2 := rawInquiry("web", "ph-002", "Seat Leon", "Iris I.", "", "+34600000001", "call 2")
	if _, err := proc.Process(context.Background(), testTenant, r1); err != nil {
		t.Fatal(err)
	}
	if _, err := proc.Process(context.Background(), testTenant, r2); err != nil {
		t.Fatal(err)
	}
	var count int
	db.QueryRow(`SELECT COUNT(*) FROM crm_contacts WHERE tenant_id=? AND phone=?`, testTenant, "+34600000001").Scan(&count)
	if count != 1 {
		t.Fatalf("expected 1 contact (phone dedup), got %d", count)
	}
}

// ── 10. Vehicle transition listed → inquiry ────────────────────────────────────

func TestVehicleTransitionsToInquiry(t *testing.T) {
	db := newTestDB(t)
	vID := seedVehicle(t, db, "ext-bmw-1", "WBA1234", "BMW", "320d", 2021, "listed")
	proc := NewProcessor(db)
	raw := rawInquiry("mobile_de", "tr-001", "ext-bmw-1", "Jack", "jack@example.com", "", "test")
	if _, err := proc.Process(context.Background(), testTenant, raw); err != nil {
		t.Fatalf("process: %v", err)
	}
	var status string
	db.QueryRow(`SELECT status FROM crm_vehicles WHERE id=?`, vID).Scan(&status)
	if status != "inquiry" {
		t.Fatalf("expected inquiry status, got %q", status)
	}
}

// ── 11. Reply creates outbound message ────────────────────────────────────────

func TestReplyCreatesOutboundMessage(t *testing.T) {
	db := newTestDB(t)
	proc := NewProcessor(db)
	raw := rawInquiry("mobile_de", "rep-001", "BMW 520d", "Karl", "karl@example.com", "", "Is it available?")
	conv, err := proc.Process(context.Background(), testTenant, raw)
	if err != nil {
		t.Fatalf("process: %v", err)
	}

	convs := NewConversationStore(db)
	tmps := NewTemplateStore(db)
	engine := NewReplyEngine(db, convs, tmps, SMTPConfig{}) // no SMTP — manual only
	_, err = engine.Reply(context.Background(), testTenant, conv.ID, ReplyRequest{
		Body:    "Yes, it is available!",
		SendVia: "manual",
	})
	if err != nil {
		t.Fatalf("reply: %v", err)
	}

	var dir string
	db.QueryRow(`SELECT direction FROM crm_messages WHERE conversation_id=? AND direction='outbound'`, conv.ID).Scan(&dir)
	if dir != "outbound" {
		t.Fatal("outbound message not found")
	}
}

// ── 12. Reply marks conversation replied ──────────────────────────────────────

func TestReplyUpdatesConversationStatus(t *testing.T) {
	db := newTestDB(t)
	proc := NewProcessor(db)
	raw := rawInquiry("mobile_de", "rep-002", "BMW 520d", "Lena", "lena@example.com", "", "Hello")
	conv, _ := proc.Process(context.Background(), testTenant, raw)

	convs := NewConversationStore(db)
	tmps := NewTemplateStore(db)
	engine := NewReplyEngine(db, convs, tmps, SMTPConfig{})
	engine.Reply(context.Background(), testTenant, conv.ID, ReplyRequest{Body: "Hi!", SendVia: "manual"}) //nolint

	var status string
	db.QueryRow(`SELECT status FROM crm_conversations WHERE id=?`, conv.ID).Scan(&status)
	if status != "replied" {
		t.Fatalf("expected replied, got %q", status)
	}
}

// ── 13. Template render replaces placeholders ─────────────────────────────────

func TestTemplateRender(t *testing.T) {
	tmpl := &Template{
		Subject: "Interesse am {{make}} {{model}}",
		Body:    "Sehr geehrte/r {{name}}, das {{make}} {{model}} {{year}} kostet {{price}}.",
	}
	subj, body := Render(tmpl, map[string]string{
		"make": "BMW", "model": "320d", "year": "2021", "name": "Müller", "price": "€25.000",
	})
	if !strings.Contains(subj, "BMW 320d") {
		t.Fatalf("subject: %q", subj)
	}
	if !strings.Contains(body, "Müller") || !strings.Contains(body, "€25.000") {
		t.Fatalf("body: %q", body)
	}
}

// ── 14. Template render leaves unknown placeholders untouched ─────────────────

func TestTemplateRenderMissingVar(t *testing.T) {
	tmpl := &Template{Subject: "Hello", Body: "Hi {{name}}, ref {{unknown}}"}
	_, body := Render(tmpl, map[string]string{"name": "World"})
	if !strings.Contains(body, "{{unknown}}") {
		t.Fatalf("expected {{unknown}} to remain, got: %q", body)
	}
}

// ── 15. List inbox filters by status ─────────────────────────────────────────

func TestListInboxFiltersStatus(t *testing.T) {
	db := newTestDB(t)
	proc := NewProcessor(db)
	for i, status := range []string{"open", "open", "replied"} {
		r := rawInquiry("web", fmt.Sprintf("ls-%d", i), "Renault Clio", fmt.Sprintf("u%d@x.com", i), fmt.Sprintf("u%d@x.com", i), "", "test")
		conv, _ := proc.Process(context.Background(), testTenant, r)
		if status != "open" {
			db.Exec(`UPDATE crm_conversations SET status=? WHERE id=?`, status, conv.ID)
		}
	}
	store := NewConversationStore(db)
	open, _ := store.List(testTenant, ListInboxQuery{Status: "open"})
	replied, _ := store.List(testTenant, ListInboxQuery{Status: "replied"})
	if len(open) != 2 {
		t.Fatalf("expected 2 open, got %d", len(open))
	}
	if len(replied) != 1 {
		t.Fatalf("expected 1 replied, got %d", len(replied))
	}
}

// ── 16. Spam not in default inbox list ───────────────────────────────────────

func TestSpamNotInDefaultList(t *testing.T) {
	db := newTestDB(t)
	proc := NewProcessor(db)
	raw := rawInquiry("web", "spam-001", "Skoda Octavia", "Spammer", "spam@spam.com", "", "BUY NOW")
	conv, _ := proc.Process(context.Background(), testTenant, raw)
	db.Exec(`UPDATE crm_conversations SET status='spam' WHERE id=?`, conv.ID)

	store := NewConversationStore(db)
	all, _ := store.List(testTenant, ListInboxQuery{}) // default excludes spam
	for _, c := range all {
		if c.Status == "spam" {
			t.Fatal("spam conversation appeared in default list")
		}
	}
}

// ── 17. Patch mark read ────────────────────────────────────────────────────────

func TestPatchMarkRead(t *testing.T) {
	db := newTestDB(t)
	proc := NewProcessor(db)
	conv, _ := proc.Process(context.Background(), testTenant, rawInquiry("web", "rd-001", "Peugeot 208", "Mary", "mary@x.com", "", "hi"))

	store := NewConversationStore(db)
	f := false
	store.Patch(testTenant, conv.ID, PatchConversationRequest{Unread: &f}) //nolint

	var unread int
	db.QueryRow(`SELECT unread FROM crm_conversations WHERE id=?`, conv.ID).Scan(&unread)
	if unread != 0 {
		t.Fatalf("expected unread=0, got %d", unread)
	}
}

// ── 18. Patch mark spam ────────────────────────────────────────────────────────

func TestPatchMarkSpam(t *testing.T) {
	db := newTestDB(t)
	proc := NewProcessor(db)
	conv, _ := proc.Process(context.Background(), testTenant, rawInquiry("email", "sp-001", "Fiat 500", "Nick", "nick@x.com", "", "junk"))

	store := NewConversationStore(db)
	sp := "spam"
	store.Patch(testTenant, conv.ID, PatchConversationRequest{Status: &sp}) //nolint

	var status string
	db.QueryRow(`SELECT status FROM crm_conversations WHERE id=?`, conv.ID).Scan(&status)
	if status != "spam" {
		t.Fatalf("expected spam, got %q", status)
	}
}

// ── 19. Patch mark closed ─────────────────────────────────────────────────────

func TestPatchMarkClosed(t *testing.T) {
	db := newTestDB(t)
	proc := NewProcessor(db)
	conv, _ := proc.Process(context.Background(), testTenant, rawInquiry("manual", "cl-001", "Opel Corsa", "Olivia", "olivia@x.com", "", "hi"))

	store := NewConversationStore(db)
	cl := "closed"
	store.Patch(testTenant, conv.ID, PatchConversationRequest{Status: &cl}) //nolint

	var status string
	db.QueryRow(`SELECT status FROM crm_conversations WHERE id=?`, conv.ID).Scan(&status)
	if status != "closed" {
		t.Fatalf("expected closed, got %q", status)
	}
}

// ── 20. Auto-reminder: 4-day-old conversation → reminder created ──────────────

func TestAutoReminderCreatesActivity(t *testing.T) {
	db := newTestDB(t)
	proc := NewProcessor(db)
	conv, _ := proc.Process(context.Background(), testTenant, rawInquiry("mobile_de", "ar-001", "BMW 320d", "Pete", "pete@x.com", "", "hi"))

	// Back-date last_message_at to 4 days ago.
	old := time.Now().UTC().Add(-96 * time.Hour).Format(time.RFC3339)
	db.Exec(`UPDATE crm_conversations SET last_message_at=? WHERE id=?`, old, conv.ID)

	job := NewReminderJob(db, 72*time.Hour)
	n, err := job.Run(context.Background())
	if err != nil {
		t.Fatalf("run: %v", err)
	}
	if n == 0 {
		t.Fatal("expected at least 1 reminder")
	}

	var actType string
	db.QueryRow(`SELECT type FROM crm_activities WHERE deal_id=? AND type='reminder'`, conv.DealID).Scan(&actType)
	if actType != "reminder" {
		t.Fatal("reminder activity not found")
	}
}

// ── 21. Auto-reminder skips replied conversations ─────────────────────────────

func TestAutoReminderSkipsReplied(t *testing.T) {
	db := newTestDB(t)
	proc := NewProcessor(db)
	conv, _ := proc.Process(context.Background(), testTenant, rawInquiry("web", "nr-001", "Kia Sportage", "Quinn", "quinn@x.com", "", "hi"))

	old := time.Now().UTC().Add(-96 * time.Hour).Format(time.RFC3339)
	db.Exec(`UPDATE crm_conversations SET last_message_at=?, status='replied' WHERE id=?`, old, conv.ID)

	job := NewReminderJob(db, 72*time.Hour)
	n, _ := job.Run(context.Background())
	if n != 0 {
		t.Fatalf("expected 0 reminders for replied conversation, got %d", n)
	}
}

// ── 22. Auto-reminder skips recent conversations ──────────────────────────────

func TestAutoReminderSkipsRecent(t *testing.T) {
	db := newTestDB(t)
	proc := NewProcessor(db)
	proc.Process(context.Background(), testTenant, rawInquiry("web", "rc-001", "Volvo XC60", "Rita", "rita@x.com", "", "hi")) //nolint

	job := NewReminderJob(db, 72*time.Hour)
	n, _ := job.Run(context.Background())
	if n != 0 {
		t.Fatalf("expected 0 reminders for recent conversation, got %d", n)
	}
}

// ── 23. List inbox filters unread ─────────────────────────────────────────────

func TestListInboxFiltersUnread(t *testing.T) {
	db := newTestDB(t)
	proc := NewProcessor(db)
	c1, _ := proc.Process(context.Background(), testTenant, rawInquiry("web", "ur-001", "Honda Civic", "Sam", "sam@x.com", "", "hi"))
	proc.Process(context.Background(), testTenant, rawInquiry("web", "ur-002", "Honda Jazz", "Tom", "tom@x.com", "", "hi")) //nolint
	// Mark c1 as read.
	db.Exec(`UPDATE crm_conversations SET unread=0 WHERE id=?`, c1.ID)

	store := NewConversationStore(db)
	t2 := true
	unread, _ := store.List(testTenant, ListInboxQuery{Unread: &t2})
	if len(unread) != 1 {
		t.Fatalf("expected 1 unread, got %d", len(unread))
	}
}

// ── 24. System templates seeded (25 rows) ─────────────────────────────────────

func TestSystemTemplatesSeeded(t *testing.T) {
	db := newTestDB(t)
	var count int
	db.QueryRow(`SELECT COUNT(*) FROM crm_templates WHERE tenant_id=?`, systemTenant).Scan(&count)
	if count != 25 {
		t.Fatalf("expected 25 system templates, got %d", count)
	}
}

// ── 25. Template list includes system templates ───────────────────────────────

func TestTemplateListIncludesSystem(t *testing.T) {
	db := newTestDB(t)
	ts := NewTemplateStore(db)
	templates, err := ts.List(context.Background(), testTenant, "EN")
	if err != nil {
		t.Fatalf("list: %v", err)
	}
	if len(templates) == 0 {
		t.Fatal("expected templates, got none")
	}
	var hasSystem bool
	for _, tmpl := range templates {
		if tmpl.IsSystem {
			hasSystem = true
		}
	}
	if !hasSystem {
		t.Fatal("expected system templates in list")
	}
}

// ── 26. HTTP GET /api/v1/inbox returns JSON ───────────────────────────────────

func TestHTTPListInbox(t *testing.T) {
	db := newTestDB(t)
	proc := NewProcessor(db)
	proc.Process(context.Background(), testTenant, rawInquiry("web", "http-001", "Tesla Model 3", "Uma", "uma@x.com", "", "hi")) //nolint

	srv := NewServer(db, SMTPConfig{}, nil)
	w := httptest.NewRecorder()
	r := httptest.NewRequest("GET", "/api/v1/inbox", nil)
	r.Header.Set("X-Tenant-ID", testTenant)
	srv.Handler().ServeHTTP(w, r)

	if w.Code != http.StatusOK {
		t.Fatalf("status %d", w.Code)
	}
	var convs []Conversation
	if err := json.NewDecoder(w.Body).Decode(&convs); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if len(convs) != 1 {
		t.Fatalf("expected 1, got %d", len(convs))
	}
}

// ── 27. HTTP GET /api/v1/inbox/:id returns with messages ─────────────────────

func TestHTTPGetConversation(t *testing.T) {
	db := newTestDB(t)
	proc := NewProcessor(db)
	conv, _ := proc.Process(context.Background(), testTenant, rawInquiry("web", "http-002", "Tesla Model S", "Vera", "vera@x.com", "", "interested"))

	srv := NewServer(db, SMTPConfig{}, nil)
	w := httptest.NewRecorder()
	r := httptest.NewRequest("GET", "/api/v1/inbox/"+conv.ID, nil)
	r.Header.Set("X-Tenant-ID", testTenant)
	srv.Handler().ServeHTTP(w, r)

	if w.Code != http.StatusOK {
		t.Fatalf("status %d: %s", w.Code, w.Body.String())
	}
	var resp ConversationWithMessages
	if err := json.NewDecoder(w.Body).Decode(&resp); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if resp.Conversation.ID != conv.ID {
		t.Fatalf("wrong conv ID")
	}
	if len(resp.Messages) != 1 {
		t.Fatalf("expected 1 message, got %d", len(resp.Messages))
	}
}

// ── 28. HTTP POST reply creates outbound message ──────────────────────────────

func TestHTTPReply(t *testing.T) {
	db := newTestDB(t)
	proc := NewProcessor(db)
	conv, _ := proc.Process(context.Background(), testTenant, rawInquiry("web", "http-003", "Porsche Cayenne", "Will", "will@x.com", "", "price?"))

	body, _ := json.Marshal(ReplyRequest{Body: "The price is €80.000.", SendVia: "manual"})
	srv := NewServer(db, SMTPConfig{}, nil)
	w := httptest.NewRecorder()
	r := httptest.NewRequest("POST", "/api/v1/inbox/"+conv.ID+"/reply", bytes.NewReader(body))
	r.Header.Set("X-Tenant-ID", testTenant)
	r.Header.Set("Content-Type", "application/json")
	srv.Handler().ServeHTTP(w, r)

	if w.Code != http.StatusCreated {
		t.Fatalf("status %d: %s", w.Code, w.Body.String())
	}
	var count int
	db.QueryRow(`SELECT COUNT(*) FROM crm_messages WHERE conversation_id=? AND direction='outbound'`, conv.ID).Scan(&count)
	if count != 1 {
		t.Fatalf("expected 1 outbound message, got %d", count)
	}
}

// ── 29. HTTP GET /api/v1/templates returns templates ─────────────────────────

func TestHTTPTemplates(t *testing.T) {
	db := newTestDB(t)
	srv := NewServer(db, SMTPConfig{}, nil)
	w := httptest.NewRecorder()
	r := httptest.NewRequest("GET", "/api/v1/templates?lang=DE", nil)
	r.Header.Set("X-Tenant-ID", testTenant)
	srv.Handler().ServeHTTP(w, r)

	if w.Code != http.StatusOK {
		t.Fatalf("status %d", w.Code)
	}
	var templates []Template
	json.NewDecoder(w.Body).Decode(&templates) //nolint
	if len(templates) == 0 {
		t.Fatal("expected templates")
	}
}

// ── 30. Vehicle lookup by VIN ─────────────────────────────────────────────────

func TestProcessMatchesVehicleByVIN(t *testing.T) {
	db := newTestDB(t)
	vID := seedVehicle(t, db, "", "WBA99990001234567", "BMW", "M3", 2022, "listed")
	proc := NewProcessor(db)
	conv, err := proc.Process(context.Background(), testTenant, rawInquiry("mobile_de", "vin-001", "WBA99990001234567", "Xena", "xena@x.com", "", "love it"))
	if err != nil {
		t.Fatalf("process: %v", err)
	}
	if conv.VehicleID != vID {
		t.Fatalf("expected vehicle %s, got %q", vID, conv.VehicleID)
	}
}

// ── helper for server tests ───────────────────────────────────────────────────

func TestHTTPPatchConversation(t *testing.T) {
	db := newTestDB(t)
	proc := NewProcessor(db)
	conv, _ := proc.Process(context.Background(), testTenant, rawInquiry("web", "pa-001", "Aston Martin DB11", "Zoe", "zoe@x.com", "", "wow"))

	closed := "closed"
	body, _ := json.Marshal(PatchConversationRequest{Status: &closed})
	srv := NewServer(db, SMTPConfig{}, nil)
	w := httptest.NewRecorder()
	r := httptest.NewRequest("PATCH", "/api/v1/inbox/"+conv.ID, bytes.NewReader(body))
	r.Header.Set("X-Tenant-ID", testTenant)
	r.Header.Set("Content-Type", "application/json")
	srv.Handler().ServeHTTP(w, r)

	if w.Code != http.StatusNoContent {
		t.Fatalf("status %d: %s", w.Code, w.Body.String())
	}
	var status string
	db.QueryRow(`SELECT status FROM crm_conversations WHERE id=?`, conv.ID).Scan(&status)
	if status != "closed" {
		t.Fatalf("expected closed, got %q", status)
	}
}
