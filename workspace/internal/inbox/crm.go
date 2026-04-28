package inbox

import (
	"database/sql"
	"strconv"
	"time"
)

// nillable converts empty string to nil for nullable SQLite TEXT columns.
func nillable(s string) any {
	if s == "" {
		return nil
	}
	return s
}

// ── CRM store — thin read layer over crm_* tables ────────────────────────────

// CRMStore provides read-only listing for the core CRM entities.
// All write operations happen via the ingestion / conversation paths.
type CRMStore struct {
	db *sql.DB
}

func NewCRMStore(db *sql.DB) *CRMStore { return &CRMStore{db: db} }

// ── API response types (camelCase JSON to match the web frontend) ─────────────

type CRMVehicle struct {
	ID         string `json:"id"`
	TenantID   string `json:"tenantId"`
	ExternalID string `json:"externalId,omitempty"`
	VIN        string `json:"vin,omitempty"`
	Make       string `json:"make"`
	Model      string `json:"model"`
	Year       int    `json:"year"`
	Status     string `json:"status"`
	// Finance fields — 0/empty for entries not yet enriched by finance module.
	Price      float64 `json:"price"`
	Currency   string  `json:"currency"`
	DaysInStock int    `json:"daysInStock"`
	Margin     float64 `json:"margin"`
	CreatedAt  string  `json:"createdAt"`
	UpdatedAt  string  `json:"updatedAt"`
}

type VehicleListResponse struct {
	Vehicles []CRMVehicle `json:"vehicles"`
	Total    int          `json:"total"`
	Page     int          `json:"page"`
	PageSize int          `json:"pageSize"`
}

type CRMContact struct {
	ID        string `json:"id"`
	TenantID  string `json:"tenantId"`
	Name      string `json:"name"`
	Email     string `json:"email"`
	Phone     string `json:"phone"`
	DealCount int    `json:"dealCount"`
	CreatedAt string `json:"createdAt"`
	UpdatedAt string `json:"updatedAt"`
}

type ContactListResponse struct {
	Contacts []CRMContact `json:"contacts"`
	Total    int          `json:"total"`
}

type CRMDeal struct {
	ID          string `json:"id"`
	TenantID    string `json:"tenantId"`
	ContactID   string `json:"contactId"`
	VehicleID   string `json:"vehicleId,omitempty"`
	Stage       string `json:"stage"`
	ContactName string `json:"contactName,omitempty"`
	VehicleName string `json:"vehicleName,omitempty"`
	CreatedAt   string `json:"createdAt"`
	UpdatedAt   string `json:"updatedAt"`
}

type DealListResponse struct {
	Deals []CRMDeal `json:"deals"`
	Total int       `json:"total"`
}

type ConversationListResponse struct {
	Conversations []*Conversation `json:"conversations"`
	Total         int             `json:"total"`
}

// ── Vehicle listing ───────────────────────────────────────────────────────────

func (s *CRMStore) ListVehicles(tenantID string, page, pageSize int, status string) (VehicleListResponse, error) {
	if page < 1 {
		page = 1
	}
	if pageSize < 1 || pageSize > 200 {
		pageSize = 20
	}
	offset := (page - 1) * pageSize

	args := []any{tenantID}
	where := "WHERE v.tenant_id = ?"
	if status != "" {
		where += " AND v.status = ?"
		args = append(args, status)
	}

	// Total count
	var total int
	if err := s.db.QueryRow(
		"SELECT COUNT(*) FROM crm_vehicles v "+where, args...,
	).Scan(&total); err != nil {
		return VehicleListResponse{}, err
	}

	// Page rows — left-join finance store for price/margin/days_in_stock when available.
	// For now we pull the base columns; the finance module enriches individual vehicles.
	rows, err := s.db.Query(
		`SELECT v.id, v.tenant_id,
		        COALESCE(v.external_id,''), COALESCE(v.vin,''),
		        v.make, v.model, v.year, v.status,
		        COALESCE(v.created_at,''), COALESCE(v.updated_at,''),
		        CAST((julianday('now') - julianday(v.created_at)) AS INTEGER)
		 FROM crm_vehicles v `+
			where+
			` ORDER BY v.updated_at DESC
		 LIMIT ? OFFSET ?`,
		append(args, pageSize, offset)...,
	)
	if err != nil {
		return VehicleListResponse{}, err
	}
	defer rows.Close()

	vehicles := make([]CRMVehicle, 0)
	for rows.Next() {
		var v CRMVehicle
		if err := rows.Scan(
			&v.ID, &v.TenantID, &v.ExternalID, &v.VIN,
			&v.Make, &v.Model, &v.Year, &v.Status,
			&v.CreatedAt, &v.UpdatedAt, &v.DaysInStock,
		); err != nil {
			return VehicleListResponse{}, err
		}
		v.Currency = "EUR"
		vehicles = append(vehicles, v)
	}
	if err := rows.Err(); err != nil {
		return VehicleListResponse{}, err
	}

	return VehicleListResponse{
		Vehicles: vehicles,
		Total:    total,
		Page:     page,
		PageSize: pageSize,
	}, nil
}

// ── Contact listing ───────────────────────────────────────────────────────────

func (s *CRMStore) ListContacts(tenantID string, page, pageSize int, search string) (ContactListResponse, error) {
	if page < 1 {
		page = 1
	}
	if pageSize < 1 || pageSize > 200 {
		pageSize = 20
	}
	offset := (page - 1) * pageSize

	args := []any{tenantID}
	where := "WHERE c.tenant_id = ?"
	if search != "" {
		where += " AND (c.name LIKE ? OR c.email LIKE ? OR c.phone LIKE ?)"
		s := "%" + search + "%"
		args = append(args, s, s, s)
	}

	var total int
	if err := s.db.QueryRow(
		"SELECT COUNT(*) FROM crm_contacts c "+where, args...,
	).Scan(&total); err != nil {
		return ContactListResponse{}, err
	}

	rows, err := s.db.Query(
		`SELECT c.id, c.tenant_id, c.name, c.email, c.phone,
		        c.created_at, c.updated_at,
		        (SELECT COUNT(*) FROM crm_deals d WHERE d.contact_id = c.id) AS deal_count
		 FROM crm_contacts c `+
			where+
			` ORDER BY c.updated_at DESC
		 LIMIT ? OFFSET ?`,
		append(args, pageSize, offset)...,
	)
	if err != nil {
		return ContactListResponse{}, err
	}
	defer rows.Close()

	contacts := make([]CRMContact, 0)
	for rows.Next() {
		var c CRMContact
		if err := rows.Scan(
			&c.ID, &c.TenantID, &c.Name, &c.Email, &c.Phone,
			&c.CreatedAt, &c.UpdatedAt, &c.DealCount,
		); err != nil {
			return ContactListResponse{}, err
		}
		contacts = append(contacts, c)
	}
	if err := rows.Err(); err != nil {
		return ContactListResponse{}, err
	}

	return ContactListResponse{Contacts: contacts, Total: total}, nil
}

// ── Deal listing ──────────────────────────────────────────────────────────────

func (s *CRMStore) ListDeals(tenantID string, page, pageSize int, stage string) (DealListResponse, error) {
	if page < 1 {
		page = 1
	}
	if pageSize < 1 || pageSize > 200 {
		pageSize = 20
	}
	offset := (page - 1) * pageSize

	args := []any{tenantID}
	where := "WHERE d.tenant_id = ?"
	if stage != "" {
		where += " AND d.stage = ?"
		args = append(args, stage)
	}

	var total int
	if err := s.db.QueryRow(
		"SELECT COUNT(*) FROM crm_deals d "+where, args...,
	).Scan(&total); err != nil {
		return DealListResponse{}, err
	}

	rows, err := s.db.Query(
		`SELECT d.id, d.tenant_id,
		        d.contact_id, COALESCE(d.vehicle_id,''),
		        d.stage, d.created_at, d.updated_at,
		        COALESCE(c.name,''), COALESCE(v.make||' '||v.model,'')
		 FROM crm_deals d
		 LEFT JOIN crm_contacts c ON c.id = d.contact_id
		 LEFT JOIN crm_vehicles v ON v.id = d.vehicle_id
		 `+where+
			` ORDER BY d.updated_at DESC
		 LIMIT ? OFFSET ?`,
		append(args, pageSize, offset)...,
	)
	if err != nil {
		return DealListResponse{}, err
	}
	defer rows.Close()

	deals := make([]CRMDeal, 0)
	for rows.Next() {
		var d CRMDeal
		if err := rows.Scan(
			&d.ID, &d.TenantID,
			&d.ContactID, &d.VehicleID,
			&d.Stage, &d.CreatedAt, &d.UpdatedAt,
			&d.ContactName, &d.VehicleName,
		); err != nil {
			return DealListResponse{}, err
		}
		deals = append(deals, d)
	}
	if err := rows.Err(); err != nil {
		return DealListResponse{}, err
	}

	return DealListResponse{Deals: deals, Total: total}, nil
}

// ── Deal mutation ─────────────────────────────────────────────────────────────

func (s *CRMStore) PatchDeal(tenantID, id string, stage string) error {
	if stage == "" {
		return errMsg("stage is required")
	}
	now := time.Now().UTC().Format(time.RFC3339)
	res, err := s.db.Exec(
		`UPDATE crm_deals SET stage=?, updated_at=? WHERE id=? AND tenant_id=?`,
		stage, now, id, tenantID,
	)
	if err != nil {
		return err
	}
	n, _ := res.RowsAffected()
	if n == 0 {
		return errMsg("deal not found")
	}
	return nil
}

func (s *CRMStore) CreateDeal(tenantID, contactID, vehicleID, stage string) (CRMDeal, error) {
	id := newID()
	if stage == "" {
		stage = "lead"
	}
	now := time.Now().UTC().Format(time.RFC3339)
	_, err := s.db.Exec(
		`INSERT INTO crm_deals(id,tenant_id,contact_id,vehicle_id,stage,created_at,updated_at)
		 VALUES(?,?,?,?,?,?,?)`,
		id, tenantID, contactID, nillable(vehicleID), stage, now, now,
	)
	if err != nil {
		return CRMDeal{}, err
	}
	return CRMDeal{
		ID:        id,
		TenantID:  tenantID,
		ContactID: contactID,
		VehicleID: vehicleID,
		Stage:     stage,
		CreatedAt: now,
		UpdatedAt: now,
	}, nil
}

// ── Contact detail ────────────────────────────────────────────────────────────

type ContactDetailResponse struct {
	Contact    CRMContact `json:"contact"`
	Activities []struct{} `json:"activities"` // placeholder — populated by inbox module later
}

func (s *CRMStore) GetContact(tenantID, id string) (CRMContact, error) {
	var c CRMContact
	err := s.db.QueryRow(
		`SELECT c.id, c.tenant_id, c.name, c.email, c.phone,
		        c.created_at, c.updated_at,
		        (SELECT COUNT(*) FROM crm_deals d WHERE d.contact_id = c.id) AS deal_count
		 FROM crm_contacts c
		 WHERE c.id=? AND c.tenant_id=?`,
		id, tenantID,
	).Scan(&c.ID, &c.TenantID, &c.Name, &c.Email, &c.Phone,
		&c.CreatedAt, &c.UpdatedAt, &c.DealCount)
	if err == sql.ErrNoRows {
		return c, errMsg("contact not found")
	}
	return c, err
}

// ── KPI aggregation ───────────────────────────────────────────────────────────

type KPISummary struct {
	StockCount    int `json:"stockCount"`
	ActiveDeals   int `json:"activeDeals"`
	PendingAlerts int `json:"pendingAlerts"`
}

func (s *CRMStore) KPISummary(tenantID string) (KPISummary, error) {
	var kpi KPISummary

	_ = s.db.QueryRow(
		`SELECT COUNT(*) FROM crm_vehicles WHERE tenant_id=? AND status NOT IN ('sold','withdrawn')`,
		tenantID,
	).Scan(&kpi.StockCount)

	_ = s.db.QueryRow(
		`SELECT COUNT(*) FROM crm_deals WHERE tenant_id=? AND stage NOT IN ('won','lost')`,
		tenantID,
	).Scan(&kpi.ActiveDeals)

	return kpi, nil
}

// ── helpers ───────────────────────────────────────────────────────────────────

// parseIntOr parses s as int; returns def on error or empty/invalid input.
func parseIntOr(s string, def int) int {
	if s == "" {
		return def
	}
	v, err := strconv.Atoi(s)
	if err != nil || v < 1 {
		return def
	}
	return v
}
