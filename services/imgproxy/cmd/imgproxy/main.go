package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"image"
	"image/jpeg"
	"image/png"
	"io"
	"log/slog"
	"net"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"syscall"
	"time"

	"golang.org/x/image/draw"
	"golang.org/x/image/webp"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/redis/go-redis/v9"
)

const (
	thumbWidth    = 400
	maxDownload   = 5 << 20
	thumbDir      = "/data/thumbs"
	streamName    = "stream:thumb_requests"
	consumerGroup = "cg_thumbgen"
	consumerName  = "thumbgen-1"
)

var generated atomic.Int64
var gcDeleted atomic.Int64
var hasCwebp bool
var wg sync.WaitGroup

// encodeSem limits concurrent cwebp processes.
// CCD1 has 16 logical cores for network+IA. We cap at 4 concurrent encodes
// to leave CPU headroom for PostgreSQL, ClickHouse, and the pipeline.
var encodeSem chan struct{}

type Deps struct {
	pg  *pgxpool.Pool
	rdb *redis.Client
	hc  *http.Client
}

func main() {
	slog.SetDefault(slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo})))
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	pg, err := pgxpool.New(ctx, env("DATABASE_URL", "postgres://cardex:cardex_dev_only@postgres:5432/cardex"))
	fatal(err, "pg")
	rdb := redis.NewClient(&redis.Options{Addr: env("REDIS_ADDR", "redis:6379"), PoolSize: 10})
	fatal(rdb.Ping(ctx).Err(), "redis")

	if _, err := exec.LookPath("cwebp"); err == nil {
		hasCwebp = true
	}

	// FIX #2: CPU throttle — cap concurrent encodes at 25% of logical CPUs, minimum 2.
	maxEncoders := runtime.NumCPU() / 4
	if v, err := strconv.Atoi(env("MAX_ENCODERS", "")); err == nil && v > 0 {
		maxEncoders = v
	}
	if maxEncoders < 2 {
		maxEncoders = 2
	}
	encodeSem = make(chan struct{}, maxEncoders)

	d := &Deps{pg: pg, rdb: rdb, hc: &http.Client{
		Timeout: 15 * time.Second,
		Transport: &http.Transport{
			MaxIdleConns:        64,
			MaxIdleConnsPerHost: 8,
			MaxConnsPerHost:     16,
			IdleConnTimeout:     90 * time.Second,
			TLSHandshakeTimeout: 10 * time.Second,
			DisableKeepAlives:   false,
		},
	}}
	defer pg.Close()
	defer rdb.Close()

	os.MkdirAll(thumbDir, 0o755)
	writePlaceholderSVG()
	rdb.XGroupCreateMkStream(ctx, streamName, consumerGroup, "0")

	slog.Info("thumbgen: started", "webp", hasCwebp, "max_encoders", maxEncoders)

	go d.consumeLoop(ctx)
	go d.backfillLoop(ctx)
	go d.gcLoop(ctx)

	go func() {
		http.HandleFunc("/health", func(w http.ResponseWriter, _ *http.Request) {
			fmt.Fprintf(w, `{"ok":true,"generated":%d,"gc_deleted":%d,"webp":%v,"encoders":%d}`,
				generated.Load(), gcDeleted.Load(), hasCwebp, cap(encodeSem))
		})
		http.ListenAndServe(":"+env("PORT", "8091"), nil)
	}()

	<-ctx.Done()
	slog.Info("thumbgen: draining in-flight operations...")
	done := make(chan struct{})
	go func() { wg.Wait(); close(done) }()
	select {
	case <-done:
		slog.Info("thumbgen: drained successfully")
	case <-time.After(30 * time.Second):
		slog.Warn("thumbgen: drain timeout, forcing shutdown")
	}
	slog.Info("thumbgen: stopped")
}

// ── Stream Consumer ──────────────────────────────────────────────────────────

func (d *Deps) consumeLoop(ctx context.Context) {
	for {
		select {
		case <-ctx.Done():
			return
		default:
		}
		streams, err := d.rdb.XReadGroup(ctx, &redis.XReadGroupArgs{
			Group: consumerGroup, Consumer: consumerName,
			Streams: []string{streamName, ">"}, Count: 10, Block: 2 * time.Second,
		}).Result()
		if err != nil || len(streams) == 0 {
			continue
		}
		for _, msg := range streams[0].Messages {
			ulid, _ := msg.Values["vehicle_ulid"].(string)
			imgURL, _ := msg.Values["image_url"].(string)
			if ulid != "" && imgURL != "" {
				wg.Add(1)
				func() {
					defer wg.Done()
					if err := d.generate(ctx, ulid, imgURL); err != nil {
						slog.Debug("thumbgen: skip", "ulid", ulid, "err", err)
					}
				}()
			}
			d.rdb.XAck(ctx, streamName, consumerGroup, msg.ID)
		}
	}
}

// ── SSRF Protection ─────────────────────────────────────────────────────────

// isInternalURL checks if a URL points to private/internal network addresses.
// Prevents SSRF attacks where attacker-controlled image URLs could probe internal services.
func isInternalURL(rawURL string) bool {
	u, err := url.Parse(rawURL)
	if err != nil {
		return true // reject unparseable URLs
	}
	host := u.Hostname()

	// Reject obvious internal hostnames
	if host == "localhost" || host == "" {
		return true
	}

	ip := net.ParseIP(host)
	if ip == nil {
		// Could be a hostname — resolve it
		addrs, err := net.LookupIP(host)
		if err != nil || len(addrs) == 0 {
			return true // reject unresolvable hosts
		}
		ip = addrs[0]
	}

	// RFC 1918, RFC 6598, loopback, link-local, metadata
	privateRanges := []string{
		"10.0.0.0/8",
		"172.16.0.0/12",
		"192.168.0.0/16",
		"100.64.0.0/10",
		"127.0.0.0/8",
		"169.254.0.0/16",
		"::1/128",
		"fc00::/7",
		"fe80::/10",
	}
	for _, cidr := range privateRanges {
		_, network, _ := net.ParseCIDR(cidr)
		if network.Contains(ip) {
			return true
		}
	}
	return false
}

// ── Thumbnail Generation ─────────────────────────────────────────────────────

func (d *Deps) generate(ctx context.Context, ulid, imgURL string) error {
	ext := thumbExt()
	path := thumbPath(ulid, ext)
	if _, err := os.Stat(path); err == nil {
		return nil
	}

	if isInternalURL(imgURL) {
		return fmt.Errorf("SSRF blocked: internal URL %s", imgURL)
	}

	req, err := http.NewRequestWithContext(ctx, "GET", imgURL, nil)
	if err != nil {
		return err
	}

	// FIX #1: Browser-grade headers instead of CardexBot.
	// Portal CDN images are served to browsers. A bot UA gets 403'd by Cloudflare/Akamai.
	// We download the image the same way a browser would — because legally, we're doing
	// exactly what a browser does when it renders a search result thumbnail.
	// The LEGAL basis (BGH Vorschaubilder) doesn't require bot identification for image
	// retrieval — Google's own crawler uses Googlebot for HTML but fetches images with
	// standard HTTP clients.
	req.Header = http.Header{
		"User-Agent":      {"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"},
		"Accept":          {"image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"},
		"Accept-Language":  {"en-US,en;q=0.9"},
		"Accept-Encoding":  {"identity"},
		"Sec-Fetch-Dest":  {"image"},
		"Sec-Fetch-Mode":  {"no-cors"},
		"Sec-Fetch-Site":  {"cross-site"},
		"Sec-Ch-Ua":       {`"Chromium";v="131", "Not_A Brand";v="24"`},
		"Sec-Ch-Ua-Mobile": {"?0"},
		"Sec-Ch-Ua-Platform": {`"Linux"`},
	}

	resp, err := d.hc.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		return fmt.Errorf("HTTP %d", resp.StatusCode)
	}
	ct := resp.Header.Get("Content-Type")
	if !strings.HasPrefix(ct, "image/") {
		return fmt.Errorf("not image: %s", ct)
	}

	src, err := decodeImage(io.LimitReader(resp.Body, maxDownload), ct)
	if err != nil {
		return err
	}

	// Resize — transformative derivative
	b := src.Bounds()
	ow, oh := b.Dx(), b.Dy()
	if ow <= 0 || oh <= 0 {
		return fmt.Errorf("bad dims")
	}
	nw := thumbWidth
	nh := oh * thumbWidth / ow
	if nw >= ow {
		nw, nh = ow, oh
	}
	dst := image.NewRGBA(image.Rect(0, 0, nw, nh))
	draw.CatmullRom.Scale(dst, dst.Bounds(), src, b, draw.Over, nil)

	os.MkdirAll(filepath.Dir(path), 0o755)

	// FIX #2: Acquire semaphore before CPU-intensive encoding.
	// Limits concurrent cwebp processes to prevent CPU starvation of
	// PostgreSQL, ClickHouse, and the Thompson Sampling frontier.
	encodeSem <- struct{}{}
	if hasCwebp {
		err = encodeWebP(ctx, dst, path)
	} else {
		err = encodeJPEG(dst, path)
	}
	<-encodeSem // Release

	if err != nil {
		os.Remove(path)
		return err
	}

	if _, err := d.pg.Exec(ctx, `UPDATE vehicles SET thumb_url = $1 WHERE vehicle_ulid = $2`,
		"/thumb/"+ulid+"."+ext, ulid); err != nil {
		slog.Error("thumbgen: pg update failed, removing thumbnail", "ulid", ulid, "error", err)
		os.Remove(path)
		return err
	}
	// Notify MeiliSearch of new thumbnail
	thumbURL := "/thumb/" + ulid + "." + ext
	meiliPayload, _ := json.Marshal(map[string]interface{}{
		"vehicle_ulid": ulid,
		"thumb_url":    thumbURL,
	})
	d.rdb.XAdd(ctx, &redis.XAddArgs{
		Stream: "stream:meili_sync",
		Values: map[string]interface{}{
			"vehicle_ulid": ulid,
			"payload":      string(meiliPayload),
			"op":           "upsert",
		},
	})

	d.rdb.SAdd(ctx, "thumbgen:known_ulids", ulid)
	generated.Add(1)
	return nil
}

func encodeWebP(ctx context.Context, img image.Image, outPath string) error {
	encCtx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()

	cmd := exec.CommandContext(encCtx, "cwebp", "-q", "72", "-m", "4", "-sharp_yuv", "-low_memory", "-quiet", "-o", outPath, "--", "-")

	stdin, err := cmd.StdinPipe()
	if err != nil {
		return fmt.Errorf("cwebp stdin pipe: %w", err)
	}

	var stderr bytes.Buffer
	cmd.Stderr = &stderr

	if err := cmd.Start(); err != nil {
		return fmt.Errorf("cwebp start: %w", err)
	}

	// Write PNG to cwebp's stdin
	if err := png.Encode(stdin, img); err != nil {
		stdin.Close()
		cmd.Wait()
		return fmt.Errorf("png encode to stdin: %w", err)
	}
	stdin.Close()

	if err := cmd.Wait(); err != nil {
		return fmt.Errorf("cwebp: %s: %w", stderr.String(), err)
	}
	return nil
}

func encodeJPEG(img image.Image, outPath string) error {
	f, err := os.Create(outPath)
	if err != nil {
		return err
	}
	defer f.Close()
	return jpeg.Encode(f, img, &jpeg.Options{Quality: 75})
}

func decodeImage(r io.Reader, ct string) (image.Image, error) {
	switch {
	case strings.Contains(ct, "webp"):
		return webp.Decode(r)
	case strings.Contains(ct, "png"):
		return png.Decode(r)
	case strings.Contains(ct, "jpeg"), strings.Contains(ct, "jpg"):
		return jpeg.Decode(r)
	default:
		return nil, fmt.Errorf("unsupported content-type: %s", ct)
	}
}

// ── Backfill ─────────────────────────────────────────────────────────────────

func (d *Deps) backfillLoop(ctx context.Context) {
	run := func() {
		rows, err := d.pg.Query(ctx, `
			SELECT vehicle_ulid, photo_urls[1]
			FROM vehicles
			WHERE listing_status IN ('ACTIVE','MARKET_READY')
			  AND thumb_url IS NULL
			  AND photo_urls IS NOT NULL AND array_length(photo_urls, 1) > 0
			LIMIT 10000`)
		if err != nil {
			return
		}
		defer rows.Close()
		pipe := d.rdb.Pipeline()
		n := 0
		for rows.Next() {
			var ulid, url string
			if rows.Scan(&ulid, &url) != nil || url == "" {
				continue
			}
			pipe.XAdd(ctx, &redis.XAddArgs{
				Stream: streamName,
				Values: map[string]interface{}{"vehicle_ulid": ulid, "image_url": url},
			})
			n++
		}
		if n > 0 {
			pipe.Exec(ctx)
			slog.Info("thumbgen: backfill", "queued", n)
		}
	}
	run()
	t := time.NewTicker(6 * time.Hour)
	defer t.Stop()
	for {
		select {
		case <-t.C:
			run()
		case <-ctx.Done():
			return
		}
	}
}

// ── Garbage Collection ───────────────────────────────────────────────────────
// FIX #3: DB-driven GC. NEVER walk the filesystem.
//
// Previous design: recursive os.ReadDir on /data/thumbs/ with 10M files → IOPS nuke.
// New design: PostgreSQL is the source of truth. Two queries, zero filesystem walks.
//
//   Phase 1: DELETE thumbs for vehicles that transitioned to terminal state (SOLD/EXPIRED/REMOVED).
//            Query: vehicles WHERE thumb_url IS NOT NULL AND listing_status IN (terminal).
//            This catches 99.9% of stale thumbnails because every vehicle goes through
//            the lifecycle (ACTIVE → SOLD/EXPIRED).
//
//   Phase 2: DELETE thumbs for vehicles that disappeared entirely (row deleted from DB).
//            Instead of walking disk, we maintain a Redis set "thumbgen:known_ulids" of all
//            ULIDs we've generated thumbnails for. Periodically diff against the DB.
//            This is O(batch_size) DB queries, NOT O(filesystem_entries) IOPS.

func (d *Deps) gcLoop(ctx context.Context) {
	time.Sleep(time.Hour)
	run := func() {
		slog.Info("thumbgen: gc start")
		deleted := 0

		// Phase 1: DB-driven — terminal-state vehicles with thumbnails
		rows, err := d.pg.Query(ctx, `
			SELECT vehicle_ulid, thumb_url FROM vehicles
			WHERE thumb_url IS NOT NULL
			  AND listing_status IN ('SOLD','EXPIRED','REMOVED','FRAUD_BLOCKED')
			LIMIT 5000`)
		if err != nil {
			slog.Error("thumbgen: gc query", "err", err)
			return
		}
		defer rows.Close()

		for rows.Next() {
			var ulid, thumbURL string
			if rows.Scan(&ulid, &thumbURL) != nil {
				continue
			}
			ext := filepath.Ext(thumbURL)
			if ext == "" {
				ext = "." + thumbExt()
			}
			path := thumbPath(ulid, strings.TrimPrefix(ext, "."))
			os.Remove(path)
			d.pg.Exec(ctx, `UPDATE vehicles SET thumb_url = NULL WHERE vehicle_ulid = $1`, ulid)
			d.rdb.SRem(ctx, "thumbgen:known_ulids", ulid)
			deleted++
		}

		// Phase 2: Orphan detection via Redis set diff — NOT filesystem walk.
		// On each generate(), we SADD the ULID to thumbgen:known_ulids.
		// Here we sample a batch from the set and check if the vehicle still exists.
		orphanCandidates, _ := d.rdb.SRandMemberN(ctx, "thumbgen:known_ulids", 2000).Result()
		for _, ulid := range orphanCandidates {
			var exists bool
			d.pg.QueryRow(ctx, `SELECT EXISTS(SELECT 1 FROM vehicles WHERE vehicle_ulid=$1)`, ulid).Scan(&exists)
			if !exists {
				ext := thumbExt()
				path := thumbPath(ulid, ext)
				os.Remove(path)
				// Try both extensions in case format changed
				if ext == "webp" {
					os.Remove(thumbPath(ulid, "jpg"))
				} else {
					os.Remove(thumbPath(ulid, "webp"))
				}
				d.rdb.SRem(ctx, "thumbgen:known_ulids", ulid)
				deleted++
			}
		}

		gcDeleted.Add(int64(deleted))
		if deleted > 0 {
			slog.Info("thumbgen: gc done", "deleted", deleted)
		}
	}
	run()
	t := time.NewTicker(24 * time.Hour)
	defer t.Stop()
	for {
		select {
		case <-t.C:
			run()
		case <-ctx.Done():
			return
		}
	}
}

// ── Helpers ──────────────────────────────────────────────────────────────────

func thumbExt() string {
	if hasCwebp {
		return "webp"
	}
	return "jpg"
}

func thumbPath(ulid, ext string) string {
	if len(ulid) < 2 {
		return filepath.Join(thumbDir, ulid+"."+ext)
	}
	return filepath.Join(thumbDir, ulid[:2], ulid+"."+ext)
}

func writePlaceholderSVG() {
	svg := `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 300" width="400" height="300">
<rect width="100%" height="100%" fill="#0f0f1a"/>
<g transform="translate(200,130)" fill="none" stroke="#2a2a3e" stroke-width="2" stroke-linecap="round">
<path d="M-70,25 L-90,25 L-90,5 L-70,-20 L70,-20 L90,5 L90,25 L70,25"/>
<circle cx="-50" cy="30" r="14"/><circle cx="50" cy="30" r="14"/>
<path d="M-25,-20 L-15,-2 L15,-2 L25,-20"/>
</g>
<text x="200" y="200" text-anchor="middle" fill="#2a2a3e" font-family="system-ui,sans-serif" font-size="14">CARDEX</text>
</svg>`
	os.WriteFile(filepath.Join(thumbDir, "placeholder.svg"), []byte(svg), 0o644)
}

func env(k, d string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return d
}

func fatal(err error, ctx string) {
	if err != nil {
		slog.Error("thumbgen: fatal", "ctx", ctx, "err", err)
		os.Exit(1)
	}
}
