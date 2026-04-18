# CARDEX Workspace — Sprint 44: Contact Management + Unified Inbox

## Executive Summary

Dealers today juggle 5+ portals (mobile.de, AutoScout24, email, web forms, phone calls). Every inquiry lands in a different UI. Response times suffer; leads fall through the cracks. The Unified Inbox collapses all inbound channels into a single conversation view — one list, one thread model, one reply engine.

**Target impact:** ≥30% reduction in average response time; zero missed inquiries from fragmented portals.

---

## Architecture

```
Platform Adapters          Ingestion Engine         CRM Records
──────────────────         ────────────────         ──────────────────────
MobileDeSource    ─┐                                crm_contacts
AutoScout24Source ─┤→  IngestionEngine ─→ Processor → crm_vehicles
EmailSource       ─┤   (polls every N min)          crm_deals
WebhookSource     ─┤                                crm_activities
ManualSource      ─┘                                │
                                                    ▼
                                            crm_conversations
                                            crm_messages
                                            crm_templates
                                                    │
                                                    ▼
                                            HTTP API (:8505)
                                            ReplyEngine → SMTP
                                            ReminderJob (cron)
```

---

## Package: `workspace/internal/inbox/`

### Files

| File | Responsibility |
|------|---------------|
| `schema.go` | SQLite schema for all CRM + inbox tables; `EnsureSchema`, `SeedSystemTemplates` |
| `types.go` | All Go types: `RawInquiry`, `InquirySource`, `Conversation`, `Message`, `Template`, `Contact`, `Vehicle`, `Deal`, `Activity` |
| `sources.go` | `WebhookSource` (mutex queue + HTTP handler), `ManualSource` (no-op, HTTP-only) |
| `ingestion.go` | `IngestionEngine`: polls all sources at interval, feeds `Processor` |
| `processor.go` | `Processor.Process()`: atomically creates/finds contact+vehicle+conversation+deal+activity+message |
| `conversation.go` | `ConversationStore`: List (paginated + filtered), Get (with messages), Patch, AddMessage |
| `templates.go` | `TemplateStore`: List, GetByID, Create, Update; `Render()` placeholder substitution |
| `reply.go` | `ReplyEngine`: outbound message creation, SMTP send, activity creation |
| `reminders.go` | `ReminderJob`: daily scan for overdue open conversations → reminder activities |
| `metrics.go` | Prometheus metrics (counters, histogram, gauge) |
| `server.go` | HTTP API server with all 9 endpoints |
| `email_inbox.go` | Generic IMAP polling scaffold (`EmailSource`) |
| `mobile_de_inbox.go` | mobile.de email-forwarding adapter |
| `autoscout24_inbox.go` | AutoScout24 email-forwarding adapter |

---

## Data Model

### crm_contacts
```sql
id TEXT PK | tenant_id | name | email | phone | created_at | updated_at
```
Dedup: match by `email` OR `phone`. Same person across platforms → single contact row.

### crm_vehicles
```sql
id TEXT PK | tenant_id | external_id | vin | make | model | year
         | status (listed|inquiry|sold|withdrawn) | created_at | updated_at
```
Status lifecycle: `listed` → `inquiry` (first inquiry) → `sold`/`withdrawn`.

### crm_deals
```sql
id TEXT PK | tenant_id | contact_id | vehicle_id | stage (lead|contacted|offer|negotiation|won|lost)
```
Created automatically in `lead` stage on first inquiry. Re-used if existing open deal found for same contact+vehicle.

### crm_conversations
```sql
id TEXT PK | tenant_id | contact_id | vehicle_id | deal_id
         | source_platform | external_id (dedup) | subject
         | status (open|replied|closed|spam) | unread | last_message_at
```
Dedup: `UNIQUE(tenant_id, source_platform, external_id)`. Same inquiry twice = one conversation, two messages.

### crm_messages
```sql
id TEXT PK | conversation_id | direction (inbound|outbound)
         | sender_name | sender_email | body | template_id | sent_via | sent_at | read_at
```

### crm_templates
```sql
id TEXT PK | tenant_id | name | language | subject | body | is_system
```
25 built-in system templates: 5 types × 5 languages (DE/FR/ES/NL/EN).

---

## Processor Flow (atomic transaction)

```
RawInquiry
    │
    ▼
findOrCreateContact(email OR phone)
    │
    ▼
findVehicle(external_id → VIN → fuzzy make+model)
    │
    ▼
findOrCreateConversation  ←─── dedup: source_platform + external_id
    │                                 if exists: add message, update last_message_at, RETURN
    ▼
findOrCreateDeal(contact + vehicle, stage=lead)
    │
    ├── UPDATE crm_conversations SET deal_id=?
    ├── INSERT crm_activities (type=inquiry)
    ├── INSERT crm_messages (direction=inbound)
    └── if vehicle.status=listed → UPDATE crm_vehicles SET status=inquiry
```

---

## Platform Adapters

### Email Forwarding (mobile.de, AutoScout24)
Both platforms forward inquiry notification emails to the dealer's registered address. The `EmailSource` scaffolding polls via IMAP (`EmailConfig{Host, Port, User, Pass, Mailbox}`). Platform-specific wrappers (`MobileDeSource`, `AutoScout24Source`) add email pattern matching and metadata extraction.

**Production step:** configure IMAP credentials in environment; implement full IMAP client using `github.com/emersion/go-imap`.

### Web Form (`WebhookSource`)
Dealer's website POSTs JSON to `POST /api/v1/ingest/web`. Source buffers in a mutex-protected queue; `IngestionEngine.PollOnce` drains it.

### Manual (`ManualSource`)
Dealer POSTs to `POST /api/v1/ingest/manual` (via the Server directly). Use case: logging a phone call or walk-in visit.

---

## Response Templates

5 template types × 5 languages = **25 system templates** seeded at startup.

| Template Name | Use Case |
|---------------|----------|
| `inquiry_ack` | Auto-acknowledge new inquiry |
| `price_offer` | Confirm a price offer |
| `follow_up` | Follow up on unanswered offer |
| `visit_invite` | Invite buyer to showroom |
| `rejection` | Notify vehicle was sold |

### Placeholder Syntax
`{{make}}`, `{{model}}`, `{{year}}`, `{{name}}`, `{{price}}`, `{{days}}`

### Render
```go
subject, body := inbox.Render(template, map[string]string{
    "make": "BMW", "model": "320d", "year": "2021", "name": "Müller",
})
```
Unknown placeholders are left intact.

---

## API Reference

### Conversations

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/inbox` | List conversations (default: non-spam, ordered by last_message_at DESC) |
| `GET` | `/api/v1/inbox/{id}` | Conversation + all messages |
| `POST` | `/api/v1/inbox/{id}/reply` | Send outbound message |
| `PATCH` | `/api/v1/inbox/{id}` | Update status / unread flag |

**List query params:** `status`, `platform`, `unread=true/false`, `vehicle_id`

**Reply body:**
```json
{ "body": "...", "template_id": "optional", "send_via": "email|manual" }
```

**Patch body:**
```json
{ "status": "closed|spam|open|replied", "unread": false }
```

### Templates

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/templates` | List templates (`?lang=DE/FR/ES/NL/EN`) |
| `POST` | `/api/v1/templates` | Create custom template |
| `PUT` | `/api/v1/templates/{id}` | Update custom template (system templates protected) |

### Ingestion

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/ingest/web` | Web form submission |
| `POST` | `/api/v1/ingest/manual` | Manual dealer entry (call/visit log) |

**Tenant identification:** `X-Tenant-ID` request header (fallback: `"default"`).

---

## Auto-Reminders

`ReminderJob` runs daily (configurable interval) and:

1. Queries all `status='open'` conversations where `last_message_at < NOW - 3 days`
2. Filters out conversations that already have a recent `type='reminder'` activity
3. Inserts `crm_activities(type='reminder', body='Sin respuesta hace N días — seguimiento recomendado')`
4. Updates `workspace_inbox_overdue_total` gauge

```go
job := inbox.NewReminderJob(db, 72*time.Hour)
n, err := job.Run(ctx) // returns count of reminders created
```

---

## Prometheus Metrics

| Metric | Type | Labels |
|--------|------|--------|
| `workspace_inbox_conversations_total` | Counter | `status`, `platform` |
| `workspace_inbox_messages_total` | Counter | `direction` |
| `workspace_inbox_response_time_seconds` | Histogram | — |
| `workspace_inbox_overdue_total` | Gauge | — |

---

## Test Coverage (31 tests)

| Test | Scenario |
|------|----------|
| `TestProcessCreatesContact` | RawInquiry → contact row created |
| `TestProcessCreatesDeal` | RawInquiry → deal with stage=lead |
| `TestProcessCreatesConversation` | RawInquiry → conversation open |
| `TestProcessCreatesActivity` | RawInquiry → activity type=inquiry |
| `TestProcessCreatesInboundMessage` | RawInquiry → message direction=inbound |
| `TestDedupSameInquiry` | Same external_id+platform → 1 conv, 2 messages |
| `TestMultiPlatformSameVehicle` | Different platforms → 2 separate conversations |
| `TestContactMatchByEmail` | Same email → 1 contact |
| `TestContactMatchByPhone` | Same phone → 1 contact |
| `TestVehicleTransitionsToInquiry` | listed vehicle → status=inquiry |
| `TestReplyCreatesOutboundMessage` | Reply → outbound message |
| `TestReplyUpdatesConversationStatus` | Reply → status=replied |
| `TestTemplateRender` | All placeholders substituted |
| `TestTemplateRenderMissingVar` | Unknown placeholder kept as-is |
| `TestListInboxFiltersStatus` | Status filter works |
| `TestSpamNotInDefaultList` | Spam excluded from default list |
| `TestPatchMarkRead` | PATCH unread=false |
| `TestPatchMarkSpam` | PATCH status=spam |
| `TestPatchMarkClosed` | PATCH status=closed |
| `TestAutoReminderCreatesActivity` | 4-day-old conv → reminder |
| `TestAutoReminderSkipsReplied` | Replied conv → no reminder |
| `TestAutoReminderSkipsRecent` | Recent conv → no reminder |
| `TestListInboxFiltersUnread` | Unread filter works |
| `TestSystemTemplatesSeeded` | 25 system templates on startup |
| `TestTemplateListIncludesSystem` | System templates in list |
| `TestHTTPListInbox` | GET /api/v1/inbox → 200 JSON |
| `TestHTTPGetConversation` | GET /api/v1/inbox/:id → conv + messages |
| `TestHTTPReply` | POST reply → 201 + outbound message |
| `TestHTTPTemplates` | GET /api/v1/templates → 200 |
| `TestProcessMatchesVehicleByVIN` | Vehicle lookup by VIN |
| `TestHTTPPatchConversation` | PATCH → 204 + status updated |

---

## Deployment

```bash
# Environment
INBOX_DB_PATH=/data/workspace.db
INBOX_PORT=8505
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=dealer@example.com
SMTP_PASS=secret
SMTP_FROM="CARDEX Dealer <dealer@example.com>"
X_TENANT_ID=tenant-001  # per-request header
```

```bash
# Makefile
make inbox-build   # go build ./workspace/...
make inbox-test    # go test -race ./workspace/...
make inbox-serve   # go run ./workspace/cmd/inbox-server
```

---

## Roadmap

| Priority | Item |
|----------|------|
| P0 | IMAP client implementation (go-imap) for email adapters |
| P0 | Per-tenant SMTP credentials (vault or DB) |
| P1 | mobile.de official Lead API (OAuth2) |
| P1 | AutoScout24 Lead Notification API |
| P2 | Conversation assignment to dealer staff members |
| P2 | Auto-reply on first inquiry (configurable per tenant) |
| P3 | Conversation merge (same customer, different platforms) |
| P3 | Analytics dashboard: response time percentiles by platform |
