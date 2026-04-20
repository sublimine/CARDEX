// Command matraba-import downloads, parses, and indexes the Spanish DGT
// MATRABA microdata feed into the workspace SQLite database.
//
// Usage:
//
//	# Import a single month
//	matraba-import -db data/workspace.db -year 2024 -month 12
//
//	# Import a range (inclusive)
//	matraba-import -db data/workspace.db -from 2024-01 -to 2024-12
//
//	# Import all three datasets for a month
//	matraba-import -db data/workspace.db -year 2024 -month 12 -all
//
//	# Import only transfer dumps
//	matraba-import -db data/workspace.db -year 2024 -month 12 -dataset transfe
//
// The downloader caches ZIPs under ./data/matraba-zips/ by default; re-
// running is idempotent — already-downloaded ZIPs are not re-fetched and
// already-indexed VINs are upserted.
package main

import (
	"context"
	"database/sql"
	"errors"
	"flag"
	"fmt"
	"log"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	_ "modernc.org/sqlite"

	"cardex.eu/workspace/internal/check/matraba"
)

func main() {
	var (
		dbPath    = flag.String("db", envOrDefault("WORKSPACE_DB_PATH", "data/workspace.db"), "SQLite database path")
		zipsDir   = flag.String("zips", envOrDefault("MATRABA_ZIPS_DIR", "data/matraba-zips"), "directory for cached ZIP files")
		year      = flag.Int("year", 0, "year to import (single-month mode)")
		month     = flag.Int("month", 0, "month to import (single-month mode, 1-12)")
		from      = flag.String("from", "", "start YYYY-MM (range mode)")
		to        = flag.String("to", "", "end YYYY-MM (range mode, inclusive)")
		dataset   = flag.String("dataset", "matraba", "dataset: matraba | transfe | bajas")
		all       = flag.Bool("all", false, "import all three datasets (overrides -dataset)")
		skipEmpty = flag.Bool("skip-missing", true, "treat 404 (not-yet-published) as warning, not error")
		showOnly  = flag.Bool("dry-run", false, "print URLs without downloading")
	)
	flag.Parse()

	months, err := resolveMonths(*year, *month, *from, *to)
	if err != nil {
		log.Fatalf("invalid -year/-month/-from/-to: %v", err)
	}
	if len(months) == 0 {
		log.Fatalf("no months selected — pass -year/-month or -from/-to")
	}

	datasets, err := resolveDatasets(*dataset, *all)
	if err != nil {
		log.Fatalf("invalid -dataset: %v", err)
	}

	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer cancel()

	if *showOnly {
		dl := matraba.NewDownloader()
		for _, m := range months {
			for _, ds := range datasets {
				fmt.Println(dl.URLFor(ds, m.year, m.month))
			}
		}
		return
	}

	db, err := sql.Open("sqlite", *dbPath)
	if err != nil {
		log.Fatalf("open db: %v", err)
	}
	defer db.Close()

	// PRAGMAs tuned for bulk write: WAL + NORMAL sync gets us ~5x on
	// cold-start imports without sacrificing crash safety between imports.
	for _, pragma := range []string{
		"PRAGMA journal_mode=WAL",
		"PRAGMA synchronous=NORMAL",
		"PRAGMA temp_store=MEMORY",
		"PRAGMA cache_size=-64000", // 64 MB page cache
	} {
		if _, err := db.Exec(pragma); err != nil {
			log.Printf("warn: %s: %v", pragma, err)
		}
	}

	if err := matraba.EnsureSchema(db); err != nil {
		log.Fatalf("ensure schema: %v", err)
	}

	store := matraba.NewStore(db)
	dl := matraba.NewDownloader()

	var totalRows, totalMasked int64
	startAll := time.Now()

	for _, m := range months {
		for _, ds := range datasets {
			ym := fmt.Sprintf("%04d-%02d", m.year, m.month)
			url := dl.URLFor(ds, m.year, m.month)
			log.Printf("==> %s %s — %s", ds, ym, url)

			started := time.Now()
			zipPath, err := dl.Download(ctx, ds, m.year, m.month, *zipsDir)
			if err != nil {
				if errors.Is(err, matraba.ErrNotYetPublished) && *skipEmpty {
					log.Printf("   skipped (not yet published)")
					_ = store.RecordImport(ctx, url, "", string(ds), ym, 0, 0, 0, err)
					continue
				}
				log.Fatalf("download: %v", err)
			}

			// Pipe records from parser → channel → store.ImportTx.
			feed := make(chan matraba.Record, 1024)
			errCh := make(chan error, 1)
			var writtenRows, maskedRows int64

			go func() {
				stats, err := store.ImportTx(ctx, feed)
				writtenRows = stats.RowsWritten
				maskedRows = stats.RowsMasked
				errCh <- err
			}()

			parseStats, parseErr := matraba.ParseZIP(ctx, zipPath, func(r matraba.Record) error {
				select {
				case feed <- r:
					return nil
				case <-ctx.Done():
					return ctx.Err()
				}
			})
			close(feed)
			storeErr := <-errCh

			if parseErr != nil {
				_ = store.RecordImport(ctx, url, zipPath, string(ds), ym,
					parseStats.LinesTotal, parseStats.LinesParsed, maskedRows, parseErr)
				log.Fatalf("parse: %v", parseErr)
			}
			if storeErr != nil {
				_ = store.RecordImport(ctx, url, zipPath, string(ds), ym,
					parseStats.LinesTotal, parseStats.LinesParsed, maskedRows, storeErr)
				log.Fatalf("store: %v", storeErr)
			}

			_ = store.RecordImport(ctx, url, zipPath, string(ds), ym,
				parseStats.LinesTotal, parseStats.LinesParsed, maskedRows, nil)

			totalRows += writtenRows
			totalMasked += maskedRows

			log.Printf("   done: %d rows parsed, %d written, %d masked (%.1fs)",
				parseStats.LinesParsed, writtenRows, maskedRows,
				time.Since(started).Seconds())
		}
	}

	n, _ := store.Count(ctx)
	log.Printf("✓ import complete: +%d rows (%d masked) in %.1fs — index now holds %d vehicles",
		totalRows, totalMasked, time.Since(startAll).Seconds(), n)
}

type yearMonth struct{ year, month int }

func resolveMonths(y, m int, from, to string) ([]yearMonth, error) {
	if from != "" || to != "" {
		if from == "" || to == "" {
			return nil, fmt.Errorf("-from and -to must both be set")
		}
		f, err := time.Parse("2006-01", from)
		if err != nil {
			return nil, fmt.Errorf("-from: %w", err)
		}
		t, err := time.Parse("2006-01", to)
		if err != nil {
			return nil, fmt.Errorf("-to: %w", err)
		}
		if t.Before(f) {
			return nil, fmt.Errorf("-to before -from")
		}
		var out []yearMonth
		for d := f; !d.After(t); d = d.AddDate(0, 1, 0) {
			out = append(out, yearMonth{d.Year(), int(d.Month())})
		}
		return out, nil
	}
	if y > 0 && m > 0 {
		if m < 1 || m > 12 {
			return nil, fmt.Errorf("month %d out of range", m)
		}
		return []yearMonth{{y, m}}, nil
	}
	return nil, nil
}

func resolveDatasets(s string, all bool) ([]matraba.Dataset, error) {
	if all {
		return []matraba.Dataset{matraba.DatasetMatraba, matraba.DatasetTransfe, matraba.DatasetBajas}, nil
	}
	switch strings.ToLower(strings.TrimSpace(s)) {
	case "matraba", "mat":
		return []matraba.Dataset{matraba.DatasetMatraba}, nil
	case "transfe", "tra":
		return []matraba.Dataset{matraba.DatasetTransfe}, nil
	case "bajas", "baj":
		return []matraba.Dataset{matraba.DatasetBajas}, nil
	}
	return nil, fmt.Errorf("unknown dataset %q (want matraba|transfe|bajas)", s)
}

func envOrDefault(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}
