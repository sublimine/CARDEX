// review.go — cardex review subcommand group.
//
// Subcommands:
//
//	cardex review list [--status PENDING|APPROVED|REJECTED] [--limit N]
//	cardex review show <listing-id>
//	cardex review approve <listing-id>
//	cardex review reject <listing-id> --reason "..."
//
// The review_queue table is created on first use if it doesn't exist. Entries
// are inserted by the quality-service when a vehicle's composite score falls
// below the configured threshold OR when a validator sets needs_human_review.
//
// Table schema (auto-migrated):
//
//	review_queue(listing_id TEXT PK, status TEXT, reason_flags TEXT,
//	             reviewer TEXT, reject_reason TEXT,
//	             created_at TIMESTAMP, resolved_at TIMESTAMP)
package main

import (
	"database/sql"
	"fmt"
	"os/user"
	"strings"
	"time"

	"github.com/charmbracelet/lipgloss"
	"github.com/spf13/cobra"
)

// ── Review styles ─────────────────────────────────────────────────────────────

var (
	stylePending  = lipgloss.NewStyle().Foreground(lipgloss.Color("220")).Bold(true) // yellow
	styleApproved = lipgloss.NewStyle().Foreground(lipgloss.Color("82")).Bold(true)  // green
	styleRejected = lipgloss.NewStyle().Foreground(lipgloss.Color("196")).Bold(true) // red
)

const reviewSchema = `
CREATE TABLE IF NOT EXISTS review_queue (
    listing_id    TEXT     PRIMARY KEY,
    status        TEXT     NOT NULL DEFAULT 'PENDING',
    reason_flags  TEXT,
    reviewer      TEXT,
    reject_reason TEXT,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at   TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_review_status ON review_queue(status);
`

// ensureReviewSchema creates the review_queue table if it does not exist.
func ensureReviewSchema(db *sql.DB) error {
	_, err := db.Exec(reviewSchema)
	return err
}

// ── Review command tree ───────────────────────────────────────────────────────

var (
	flagReviewStatus string
	flagReviewLimit  int
	flagRejectReason string
)

func newReviewCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "review",
		Short: "Manage the manual review queue",
		Long: `cardex review — manage vehicles flagged for human review.

Vehicles are enqueued by the quality-service when their composite score falls
below the configured threshold (default: 40/100) or when a validator emits a
needs_human_review flag.`,
	}
	cmd.AddCommand(newReviewListCmd())
	cmd.AddCommand(newReviewShowCmd())
	cmd.AddCommand(newReviewApproveCmd())
	cmd.AddCommand(newReviewRejectCmd())
	return cmd
}

// ── cardex review list ────────────────────────────────────────────────────────

func newReviewListCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "list",
		Short: "List items in the review queue",
		Example: `  cardex review list
  cardex review list --status APPROVED --limit 50`,
		RunE: func(_ *cobra.Command, _ []string) error {
			db, err := openDB(flagDBPath)
			if err != nil {
				return err
			}
			defer db.Close()
			if err := ensureReviewSchema(db); err != nil {
				return fmt.Errorf("review schema: %w", err)
			}
			return runReviewList(db)
		},
	}
	cmd.Flags().StringVar(&flagReviewStatus, "status", "PENDING", "filter by status: PENDING, APPROVED, REJECTED, ALL")
	cmd.Flags().IntVar(&flagReviewLimit, "limit", 50, "maximum rows to return")
	return cmd
}

func runReviewList(db *sql.DB) error {
	query := `
		SELECT rq.listing_id,
		       rq.status,
		       COALESCE(rq.reason_flags, ''),
		       COALESCE(rq.reviewer, ''),
		       COALESCE(rq.reject_reason, ''),
		       rq.created_at,
		       COALESCE(rq.resolved_at, '')
		FROM review_queue rq`

	var args []any
	status := strings.ToUpper(strings.TrimSpace(flagReviewStatus))
	if status != "ALL" && status != "" {
		query += " WHERE rq.status = ?"
		args = append(args, status)
	}
	query += " ORDER BY rq.created_at DESC LIMIT ?"
	args = append(args, flagReviewLimit)

	rows, err := db.Query(query, args...)
	if err != nil {
		return fmt.Errorf("review list: %w", err)
	}
	defer rows.Close()

	type entry struct {
		listingID, status, flags, reviewer, rejectReason, createdAt, resolvedAt string
	}
	var entries []entry
	for rows.Next() {
		var e entry
		if err := rows.Scan(&e.listingID, &e.status, &e.flags, &e.reviewer,
			&e.rejectReason, &e.createdAt, &e.resolvedAt); err != nil {
			return err
		}
		entries = append(entries, e)
	}
	if err := rows.Err(); err != nil {
		return err
	}

	if len(entries) == 0 {
		fmt.Println(styleDim.Render("Review queue is empty."))
		return nil
	}

	hdr := fmt.Sprintf("%-30s %-10s %-28s %-20s %s",
		"LISTING ID", "STATUS", "FLAGS", "CREATED AT", "REVIEWER/NOTE")
	fmt.Println(styleHeader.Render(hdr))
	fmt.Println(strings.Repeat("─", 110))

	for _, e := range entries {
		statusStr := renderStatus(e.status)
		flags := e.flags
		if len(flags) > 26 {
			flags = flags[:23] + "..."
		}
		createdAt := e.createdAt
		if len(createdAt) > 19 {
			createdAt = createdAt[:19]
		}
		note := e.reviewer
		if e.rejectReason != "" {
			note += " — " + e.rejectReason
		}
		if len(note) > 30 {
			note = note[:27] + "..."
		}
		fmt.Printf("%-30s %-21s %-28s %-20s %s\n",
			e.listingID, statusStr, flags, createdAt, styleDim.Render(note))
	}
	fmt.Printf("\n%s\n", styleDim.Render(fmt.Sprintf("%d item(s)  (--status ALL to see all; --limit to paginate)", len(entries))))
	return nil
}

// ── cardex review show <id> ───────────────────────────────────────────────────

func newReviewShowCmd() *cobra.Command {
	return &cobra.Command{
		Use:     "show <listing-id>",
		Short:   "Show full details of a review queue item",
		Args:    cobra.ExactArgs(1),
		Example: `  cardex review show 01ARZ3NDEKTSV4RRFFQ69G5FAV`,
		RunE: func(_ *cobra.Command, args []string) error {
			db, err := openDB(flagDBPath)
			if err != nil {
				return err
			}
			defer db.Close()
			if err := ensureReviewSchema(db); err != nil {
				return fmt.Errorf("review schema: %w", err)
			}
			return runReviewShow(db, args[0])
		},
	}
}

func runReviewShow(db *sql.DB, listingID string) error {
	var status, flags, reviewer, rejectReason, createdAt, resolvedAt string
	err := db.QueryRow(`
		SELECT status,
		       COALESCE(reason_flags, ''),
		       COALESCE(reviewer, ''),
		       COALESCE(reject_reason, ''),
		       created_at,
		       COALESCE(resolved_at, '')
		FROM review_queue WHERE listing_id = ?`, listingID).
		Scan(&status, &flags, &reviewer, &rejectReason, &createdAt, &resolvedAt)
	if err == sql.ErrNoRows {
		return fmt.Errorf("listing %q not found in review queue", listingID)
	}
	if err != nil {
		return err
	}

	fmt.Println()
	fmt.Println(styleBorder.Render(
		styleHeader.Render("REVIEW QUEUE ITEM") + "\n\n" +
			field("Listing ID", listingID) +
			field("Status", renderStatus(status)) +
			field("Reason flags", flags) +
			field("Created at", createdAt) +
			field("Resolved at", resolvedAt) +
			field("Reviewer", reviewer) +
			field("Reject reason", rejectReason),
	))

	// Also print vehicle details if vehicle_raw or vehicle_record table exists.
	if err := printVehicleDetailsForReview(db, listingID); err != nil {
		fmt.Println(styleDim.Render("(vehicle details unavailable: " + err.Error() + ")"))
	}

	// Print quality validator results for this vehicle.
	valRows, err := db.Query(`
		SELECT validator_id, pass, severity, COALESCE(issue,'')
		FROM validation_result
		WHERE vehicle_id = ?
		ORDER BY validator_id`, listingID)
	if err == nil {
		defer valRows.Close()
		var validators []string
		for valRows.Next() {
			var vid, sev, issue string
			var pass bool
			if err := valRows.Scan(&vid, &pass, &sev, &issue); err != nil {
				break
			}
			mark := styleGreen.Render("✓")
			if !pass {
				if sev == "CRITICAL" {
					mark = styleRed.Render("✗")
				} else {
					mark = styleYellow.Render("⚠")
				}
			}
			line := fmt.Sprintf("  %s %s", mark, styleBold.Render(vid))
			if issue != "" {
				line += styleDim.Render(" — " + issue)
			}
			validators = append(validators, line)
		}
		if len(validators) > 0 {
			fmt.Println("\n" + styleHeader.Render("QUALITY VALIDATORS"))
			for _, v := range validators {
				fmt.Println(v)
			}
		}
	}

	fmt.Println()
	return nil
}

func printVehicleDetailsForReview(db *sql.DB, listingID string) error {
	// Check for vehicle_record (full schema) first, fall back to vehicle_raw.
	var exists int
	if err := db.QueryRow(`SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='vehicle_record'`).Scan(&exists); err != nil {
		return err
	}
	if exists == 0 {
		return fmt.Errorf("vehicle_record table not found")
	}

	var make_, model_, vin, url, country, dealer string
	var year, mileage, priceGross int
	var score float64
	err := db.QueryRow(`
		SELECT COALESCE(vr.make_canonical,''), COALESCE(vr.model_canonical,''),
		       COALESCE(vr.vin,''), COALESCE(vr.source_url,''),
		       COALESCE(de.country_code,''), COALESCE(de.canonical_name,''),
		       COALESCE(vr.year,0), COALESCE(vr.mileage_km,0),
		       CAST(COALESCE(vr.price_gross_eur,0) AS INTEGER),
		       COALESCE(vr.confidence_score,0.0)
		FROM vehicle_record vr
		LEFT JOIN dealer_entity de ON de.dealer_id = vr.dealer_id
		WHERE vr.vehicle_id = ?`, listingID).
		Scan(&make_, &model_, &vin, &url, &country, &dealer,
			&year, &mileage, &priceGross, &score)
	if err == sql.ErrNoRows {
		return fmt.Errorf("vehicle %q not in vehicle_record", listingID)
	}
	if err != nil {
		return err
	}

	fmt.Println(styleBorder.Render(
		styleHeader.Render("VEHICLE DETAILS") + "\n\n" +
			field("Make/Model", make_+" "+model_) +
			field("VIN", vin) +
			field("Year", fmt.Sprintf("%d", year)) +
			field("Mileage", fmt.Sprintf("%d km", mileage)) +
			field("Price (gross)", fmt.Sprintf("€%d", priceGross)) +
			field("Country", country) +
			field("Dealer", dealer) +
			field("Source URL", url) +
			field("Quality score", scoreStyle(score*100)),
	))
	return nil
}

// ── cardex review approve <id> ────────────────────────────────────────────────

func newReviewApproveCmd() *cobra.Command {
	return &cobra.Command{
		Use:     "approve <listing-id>",
		Short:   "Approve a pending review item",
		Args:    cobra.ExactArgs(1),
		Example: `  cardex review approve 01ARZ3NDEKTSV4RRFFQ69G5FAV`,
		RunE: func(_ *cobra.Command, args []string) error {
			db, err := openDB(flagDBPath)
			if err != nil {
				return err
			}
			defer db.Close()
			if err := ensureReviewSchema(db); err != nil {
				return fmt.Errorf("review schema: %w", err)
			}
			return runReviewApprove(db, args[0])
		},
	}
}

func runReviewApprove(db *sql.DB, listingID string) error {
	reviewer := currentUser()
	now := time.Now().UTC().Format(time.RFC3339)

	res, err := db.Exec(`
		UPDATE review_queue
		SET status = 'APPROVED', reviewer = ?, resolved_at = ?
		WHERE listing_id = ? AND status = 'PENDING'`,
		reviewer, now, listingID)
	if err != nil {
		return fmt.Errorf("approve: %w", err)
	}
	n, _ := res.RowsAffected()
	if n == 0 {
		// Check if it exists at all.
		var status string
		if scanErr := db.QueryRow(`SELECT status FROM review_queue WHERE listing_id = ?`, listingID).Scan(&status); scanErr == sql.ErrNoRows {
			return fmt.Errorf("listing %q not found in review queue", listingID)
		} else if scanErr == nil {
			return fmt.Errorf("listing %q has status %q — only PENDING items can be approved", listingID, status)
		}
		return fmt.Errorf("approve: no rows updated")
	}
	fmt.Printf("%s  %s approved by %s\n",
		styleApproved.Render("✓ APPROVED"), styleBold.Render(listingID), styleDim.Render(reviewer))
	return nil
}

// ── cardex review reject <id> --reason "..." ──────────────────────────────────

func newReviewRejectCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:     "reject <listing-id>",
		Short:   "Reject a pending review item",
		Args:    cobra.ExactArgs(1),
		Example: `  cardex review reject 01ARZ3NDEKTSV4RRFFQ69G5FAV --reason "VIN mismatch confirmed"`,
		RunE: func(_ *cobra.Command, args []string) error {
			if strings.TrimSpace(flagRejectReason) == "" {
				return fmt.Errorf("--reason is required for rejection")
			}
			db, err := openDB(flagDBPath)
			if err != nil {
				return err
			}
			defer db.Close()
			if err := ensureReviewSchema(db); err != nil {
				return fmt.Errorf("review schema: %w", err)
			}
			return runReviewReject(db, args[0], flagRejectReason)
		},
	}
	cmd.Flags().StringVar(&flagRejectReason, "reason", "", "rejection reason (required)")
	_ = cmd.MarkFlagRequired("reason")
	return cmd
}

func runReviewReject(db *sql.DB, listingID, reason string) error {
	reviewer := currentUser()
	now := time.Now().UTC().Format(time.RFC3339)

	res, err := db.Exec(`
		UPDATE review_queue
		SET status = 'REJECTED', reviewer = ?, reject_reason = ?, resolved_at = ?
		WHERE listing_id = ? AND status = 'PENDING'`,
		reviewer, reason, now, listingID)
	if err != nil {
		return fmt.Errorf("reject: %w", err)
	}
	n, _ := res.RowsAffected()
	if n == 0 {
		var status string
		if scanErr := db.QueryRow(`SELECT status FROM review_queue WHERE listing_id = ?`, listingID).Scan(&status); scanErr == sql.ErrNoRows {
			return fmt.Errorf("listing %q not found in review queue", listingID)
		} else if scanErr == nil {
			return fmt.Errorf("listing %q has status %q — only PENDING items can be rejected", listingID, status)
		}
		return fmt.Errorf("reject: no rows updated")
	}
	fmt.Printf("%s  %s rejected by %s\n       reason: %s\n",
		styleRejected.Render("✗ REJECTED"), styleBold.Render(listingID),
		styleDim.Render(reviewer), styleDim.Render(reason))
	return nil
}

// ── Helpers ───────────────────────────────────────────────────────────────────

// renderStatus returns a coloured status string.
func renderStatus(status string) string {
	switch strings.ToUpper(status) {
	case "PENDING":
		return stylePending.Render("PENDING")
	case "APPROVED":
		return styleApproved.Render("APPROVED")
	case "REJECTED":
		return styleRejected.Render("REJECTED")
	default:
		return styleDim.Render(status)
	}
}

// currentUser returns the OS user name, falling back to "unknown".
func currentUser() string {
	if u, err := user.Current(); err == nil && u.Username != "" {
		return u.Username
	}
	return "unknown"
}
