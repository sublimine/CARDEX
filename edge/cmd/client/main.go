package main

import (
	"context"
	"crypto/tls"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"

	"github.com/quic-go/quic-go/http3"
	"github.com/redis/go-redis/v9"
)

func main() {
	rdb := redis.NewClient(&redis.Options{Addr: "127.0.0.1:6379"})

	quoteID, err := rdb.HGet(context.Background(), "vehicle_state:GOLF_GTI_123", "quote_id").Result()
	if err != nil {
		log.Fatalf("[FALLO] No se encontró el QuoteID en Redis. ¿Está la Fase 6 activa?: %v", err)
	}

	fmt.Printf("[CLIENTE] QuoteID extraído: %s\n", quoteID)

	client := &http.Client{
		Transport: &http3.Transport{
			TLSClientConfig: &tls.Config{InsecureSkipVerify: true},
		},
	}

	url := fmt.Sprintf("https://localhost:8443/reserve?vin=GOLF_GTI_123&buyer_id=DEALER_ALFA&quote_id=%s", quoteID)
	fmt.Printf("[CLIENTE] Disparando reserva QUIC hacia: %s\n", url)

	resp, err := client.Get(url)
	if err != nil {
		log.Fatalf("[FALLO] Error de red QUIC: %v", err)
	}
	defer resp.Body.Close()

	body, _ := io.ReadAll(resp.Body)

	if resp.StatusCode == 200 {
		fmt.Printf("\n[ÉXITO] Status: %s | Payload: %s\n", resp.Status, string(body))
		fmt.Println("[SISTEMA] Monopolio de 120s concedido. Operador anclado.")
	} else {
		fmt.Printf("\n[RECHAZO] Status: %s | Payload: %s\n", resp.Status, string(body))
		os.Exit(1)
	}
}
