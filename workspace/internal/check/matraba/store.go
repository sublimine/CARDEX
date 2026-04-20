package matraba

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"strings"
	"time"
)

// Store is a SQLite-backed VIN index over the MATRABA feed. It lets the
// ES plate resolver enrich its PlateResult with DGT-grade technical fields
// (municipality, homologation, electric range, wheelbase, etc.) after a
// VIN has been retrieved from comprobarmatricula.com.
//
// Post-2025-02 the published VINs are masked (last 10 chars replaced by
// asterisks). The schema therefore carries a separate `vin_prefix` column
// indexing the first 11 chars (WMI + first 3 VDS) so lookups can fall
// back to prefix matching when the full VIN is not available.
//
// Records are written in bulk via ImportTx — a single big transaction
// per monthly dump (typically 300 k-1 M rows). The record payload is
// stored as JSON to keep the schema forward-compatible; queried fields
// are duplicated into top-level columns for fast filtering.
type Store struct {
	db *sql.DB
}

// NewStore wraps an already-open *sql.DB. The caller owns the connection
// lifecycle; Close only releases the wrapper.
func NewStore(db *sql.DB) *Store {
	return &Store{db: db}
}

// Schema defines the matraba_vehicles table. Applied idempotently by
// EnsureSchema; also embedded by the main workspace schema in cache.go
// once the importer ships to production.
const Schema = `
CREATE TABLE IF NOT EXISTS matraba_vehicles (
    vin                TEXT PRIMARY KEY,
    vin_prefix         TEXT NOT NULL,
    cod_clase_mat      TEXT,
    cod_tipo           TEXT,
    cod_propulsion     TEXT,
    marca              TEXT,
    modelo             TEXT,
    version            TEXT,
    fec_matricula      TEXT, -- ISO YYYY-MM-DD
    fec_prim_mat       TEXT,
    cod_provincia_veh  TEXT,
    cod_provincia_mat  TEXT,
    municipio          TEXT,
    cod_municipio_ine  TEXT,
    categoria_eu       TEXT,
    categoria_electric TEXT,
    contrasena_homolog TEXT,
    record_json        BLOB NOT NULL,
    imported_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_matraba_prefix ON matraba_vehicles(vin_prefix);
CREATE INDEX IF NOT EXISTS idx_matraba_marca  ON matraba_vehicles(marca);
CREATE INDEX IF NOT EXISTS idx_matraba_fecmat ON matraba_vehicles(fec_matricula);

CREATE TABLE IF NOT EXISTS matraba_imports (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source_url   TEXT NOT NULL,
    source_file  TEXT,
    dataset      TEXT NOT NULL,       -- "matraba" / "transfe" / "bajas"
    year_month   TEXT NOT NULL,       -- "2024-12"
    rows_total   INTEGER NOT NULL,
    rows_parsed  INTEGER NOT NULL,
    rows_masked  INTEGER NOT NULL,
    started_at   TEXT NOT NULL,
    finished_at  TEXT,
    error        TEXT
);
`

// EnsureSchema creates the matraba tables/indexes if they do not exist.
func EnsureSchema(db *sql.DB) error {
	_, err := db.Exec(Schema)
	return err
}

// ImportStats summarises the rows written during an ImportTx call.
type ImportStats struct {
	RowsWritten int64
	RowsMasked  int64 // subset of RowsWritten with partially-masked VINs
}

// ImportTx inserts every record yielded by feed into matraba_vehicles
// inside a single transaction. A record's VIN is the primary key, so
// repeated imports idempotently upsert (latest record wins — transfer/
// deregistration dumps therefore correctly overwrite older matriculation
// rows for the same vehicle).
//
// feed is typically wired to ParseZIP/ParseFile: the caller drives the
// parser, which invokes a closure that appends records to an unbuffered
// channel; ImportTx drains the channel. This keeps parsing and DB writes
// in lockstep without buffering the whole dump in memory.
func (s *Store) ImportTx(ctx context.Context, feed <-chan Record) (ImportStats, error) {
	var stats ImportStats
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return stats, fmt.Errorf("matraba begin tx: %w", err)
	}
	defer func() {
		if p := recover(); p != nil {
			_ = tx.Rollback()
			panic(p)
		}
	}()

	const insertSQL = `
		INSERT INTO matraba_vehicles(
			vin, vin_prefix, cod_clase_mat, cod_tipo, cod_propulsion,
			marca, modelo, version, fec_matricula, fec_prim_mat,
			cod_provincia_veh, cod_provincia_mat, municipio, cod_municipio_ine,
			categoria_eu, categoria_electric, contrasena_homolog,
			record_json, imported_at
		) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
		ON CONFLICT(vin) DO UPDATE SET
			vin_prefix = excluded.vin_prefix,
			cod_clase_mat = excluded.cod_clase_mat,
			cod_tipo = excluded.cod_tipo,
			cod_propulsion = excluded.cod_propulsion,
			marca = excluded.marca,
			modelo = excluded.modelo,
			version = excluded.version,
			fec_matricula = excluded.fec_matricula,
			fec_prim_mat = excluded.fec_prim_mat,
			cod_provincia_veh = excluded.cod_provincia_veh,
			cod_provincia_mat = excluded.cod_provincia_mat,
			municipio = excluded.municipio,
			cod_municipio_ine = excluded.cod_municipio_ine,
			categoria_eu = excluded.categoria_eu,
			categoria_electric = excluded.categoria_electric,
			contrasena_homolog = excluded.contrasena_homolog,
			record_json = excluded.record_json,
			imported_at = excluded.imported_at
	`
	stmt, err := tx.PrepareContext(ctx, insertSQL)
	if err != nil {
		_ = tx.Rollback()
		return stats, fmt.Errorf("matraba prepare insert: %w", err)
	}
	defer stmt.Close()

	importedAt := time.Now().UTC().Format(time.RFC3339)

	for r := range feed {
		if r.Bastidor == "" {
			// Rows without a VIN can't be indexed and would collide on the
			// empty-string primary key — skip.
			continue
		}
		blob, err := json.Marshal(r)
		if err != nil {
			_ = tx.Rollback()
			return stats, fmt.Errorf("matraba marshal record %q: %w", r.Bastidor, err)
		}
		_, err = stmt.ExecContext(ctx,
			r.Bastidor, r.VINPrefix(),
			r.CodClaseMat, r.CodTipo, r.CodPropulsionITV,
			r.MarcaITV, r.ModeloITV, r.VersionITV,
			isoDate(r.FecMatricula), isoDate(r.FecPrimMatriculacion),
			r.CodProvinciaVeh, r.CodProvinciaMat, r.Municipio, r.CodMunicipioINE,
			r.CatHomologacionUE, r.CategoriaElectrico, r.ContrasenaHomolog,
			blob, importedAt,
		)
		if err != nil {
			_ = tx.Rollback()
			return stats, fmt.Errorf("matraba insert %q: %w", r.Bastidor, err)
		}
		stats.RowsWritten++
		if r.VINMasked() {
			stats.RowsMasked++
		}
	}

	if err := tx.Commit(); err != nil {
		return stats, fmt.Errorf("matraba commit: %w", err)
	}
	return stats, nil
}

// RecordImport appends a bookkeeping row to matraba_imports. Invoked by
// the CLI before/after each file is processed so we have an audit trail
// of what was ingested when, keyed by source URL.
func (s *Store) RecordImport(ctx context.Context, sourceURL, sourceFile, dataset, yearMonth string, rowsTotal, rowsParsed, rowsMasked int64, importErr error) error {
	errStr := ""
	if importErr != nil {
		errStr = importErr.Error()
	}
	_, err := s.db.ExecContext(ctx,
		`INSERT INTO matraba_imports(source_url, source_file, dataset, year_month,
			rows_total, rows_parsed, rows_masked, started_at, finished_at, error)
		 VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
		sourceURL, sourceFile, dataset, yearMonth,
		rowsTotal, rowsParsed, rowsMasked,
		time.Now().UTC().Format(time.RFC3339), time.Now().UTC().Format(time.RFC3339),
		errStr,
	)
	return err
}

// LookupByVIN returns the most recently imported Record for a full VIN
// (17 chars). Returns ok=false when no row matches.
func (s *Store) LookupByVIN(ctx context.Context, vin string) (Record, bool, error) {
	vin = strings.ToUpper(strings.TrimSpace(vin))
	if vin == "" {
		return Record{}, false, nil
	}
	var blob []byte
	err := s.db.QueryRowContext(ctx,
		`SELECT record_json FROM matraba_vehicles WHERE vin = ?`, vin,
	).Scan(&blob)
	if err == sql.ErrNoRows {
		return Record{}, false, nil
	}
	if err != nil {
		return Record{}, false, fmt.Errorf("matraba lookup: %w", err)
	}
	var r Record
	if err := json.Unmarshal(blob, &r); err != nil {
		return Record{}, false, fmt.Errorf("matraba decode record: %w", err)
	}
	return r, true, nil
}

// LookupByPrefix returns up to limit records whose VIN prefix (first 11
// chars) matches. Used for post-2025-02 redacted VINs where only the
// prefix is available. Results are ordered by fec_matricula DESC so the
// most recent match wins.
func (s *Store) LookupByPrefix(ctx context.Context, prefix string, limit int) ([]Record, error) {
	prefix = strings.ToUpper(strings.TrimSpace(prefix))
	if prefix == "" {
		return nil, nil
	}
	if limit <= 0 {
		limit = 10
	}
	rows, err := s.db.QueryContext(ctx,
		`SELECT record_json FROM matraba_vehicles
		 WHERE vin_prefix = ?
		 ORDER BY fec_matricula DESC
		 LIMIT ?`, prefix, limit)
	if err != nil {
		return nil, fmt.Errorf("matraba prefix query: %w", err)
	}
	defer rows.Close()

	var out []Record
	for rows.Next() {
		var blob []byte
		if err := rows.Scan(&blob); err != nil {
			return nil, err
		}
		var r Record
		if err := json.Unmarshal(blob, &r); err != nil {
			continue
		}
		out = append(out, r)
	}
	return out, rows.Err()
}

// Count returns the total number of indexed vehicles.
func (s *Store) Count(ctx context.Context) (int64, error) {
	var n int64
	err := s.db.QueryRowContext(ctx,
		`SELECT COUNT(*) FROM matraba_vehicles`).Scan(&n)
	return n, err
}

func isoDate(t time.Time) string {
	if t.IsZero() {
		return ""
	}
	return t.Format("2006-01-02")
}
