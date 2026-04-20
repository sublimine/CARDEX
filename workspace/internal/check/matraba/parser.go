package matraba

import (
	"archive/zip"
	"bufio"
	"context"
	"fmt"
	"io"
	"os"
	"strings"
)

// latin1Decoder converts ISO-8859-1 bytes to UTF-8 on the fly. The mapping
// is the trivial identity for codepoints 0x00-0xFF: every byte b becomes
// the Unicode rune U+00bb. This avoids pulling in golang.org/x/text just
// to decode a single-byte encoding.
//
// We reuse a single []rune scratch buffer to keep allocation amortised
// across multi-million-row files.
type latin1Decoder struct {
	runes []rune
}

func (d *latin1Decoder) decode(b []byte) string {
	if cap(d.runes) < len(b) {
		d.runes = make([]rune, len(b))
	} else {
		d.runes = d.runes[:len(b)]
	}
	for i, c := range b {
		d.runes[i] = rune(c)
	}
	return string(d.runes)
}

// ParseCallback is invoked for each successfully parsed Record. Returning
// a non-nil error aborts the parse and propagates the error out of
// ParseStream / ParseZIP / ParseFile.
type ParseCallback func(Record) error

// ParseStats reports counters collected during a parse. Returned by each
// Parse* entry point so callers can surface import progress in logs and
// the admin CLI.
type ParseStats struct {
	LinesTotal     int64 // every line read (including skipped)
	LinesParsed    int64 // Parse() returned a Record
	LinesShort     int64 // <91 bytes — identity fields truncated
	LinesError     int64 // Parse() returned an error other than "too short"
	BytesProcessed int64 // uncompressed bytes read from the stream
}

// ParseStream decodes a Latin-1 fixed-width MATRABA stream from r and
// invokes fn for every row. The scanner buffer is sized for the 714-byte
// record layout plus generous headroom so pre-spec-revision historical
// files (which sometimes run shorter/longer) still parse.
//
// Respects ctx cancellation: the loop checks ctx.Err() every 8k rows so
// a stuck import can be interrupted without waiting for I/O.
func ParseStream(ctx context.Context, r io.Reader, fn ParseCallback) (ParseStats, error) {
	var stats ParseStats
	var dec latin1Decoder

	sc := bufio.NewScanner(r)
	// 64 KB default is more than enough for 714-char rows, but we bump it
	// anyway to cope with rare stray long lines (e.g. BOM-prefixed headers).
	sc.Buffer(make([]byte, 0, 8192), 64*1024)

	for sc.Scan() {
		stats.LinesTotal++
		raw := sc.Bytes()
		stats.BytesProcessed += int64(len(raw)) + 1 // +1 for the newline

		if len(raw) == 0 {
			continue
		}

		// Some DGT ZIPs ship a UTF-8 BOM on line 1 even though the payload
		// is Latin-1 — strip the raw 3 bytes before decoding so offsets
		// line up with the fixed-width spec from byte 0.
		if stats.LinesTotal == 1 && len(raw) >= 3 &&
			raw[0] == 0xEF && raw[1] == 0xBB && raw[2] == 0xBF {
			raw = raw[3:]
		}
		line := dec.decode(raw)

		rec, err := Parse(line)
		if err != nil {
			if strings.Contains(err.Error(), "line too short") {
				stats.LinesShort++
				continue
			}
			stats.LinesError++
			continue
		}
		stats.LinesParsed++

		if err := fn(rec); err != nil {
			return stats, err
		}

		// Cancellation check — cheap enough to do per row but we sample to
		// keep overhead negligible on multi-million-row imports.
		if stats.LinesTotal%8192 == 0 {
			if err := ctx.Err(); err != nil {
				return stats, err
			}
		}
	}

	if err := sc.Err(); err != nil {
		return stats, fmt.Errorf("matraba scan: %w", err)
	}
	return stats, nil
}

// ParseFile opens path and delegates to ParseStream. The file must contain
// a single fixed-width record per line in Latin-1 encoding.
func ParseFile(ctx context.Context, path string, fn ParseCallback) (ParseStats, error) {
	f, err := os.Open(path)
	if err != nil {
		return ParseStats{}, fmt.Errorf("matraba open %s: %w", path, err)
	}
	defer f.Close()
	return ParseStream(ctx, f, fn)
}

// ParseZIP opens a DGT MATRABA distribution ZIP and parses every contained
// text file (typically a single .txt member per monthly dump, sometimes a
// README or .txt per dataset). Non-text members are skipped silently.
//
// Stats are aggregated across all members.
func ParseZIP(ctx context.Context, path string, fn ParseCallback) (ParseStats, error) {
	zr, err := zip.OpenReader(path)
	if err != nil {
		return ParseStats{}, fmt.Errorf("matraba open zip %s: %w", path, err)
	}
	defer zr.Close()

	var total ParseStats
	for _, zf := range zr.File {
		name := strings.ToLower(zf.Name)
		// Skip anything that obviously isn't a fixed-width data file. Real
		// DGT zips ship only `.txt` members, but we've seen `readme.txt`
		// supplements occasionally — filter by member name + heuristic.
		if !strings.HasSuffix(name, ".txt") {
			continue
		}
		if strings.Contains(name, "readme") || strings.Contains(name, "leeme") {
			continue
		}

		rc, err := zf.Open()
		if err != nil {
			return total, fmt.Errorf("matraba read %s in %s: %w", zf.Name, path, err)
		}
		memberStats, err := ParseStream(ctx, rc, fn)
		rc.Close()
		total.LinesTotal += memberStats.LinesTotal
		total.LinesParsed += memberStats.LinesParsed
		total.LinesShort += memberStats.LinesShort
		total.LinesError += memberStats.LinesError
		total.BytesProcessed += memberStats.BytesProcessed
		if err != nil {
			return total, fmt.Errorf("matraba parse %s: %w", zf.Name, err)
		}
	}
	return total, nil
}
