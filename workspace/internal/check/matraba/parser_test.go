package matraba

import (
	"archive/zip"
	"bytes"
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// latin1Encode is the inverse of latin1Decoder.decode — every rune whose
// codepoint fits in a byte maps to that byte. Used by tests to assemble
// Latin-1 payloads containing accented characters (ñ, é, á).
func latin1Encode(s string) []byte {
	b := make([]byte, 0, len(s))
	for _, r := range s {
		if r <= 0xFF {
			b = append(b, byte(r))
		}
	}
	return b
}

func TestLatin1Decoder(t *testing.T) {
	input := []byte{0x41, 0xE9, 0xF1, 0xFC} // "Aéñü" in ISO-8859-1
	var d latin1Decoder
	got := d.decode(input)
	want := "Aéñü"
	if got != want {
		t.Errorf("decode = %q, want %q", got, want)
	}
}

func TestParseStreamMixedGoodAndBadRows(t *testing.T) {
	row1, _ := fullSampleRow(t)
	row2 := buildRow(t, map[int]string{
		7: "VF1AAAAAAAA123456",
		8: "40",
	})

	payload := []byte{}
	payload = append(payload, []byte(row1)...)
	payload = append(payload, '\n')
	payload = append(payload, []byte("oops too short")...)
	payload = append(payload, '\n')
	payload = append(payload, []byte(row2)...)
	payload = append(payload, '\n')

	var got []Record
	stats, err := ParseStream(context.Background(), bytes.NewReader(payload), func(r Record) error {
		got = append(got, r)
		return nil
	})
	if err != nil {
		t.Fatalf("parse stream: %v", err)
	}
	if stats.LinesParsed != 2 {
		t.Errorf("LinesParsed = %d, want 2", stats.LinesParsed)
	}
	if stats.LinesShort != 1 {
		t.Errorf("LinesShort = %d, want 1", stats.LinesShort)
	}
	if len(got) != 2 {
		t.Fatalf("callback invocations = %d, want 2", len(got))
	}
	if got[0].Bastidor != "WVGZZZ5NZAW021819" || got[1].Bastidor != "VF1AAAAAAAA123456" {
		t.Errorf("unexpected VINs: %q, %q", got[0].Bastidor, got[1].Bastidor)
	}
}

func TestParseStreamLatin1Accents(t *testing.T) {
	// Assemble a row where field 31 (MUNICIPIO) contains an accented name,
	// encoded in Latin-1. The decoder should lift it to UTF-8 cleanly.
	row := buildRow(t, map[int]string{
		7:  "VF1BBBBBBBB123456",
		31: "CÁDIZ", // Spanish province capital with accent
	})
	payload := latin1Encode(row + "\n")

	var rec Record
	_, err := ParseStream(context.Background(), bytes.NewReader(payload), func(r Record) error {
		rec = r
		return nil
	})
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	if rec.Municipio != "CÁDIZ" {
		t.Errorf("Municipio = %q, want CÁDIZ (Latin-1 decode broken)", rec.Municipio)
	}
}

func TestParseStreamStripsUTF8BOM(t *testing.T) {
	row, _ := fullSampleRow(t)
	payload := append([]byte("\xef\xbb\xbf"), []byte(row)...)
	payload = append(payload, '\n')

	var seen int
	_, err := ParseStream(context.Background(), bytes.NewReader(payload), func(r Record) error {
		seen++
		if r.Bastidor != "WVGZZZ5NZAW021819" {
			t.Errorf("BOM leaked into first field: VIN = %q", r.Bastidor)
		}
		return nil
	})
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	if seen != 1 {
		t.Errorf("callback fired %d times, want 1", seen)
	}
}

func TestParseStreamRespectsContextCancellation(t *testing.T) {
	row, _ := fullSampleRow(t)
	// Emit 9000 rows so we cross the 8192-boundary cancellation check.
	var buf bytes.Buffer
	for i := 0; i < 9000; i++ {
		buf.WriteString(row)
		buf.WriteByte('\n')
	}
	ctx, cancel := context.WithCancel(context.Background())
	var parsed int
	_, err := ParseStream(ctx, &buf, func(r Record) error {
		parsed++
		if parsed == 100 {
			cancel()
		}
		return nil
	})
	if err == nil {
		t.Errorf("expected context cancellation error after 100 rows + 8k more, got nil")
	}
}

func TestParseZIP(t *testing.T) {
	row, _ := fullSampleRow(t)

	// Build a minimal DGT-style ZIP with one .txt member and a skipped
	// readme.txt — verifies the filter logic.
	dir := t.TempDir()
	zipPath := filepath.Join(dir, "export_mensual_mat_202412.zip")
	f, err := os.Create(zipPath)
	if err != nil {
		t.Fatalf("create zip: %v", err)
	}
	zw := zip.NewWriter(f)

	mw, err := zw.Create("export_mensual_mat_202412.txt")
	if err != nil {
		t.Fatalf("zip create member: %v", err)
	}
	mw.Write([]byte(row))
	mw.Write([]byte{'\n'})
	mw.Write([]byte(row))
	mw.Write([]byte{'\n'})

	// Filtered out — readme member.
	rw, _ := zw.Create("README.txt")
	rw.Write([]byte("This file describes the layout of the export."))

	if err := zw.Close(); err != nil {
		t.Fatalf("close zip writer: %v", err)
	}
	f.Close()

	var count int
	stats, err := ParseZIP(context.Background(), zipPath, func(r Record) error {
		count++
		return nil
	})
	if err != nil {
		t.Fatalf("ParseZIP: %v", err)
	}
	if count != 2 {
		t.Errorf("records parsed = %d, want 2", count)
	}
	if stats.LinesParsed != 2 {
		t.Errorf("stats.LinesParsed = %d, want 2", stats.LinesParsed)
	}
}

func TestParseZIPHandlesWindowsLineEndings(t *testing.T) {
	row, _ := fullSampleRow(t)
	dir := t.TempDir()
	zipPath := filepath.Join(dir, "win.zip")
	f, _ := os.Create(zipPath)
	zw := zip.NewWriter(f)
	mw, _ := zw.Create("win.txt")
	mw.Write([]byte(row))
	mw.Write([]byte("\r\n"))
	zw.Close()
	f.Close()

	var got Record
	_, err := ParseZIP(context.Background(), zipPath, func(r Record) error {
		got = r
		return nil
	})
	if err != nil {
		t.Fatalf("ParseZIP: %v", err)
	}
	if got.Bastidor != "WVGZZZ5NZAW021819" {
		t.Errorf("CRLF should not break VIN offset: got %q", got.Bastidor)
	}
}

// Sanity: field index exactly 70 (out of range) returns "" rather than
// panicking — important because parsers downstream treat empty as a
// normal "missing column" signal.
func TestFieldOutOfRange(t *testing.T) {
	if got := field(strings.Repeat(" ", RecordLength), 70); got != "" {
		t.Errorf("out-of-range field() = %q, want empty", got)
	}
}
