package kg

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
)

// UpsertWebPresence inserts or updates a dealer web presence entry keyed on domain.
// On conflict with an existing domain entry, url_root and discovered_by_families
// are updated; all other fields retain their existing values.
func (g *SQLiteGraph) UpsertWebPresence(ctx context.Context, wp *DealerWebPresence) error {
	const q = `
INSERT INTO dealer_web_presence
  (web_id, dealer_id, domain, url_root, platform_type, dms_provider,
   extraction_strategy, discovered_by_families, metadata_json)
VALUES (?,?,?,?,?,?,?,?,?)
ON CONFLICT(domain) DO UPDATE SET
  url_root               = excluded.url_root,
  discovered_by_families = excluded.discovered_by_families`

	_, err := g.db.ExecContext(ctx, q,
		wp.WebID,
		wp.DealerID,
		wp.Domain,
		wp.URLRoot,
		wp.PlatformType,
		wp.DMSProvider,
		wp.ExtractionStrategy,
		wp.DiscoveredByFamilies,
		wp.MetadataJSON,
	)
	if err != nil {
		return fmt.Errorf("kg.UpsertWebPresence %q: %w", wp.Domain, err)
	}
	return nil
}

// FindDealerIDByDomain returns the dealer_id for the given domain or ("", nil)
// when no web presence entry exists for that domain.
func (g *SQLiteGraph) FindDealerIDByDomain(ctx context.Context, domain string) (string, error) {
	const q = `SELECT dealer_id FROM dealer_web_presence WHERE domain = ? LIMIT 1`
	var dealerID string
	err := g.db.QueryRowContext(ctx, q, domain).Scan(&dealerID)
	if errors.Is(err, sql.ErrNoRows) {
		return "", nil
	}
	if err != nil {
		return "", fmt.Errorf("kg.FindDealerIDByDomain %q: %w", domain, err)
	}
	return dealerID, nil
}

// UpdateWebPresenceMetadata overwrites the metadata_json field for the given
// domain. Returns an error when the domain has no web presence entry.
func (g *SQLiteGraph) UpdateWebPresenceMetadata(ctx context.Context, domain, metadataJSON string) error {
	const q = `UPDATE dealer_web_presence SET metadata_json = ? WHERE domain = ?`
	res, err := g.db.ExecContext(ctx, q, metadataJSON, domain)
	if err != nil {
		return fmt.Errorf("kg.UpdateWebPresenceMetadata %q: %w", domain, err)
	}
	n, _ := res.RowsAffected()
	if n == 0 {
		return fmt.Errorf("kg.UpdateWebPresenceMetadata %q: domain not found", domain)
	}
	return nil
}

// ListWebPresencesByCountry returns all web presence entries for dealers whose
// country_code matches the given ISO 3166-1 alpha-2 code. Returns an empty
// (non-nil) slice when no entries are found.
func (g *SQLiteGraph) ListWebPresencesByCountry(ctx context.Context, country string) ([]*DealerWebPresence, error) {
	const q = `
SELECT wp.web_id, wp.dealer_id, wp.domain, wp.url_root,
       wp.platform_type, wp.dms_provider, wp.extraction_strategy,
       wp.discovered_by_families, wp.metadata_json
FROM dealer_web_presence wp
JOIN dealer_entity de ON wp.dealer_id = de.dealer_id
WHERE de.country_code = ?`

	rows, err := g.db.QueryContext(ctx, q, country)
	if err != nil {
		return nil, fmt.Errorf("kg.ListWebPresencesByCountry %q: %w", country, err)
	}
	defer rows.Close()

	var wps []*DealerWebPresence
	for rows.Next() {
		wp := &DealerWebPresence{}
		var (
			platformType       sql.NullString
			dmsProvider        sql.NullString
			extractionStrategy sql.NullString
			metadataJSON       sql.NullString
		)
		if err := rows.Scan(
			&wp.WebID, &wp.DealerID, &wp.Domain, &wp.URLRoot,
			&platformType, &dmsProvider, &extractionStrategy,
			&wp.DiscoveredByFamilies, &metadataJSON,
		); err != nil {
			return nil, fmt.Errorf("kg.ListWebPresencesByCountry: scan: %w", err)
		}
		if platformType.Valid {
			wp.PlatformType = &platformType.String
		}
		if dmsProvider.Valid {
			wp.DMSProvider = &dmsProvider.String
		}
		if extractionStrategy.Valid {
			wp.ExtractionStrategy = &extractionStrategy.String
		}
		if metadataJSON.Valid {
			wp.MetadataJSON = &metadataJSON.String
		}
		wps = append(wps, wp)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("kg.ListWebPresencesByCountry: rows: %w", err)
	}
	if wps == nil {
		wps = []*DealerWebPresence{} // always return non-nil slice
	}
	return wps, nil
}
