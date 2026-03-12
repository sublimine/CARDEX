package main

import (
	"compress/gzip"
	"context"
	"encoding/xml"
	"io"
	"log/slog"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/redis/go-redis/v9"
)

var ctx = context.Background()

type SitemapIndex struct {
	Sitemaps []struct {
		Loc string `xml:"loc"`
	} `xml:"sitemap"`
}

type UrlSet struct {
	Urls []struct {
		Loc string `xml:"loc"`
	} `xml:"url"`
}

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	slog.SetDefault(logger)

	redisAddr := os.Getenv("REDIS_ADDR")
	if redisAddr == "" {
		redisAddr = "127.0.0.1:6379"
	}

	targetIndex := os.Getenv("SITEMAP_INDEX_URL")
	if targetIndex == "" {
		targetIndex = "https://www.tu-objetivo.com/sitemap.xml"
	}

	slog.Info("iniciando cartógrafo seo", "target", targetIndex, "redis", redisAddr)

	rdb := redis.NewClient(&redis.Options{Addr: redisAddr})
	if err := rdb.Ping(ctx).Err(); err != nil {
		slog.Error("fallo crítico de conexión a redis", "error", err)
		os.Exit(1)
	}

	req, err := http.NewRequestWithContext(ctx, "GET", targetIndex, nil)
	if err != nil {
		slog.Error("fallo creando request", "error", err)
		os.Exit(1)
	}
	req.Header.Set("User-Agent", "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		slog.Error("fallo descargando índice de sitemaps", "error", err)
		os.Exit(1)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		slog.Error("fallo descargando índice de sitemaps", "status", resp.StatusCode)
		os.Exit(1)
	}

	var index SitemapIndex
	if err := xml.NewDecoder(resp.Body).Decode(&index); err != nil {
		slog.Error("fallo parseando xml del índice", "error", err)
		os.Exit(1)
	}

	slog.Info("índice interceptado", "total_sitemaps", len(index.Sitemaps))

	totalExtracted := 0
	for _, sm := range index.Sitemaps {
		loc := sm.Loc

		if !strings.Contains(loc, "vehicles") && !strings.Contains(loc, "details") {
			slog.Debug("sitemap descartado por filtro", "loc", loc)
			continue
		}

		urls := extractURLs(loc)
		if len(urls) == 0 {
			continue
		}

		pipe := rdb.Pipeline()
		for _, u := range urls {
			pipe.RPush(ctx, "queue:url_tasks", u)
		}
		if _, err := pipe.Exec(ctx); err != nil {
			slog.Error("fallo inyectando urls en redis", "loc", loc, "error", err)
			continue
		}

		totalExtracted += len(urls)
		slog.Info("segmento volcado", "urls", len(urls), "loc", loc)

		select {
		case <-time.After(500 * time.Millisecond):
		}
	}

	slog.Info("bóveda saturada", "total_urls", totalExtracted)
}

func extractURLs(sitemapURL string) []string {
	req, err := http.NewRequestWithContext(ctx, "GET", sitemapURL, nil)
	if err != nil {
		slog.Warn("fallo creando request", "url", sitemapURL, "error", err)
		return nil
	}
	req.Header.Set("User-Agent", "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		slog.Warn("fallo descargando sitemap", "url", sitemapURL, "error", err)
		return nil
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		slog.Warn("sitemap rechazado", "url", sitemapURL, "status", resp.StatusCode)
		return nil
	}

	var reader io.Reader = resp.Body
	if strings.HasSuffix(strings.ToLower(sitemapURL), ".gz") || strings.Contains(resp.Header.Get("Content-Encoding"), "gzip") {
		gzReader, err := gzip.NewReader(resp.Body)
		if err != nil {
			slog.Warn("fallo descomprimiendo gzip", "url", sitemapURL, "error", err)
			return nil
		}
		defer gzReader.Close()
		reader = gzReader
	}

	var urlSet UrlSet
	if err := xml.NewDecoder(reader).Decode(&urlSet); err != nil {
		slog.Warn("fallo parseando xml", "url", sitemapURL, "error", err)
		return nil
	}

	var extracted []string
	for _, u := range urlSet.Urls {
		if u.Loc != "" {
			extracted = append(extracted, u.Loc)
		}
	}
	return extracted
}
