package inbox

import (
	"database/sql"
	"time"
)

const inboxSchema = `
CREATE TABLE IF NOT EXISTS crm_contacts (
    id         TEXT PRIMARY KEY,
    tenant_id  TEXT NOT NULL,
    name       TEXT NOT NULL DEFAULT '',
    email      TEXT NOT NULL DEFAULT '',
    phone      TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_contacts_tenant_email ON crm_contacts(tenant_id, email)
    WHERE email != '';
CREATE INDEX IF NOT EXISTS idx_contacts_tenant_phone ON crm_contacts(tenant_id, phone)
    WHERE phone != '';

CREATE TABLE IF NOT EXISTS crm_vehicles (
    id          TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL,
    external_id TEXT,
    vin         TEXT,
    make        TEXT NOT NULL DEFAULT '',
    model       TEXT NOT NULL DEFAULT '',
    year        INTEGER NOT NULL DEFAULT 0,
    status      TEXT NOT NULL DEFAULT 'listed',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_vehicles_tenant      ON crm_vehicles(tenant_id);
CREATE INDEX IF NOT EXISTS idx_vehicles_external_id ON crm_vehicles(tenant_id, external_id)
    WHERE external_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_vehicles_vin         ON crm_vehicles(tenant_id, vin)
    WHERE vin IS NOT NULL;

CREATE TABLE IF NOT EXISTS crm_deals (
    id         TEXT PRIMARY KEY,
    tenant_id  TEXT NOT NULL,
    contact_id TEXT NOT NULL REFERENCES crm_contacts(id),
    vehicle_id TEXT REFERENCES crm_vehicles(id),
    stage      TEXT NOT NULL DEFAULT 'lead',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_deals_tenant_contact ON crm_deals(tenant_id, contact_id);
CREATE INDEX IF NOT EXISTS idx_deals_vehicle        ON crm_deals(vehicle_id)
    WHERE vehicle_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS crm_activities (
    id         TEXT PRIMARY KEY,
    tenant_id  TEXT NOT NULL,
    deal_id    TEXT NOT NULL REFERENCES crm_deals(id),
    type       TEXT NOT NULL,
    body       TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_activities_deal ON crm_activities(deal_id);

CREATE TABLE IF NOT EXISTS crm_conversations (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    contact_id      TEXT NOT NULL REFERENCES crm_contacts(id),
    vehicle_id      TEXT REFERENCES crm_vehicles(id),
    deal_id         TEXT REFERENCES crm_deals(id),
    source_platform TEXT NOT NULL,
    external_id     TEXT,
    subject         TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'open',
    unread          INTEGER NOT NULL DEFAULT 1,
    last_message_at TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_conversations_tenant ON crm_conversations(tenant_id, status, last_message_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_conversations_dedup
    ON crm_conversations(tenant_id, source_platform, external_id)
    WHERE external_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS crm_messages (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES crm_conversations(id),
    direction       TEXT NOT NULL,
    sender_name     TEXT NOT NULL DEFAULT '',
    sender_email    TEXT NOT NULL DEFAULT '',
    body            TEXT NOT NULL,
    template_id     TEXT,
    sent_via        TEXT NOT NULL DEFAULT 'manual',
    sent_at         TEXT NOT NULL,
    read_at         TEXT,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON crm_messages(conversation_id, sent_at);

CREATE TABLE IF NOT EXISTS crm_templates (
    id         TEXT PRIMARY KEY,
    tenant_id  TEXT NOT NULL,
    name       TEXT NOT NULL,
    language   TEXT NOT NULL,
    subject    TEXT NOT NULL,
    body       TEXT NOT NULL,
    is_system  INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(tenant_id, name, language)
);
CREATE INDEX IF NOT EXISTS idx_templates_tenant ON crm_templates(tenant_id, language);
`

// EnsureSchema creates all inbox tables if they do not exist.
func EnsureSchema(db *sql.DB) error {
	_, err := db.Exec(inboxSchema)
	return err
}

// systemTenant is the owner of built-in templates shared across all tenants.
const systemTenant = "_system_"

type systemTemplate struct {
	name, lang, subject, body string
}

var systemTemplates = []systemTemplate{
	// inquiry_ack
	{"inquiry_ack", "DE", "Danke für Ihr Interesse an unserem {{make}} {{model}}", "Sehr geehrte/r {{name}},\n\nvielen Dank für Ihr Interesse an unserem {{make}} {{model}} ({{year}}). Wir werden uns schnellstmöglich bei Ihnen melden.\n\nMit freundlichen Grüßen"},
	{"inquiry_ack", "FR", "Merci pour votre intérêt pour notre {{make}} {{model}}", "Cher(e) {{name}},\n\nNous vous remercions de l'intérêt que vous portez à notre {{make}} {{model}} ({{year}}). Nous vous contacterons dans les plus brefs délais.\n\nCordialement"},
	{"inquiry_ack", "ES", "Gracias por su interés en nuestro {{make}} {{model}}", "Estimado/a {{name}},\n\nGracias por su interés en nuestro {{make}} {{model}} ({{year}}). Nos pondremos en contacto con usted a la brevedad posible.\n\nAtentamente"},
	{"inquiry_ack", "NL", "Bedankt voor uw interesse in onze {{make}} {{model}}", "Beste {{name}},\n\nBedankt voor uw interesse in onze {{make}} {{model}} ({{year}}). We nemen zo snel mogelijk contact met u op.\n\nMet vriendelijke groeten"},
	{"inquiry_ack", "EN", "Thank you for your interest in our {{make}} {{model}}", "Dear {{name}},\n\nThank you for your interest in our {{make}} {{model}} ({{year}}). We will get back to you as soon as possible.\n\nKind regards"},
	// price_offer
	{"price_offer", "DE", "Preisangebot für den {{make}} {{model}}", "Sehr geehrte/r {{name}},\n\nwir bestätigen Ihnen den Preis von {{price}} für den {{make}} {{model}} ({{year}}). Dieses Angebot gilt für 7 Tage.\n\nMit freundlichen Grüßen"},
	{"price_offer", "FR", "Offre de prix pour le {{make}} {{model}}", "Cher(e) {{name}},\n\nNous vous confirmons le prix de {{price}} pour le {{make}} {{model}} ({{year}}). Cette offre est valable 7 jours.\n\nCordialement"},
	{"price_offer", "ES", "Oferta de precio para el {{make}} {{model}}", "Estimado/a {{name}},\n\nLe confirmamos el precio de {{price}} para el {{make}} {{model}} ({{year}}). Esta oferta es válida durante 7 días.\n\nAtentamente"},
	{"price_offer", "NL", "Prijsaanbieding voor de {{make}} {{model}}", "Beste {{name}},\n\nWij bevestigen de prijs van {{price}} voor de {{make}} {{model}} ({{year}}). Dit aanbod geldt 7 dagen.\n\nMet vriendelijke groeten"},
	{"price_offer", "EN", "Price offer for the {{make}} {{model}}", "Dear {{name}},\n\nWe confirm the price of {{price}} for the {{make}} {{model}} ({{year}}). This offer is valid for 7 days.\n\nKind regards"},
	// follow_up
	{"follow_up", "DE", "Nachfrage zu Ihrem Interesse am {{make}} {{model}}", "Sehr geehrte/r {{name}},\n\nvor {{days}} Tagen haben wir Ihnen ein Angebot für den {{make}} {{model}} zugesandt. Haben Sie noch Fragen?\n\nMit freundlichen Grüßen"},
	{"follow_up", "FR", "Suivi de votre intérêt pour le {{make}} {{model}}", "Cher(e) {{name}},\n\nIl y a {{days}} jours, nous vous avons envoyé une offre pour le {{make}} {{model}}. Avez-vous des questions?\n\nCordialement"},
	{"follow_up", "ES", "Seguimiento de su interés en el {{make}} {{model}}", "Estimado/a {{name}},\n\nHace {{days}} días le enviamos una oferta para el {{make}} {{model}}. ¿Tiene alguna pregunta?\n\nAtentamente"},
	{"follow_up", "NL", "Opvolging van uw interesse in de {{make}} {{model}}", "Beste {{name}},\n\n{{days}} dagen geleden stuurden wij u een aanbieding voor de {{make}} {{model}}. Heeft u nog vragen?\n\nMet vriendelijke groeten"},
	{"follow_up", "EN", "Follow-up on your interest in the {{make}} {{model}}", "Dear {{name}},\n\n{{days}} days ago we sent you an offer for the {{make}} {{model}}. Do you have any questions?\n\nKind regards"},
	// visit_invite
	{"visit_invite", "DE", "Einladung zur Besichtigung des {{make}} {{model}}", "Sehr geehrte/r {{name}},\n\nwir laden Sie herzlich ein, unsere Ausstellung zu besuchen und den {{make}} {{model}} ({{year}}) persönlich zu besichtigen.\n\nMit freundlichen Grüßen"},
	{"visit_invite", "FR", "Invitation à visiter le {{make}} {{model}}", "Cher(e) {{name}},\n\nNous vous invitons à visiter nos installations pour voir le {{make}} {{model}} ({{year}}) en personne.\n\nCordialement"},
	{"visit_invite", "ES", "Invitación a visitar nuestras instalaciones — {{make}} {{model}}", "Estimado/a {{name}},\n\nLe invitamos a visitar nuestras instalaciones para ver el {{make}} {{model}} ({{year}}) en persona.\n\nAtentamente"},
	{"visit_invite", "NL", "Uitnodiging voor een bezoek — {{make}} {{model}}", "Beste {{name}},\n\nWij nodigen u uit om onze showroom te bezoeken en de {{make}} {{model}} ({{year}}) in persoon te bekijken.\n\nMet vriendelijke groeten"},
	{"visit_invite", "EN", "Invitation to visit our showroom — {{make}} {{model}}", "Dear {{name}},\n\nWe would like to invite you to visit our showroom and see the {{make}} {{model}} ({{year}}) in person.\n\nKind regards"},
	// rejection
	{"rejection", "DE", "Information zu Ihrem Interesse am {{make}} {{model}}", "Sehr geehrte/r {{name}},\n\nleider müssen wir Ihnen mitteilen, dass der {{make}} {{model}} ({{year}}) bereits verkauft wurde. Gerne zeigen wir Ihnen ähnliche Fahrzeuge.\n\nMit freundlichen Grüßen"},
	{"rejection", "FR", "Information concernant le {{make}} {{model}}", "Cher(e) {{name}},\n\nNous regrettons de vous informer que le {{make}} {{model}} ({{year}}) a été vendu. Nous pouvons vous proposer des véhicules similaires.\n\nCordialement"},
	{"rejection", "ES", "Información sobre el {{make}} {{model}}", "Estimado/a {{name}},\n\nLamentamos informarle que el {{make}} {{model}} ({{year}}) ha sido vendido. Con gusto le mostraremos vehículos similares.\n\nAtentamente"},
	{"rejection", "NL", "Informatie over de {{make}} {{model}}", "Beste {{name}},\n\nHelaas moeten wij u mededelen dat de {{make}} {{model}} ({{year}}) al verkocht is. Graag tonen wij u vergelijkbare voertuigen.\n\nMet vriendelijke groeten"},
	{"rejection", "EN", "Update on the {{make}} {{model}}", "Dear {{name}},\n\nWe regret to inform you that the {{make}} {{model}} ({{year}}) has been sold. We would be happy to show you similar vehicles.\n\nKind regards"},
}

// SeedSystemTemplates inserts built-in templates (idempotent via INSERT OR IGNORE).
func SeedSystemTemplates(db *sql.DB) error {
	now := time.Now().UTC().Format(time.RFC3339)
	tx, err := db.Begin()
	if err != nil {
		return err
	}
	defer tx.Rollback() //nolint:errcheck
	stmt, err := tx.Prepare(`
		INSERT OR IGNORE INTO crm_templates(id,tenant_id,name,language,subject,body,is_system,created_at,updated_at)
		VALUES(?,?,?,?,?,?,1,?,?)`)
	if err != nil {
		return err
	}
	defer stmt.Close()
	for _, t := range systemTemplates {
		id := newID()
		if _, err := stmt.Exec(id, systemTenant, t.name, t.lang, t.subject, t.body, now, now); err != nil {
			return err
		}
	}
	return tx.Commit()
}
