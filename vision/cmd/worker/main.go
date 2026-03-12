package main

import (
	"context"
	"fmt"
	"image"
	_ "image/jpeg"
	_ "image/png"
	"log"
	"net/http"
	"time"

	"github.com/corona10/goimagehash"
	"github.com/redis/go-redis/v9"
)

var rdb *redis.Client
var ctx = context.Background()

func init() {
	rdb = redis.NewClient(&redis.Options{
		Addr:     "127.0.0.1:6379",
		PoolSize: 100,
	})
}

// downloadAndHash descarga la imagen evadiendo filtros de bot y calcula su pHash
func downloadAndHash(imageURL string) (uint64, error) {
	client := &http.Client{Timeout: 5 * time.Second}

	req, err := http.NewRequest("GET", imageURL, nil)
	if err != nil {
		return 0, err
	}

	// Evasión estandarizada de WAF/CDN
	req.Header.Set("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36")

	resp, err := client.Do(req)
	if err != nil {
		return 0, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		return 0, fmt.Errorf("HTTP %d", resp.StatusCode)
	}

	img, _, err := image.Decode(resp.Body)
	if err != nil {
		return 0, err
	}

	hash, err := goimagehash.PerceptionHash(img)
	if err != nil {
		return 0, err
	}

	return hash.GetHash(), nil
}

// deduplicate evalúa si el pHash ya existe en la base de datos vectorial
func deduplicate(vin string, phash uint64) {
	hashKey := fmt.Sprintf("%d", phash)

	isNew, err := rdb.HSetNX(ctx, "vision:phash_registry", hashKey, vin).Result()
	if err != nil {
		log.Printf("[VISION] Error Redis: %v", err)
		return
	}

	if isNew {
		log.Printf("[VISION] 🟢 NUEVO ACTIVO | VIN: %s | pHash: %x", vin, phash)
	} else {
		existingVIN, _ := rdb.HGet(ctx, "vision:phash_registry", hashKey).Result()
		log.Printf("[VISION] ⚠️ DUPLICADO DETECTADO | El VIN %s es visualmente idéntico al VIN %s", vin, existingVIN)
	}
}

func main() {
	log.Println("[V1.3] Motor de Visión Computacional (pHash) en línea. Target: GitHub Avatars.")

	testCases := []struct {
		VIN string
		URL string
	}{
		// Avatar estático de GitHub. Garantía de disponibilidad y sin Rate Limit estricto.
		{"TEST_VIN_001", "https://avatars.githubusercontent.com/u/9919?s=200&v=4"},
		{"TEST_VIN_002", "https://avatars.githubusercontent.com/u/9919?s=200&v=4"},
	}

	for _, tc := range testCases {
		log.Printf("[VISION] Descargando y analizando: %s", tc.VIN)

		phash, err := downloadAndHash(tc.URL)
		if err != nil {
			log.Printf("[VISION] ❌ Error procesando %s: %v", tc.VIN, err)
			continue
		}

		deduplicate(tc.VIN, phash)
		time.Sleep(1 * time.Second)
	}

	log.Println("[VISION] Bucle de prueba finalizado. Esperando eventos...")
	select {}
}
