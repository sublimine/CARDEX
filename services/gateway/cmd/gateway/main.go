package main

import (
	"context"
	"crypto/ed25519"
	"crypto/hmac"
	"crypto/sha256"
	"crypto/tls"
	"encoding/hex"
	"encoding/json"
	"io"
	"log"
	"net"
	"net/http"
	"os"
	"runtime"
	"time"

	"github.com/quic-go/quic-go"
	"github.com/redis/go-redis/v9"
)

var rdbCentral *redis.Client
var pubKey ed25519.PublicKey
var b2bHmacSecret []byte

type EdgePayload struct {
	Signature string `json:"sig"`
	Timestamp int64  `json:"ts"`
	Data      string `json:"data"`
}

func init() {
	// Fail-Closed: HMAC_SECRET obligatorio. Sin él, no arrancar.
	secret := os.Getenv("HMAC_SECRET")
	if secret == "" {
		log.Fatal("FATAL [FAIL-CLOSED]: HMAC_SECRET no detectado en el entorno. Abortando arranque.")
	}
	b2bHmacSecret = []byte(secret)

	redisAddr := os.Getenv("REDIS_ADDR")
	if redisAddr == "" {
		redisAddr = "127.0.0.1:6379"
	}

	pubHex := os.Getenv("EDGE_PUB_KEY_HEX")
	if pubHex != "" {
		pubBytes, err := hex.DecodeString(pubHex)
		if err == nil && len(pubBytes) == ed25519.PublicKeySize {
			pubKey = ed25519.PublicKey(pubBytes)
		}
	}

	rdbCentral = redis.NewClient(&redis.Options{Addr: redisAddr, PoolSize: 2000})

	// Fail-Closed: verificar conectividad Redis antes de continuar.
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := rdbCentral.Ping(ctx).Err(); err != nil {
		log.Fatalf("FATAL [FAIL-CLOSED]: Redis inalcanzable en %s: %v. Abortando arranque.", redisAddr, err)
	}
}

func handleB2BWebhook(w http.ResponseWriter, r *http.Request) {
	partnerID := r.Header.Get("X-Partner-ID")
	if partnerID == "" {
		http.Error(w, `{"error": "missing partner ID"}`, http.StatusBadRequest)
		return
	}

	body, err := io.ReadAll(r.Body)
	if err != nil {
		http.Error(w, "Bad Request", http.StatusBadRequest)
		return
	}
	defer r.Body.Close()

	// Validación HMAC-SHA256 enrutada: rechazar si firma inválida.
	signature := r.Header.Get("X-Cardex-Signature")
	if signature == "" {
		log.Printf("[SECURITY DROP] Firma HMAC ausente para Partner: %s", partnerID)
		http.Error(w, `{"error": "unauthorized"}`, http.StatusUnauthorized)
		return
	}
	mac := hmac.New(sha256.New, b2bHmacSecret)
	mac.Write(body)
	expectedMAC := hex.EncodeToString(mac.Sum(nil))

	if !hmac.Equal([]byte(signature), []byte(expectedMAC)) {
		log.Printf("[SECURITY DROP] HMAC Inválido para Partner: %s", partnerID)
		http.Error(w, `{"error": "unauthorized"}`, http.StatusUnauthorized)
		return
	}

	// Fail-Closed: si Redis falla, no confirmar ingestión.
	if err := rdbCentral.XAdd(context.Background(), &redis.XAddArgs{
		Stream: "stream:ingestion_raw",
		Values: map[string]interface{}{"payload": string(body), "source": partnerID},
	}).Err(); err != nil {
		log.Printf("[FAIL-CLOSED] Redis XAdd falló para Partner %s: %v", partnerID, err)
		http.Error(w, `{"error": "service unavailable"}`, http.StatusServiceUnavailable)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	w.Write([]byte(`{"status": "ingested"}`))
}

func listenQUIC() {
	if pubKey == nil {
		log.Println("[WARNING] EDGE_PUB_KEY_HEX no configurado. QUIC Edge pausado.")
		return
	}

	// Fail-Closed: certificados TLS obligatorios para QUIC.
	cert, err := tls.LoadX509KeyPair("server.crt", "server.key")
	if err != nil {
		log.Fatalf("FATAL [FAIL-CLOSED]: No se pudieron cargar certificados TLS (server.crt/server.key): %v. Abortando QUIC.", err)
	}

	udpConn, err := net.ListenUDP("udp4", &net.UDPAddr{Port: 4433})
	if err != nil {
		log.Fatal(err)
	}
	udpConn.SetReadBuffer(268435456)

	tlsConf := &tls.Config{Certificates: []tls.Certificate{cert}, NextProtos: []string{"cardex-quic-v2"}}

	listener, err := quic.Listen(udpConn, tlsConf, &quic.Config{Allow0RTT: true})
	if err != nil {
		log.Fatal(err)
	}

	log.Println("[QUIC] Swarm Edge Gateway Activo (UDP:4433). Autenticación Ed25519 Armada.")

	for {
		conn, err := listener.Accept(context.Background())
		if err != nil {
			continue
		}
		go func(c *quic.Conn) {
			stream, err := c.AcceptStream(context.Background())
			if err != nil {
				return
			}
			defer stream.Close()

			var p EdgePayload
			if err := json.NewDecoder(stream).Decode(&p); err != nil {
				return
			}
			if time.Now().Unix()-p.Timestamp > 60 {
				return
			}

			sigBytes, err := hex.DecodeString(p.Signature)
			if err != nil || len(sigBytes) != ed25519.SignatureSize {
				return
			}
			if !ed25519.Verify(pubKey, []byte(p.Data), sigBytes) {
				return
			}

			// Fail-Closed: ignorar errores de XAdd en QUIC (log pero no exponer).
			if err := rdbCentral.XAdd(context.Background(), &redis.XAddArgs{
				Stream: "stream:ingestion_raw",
				Values: map[string]interface{}{"payload": p.Data, "source": "EDGE_FLEET"},
			}).Err(); err != nil {
				log.Printf("[FAIL-CLOSED] Redis XAdd falló para EDGE_FLEET: %v", err)
			}
		}(conn)
	}
}

func main() {
	runtime.GOMAXPROCS(16)

	go listenQUIC()

	http.HandleFunc("/v1/ingest", handleB2BWebhook)
	log.Println("[HTTP] Institutional Webhook Gateway Activo (TCP:8080). Fail-Closed estricto implementado.")
	http.ListenAndServe("0.0.0.0:8080", nil)
}
