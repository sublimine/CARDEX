package main

import (
	"context"
	"crypto/rand"
	"crypto/rsa"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/pem"
	"fmt"
	"log"
	"math/big"
	"net/http"
	"runtime"
	"time"

	"github.com/quic-go/quic-go/http3"
	"github.com/redis/go-redis/v9"
)

var rdb *redis.Client
var luaMutexSHA string

const luaMutex = `
if redis.call("EXISTS", KEYS[1]) == 1 then
	return -1 -- SOLD_OUT
end
local current_quote = redis.call("HGET", KEYS[2], "quote_id")
if current_quote and current_quote ~= ARGV[2] then
	return -2 -- PRICE_MISMATCH
end
redis.call("SET", KEYS[1], ARGV[1], "EX", 120) -- Escrow Lógico 120s
return 1 -- LOCKED_SUCCESS
`

func init() {
	rdb = redis.NewClient(&redis.Options{Addr: "127.0.0.1:6379", PoolSize: 2000})

	// Carga determinista del SHA en el arranque del Gateway
	sha, err := rdb.ScriptLoad(context.Background(), luaMutex).Result()
	if err != nil {
		log.Fatalf("FATAL: Imposible cargar LUA Mutex en Redis: %v", err)
	}
	luaMutexSHA = sha
}

func handleReservation(w http.ResponseWriter, r *http.Request) {
	vin := r.URL.Query().Get("vin")
	buyerID := r.URL.Query().Get("buyer_id")
	quoteID := r.URL.Query().Get("quote_id")

	if vin == "" || buyerID == "" || quoteID == "" {
		http.Error(w, `{"error": "MISSING_PARAMETERS"}`, http.StatusBadRequest)
		return
	}

	// Ejecución O(1) del LUA Mutex
	res, err := rdb.EvalSha(context.Background(), luaMutexSHA, []string{"lock:" + vin, "vehicle_state:" + vin}, buyerID, quoteID).Result()
	if err != nil {
		http.Error(w, `{"error": "INTERNAL_ERROR"}`, http.StatusInternalServerError)
		return
	}

	status := res.(int64)
	w.Header().Set("Content-Type", "application/json")

	if status == 1 {
		w.Write([]byte(`{"status": "LOCKED_SUCCESS"}`))
		// Encolar auditoría legal (Fase 7)
		rdb.XAdd(context.Background(), &redis.XAddArgs{
			Stream: "stream:legal_audit_pending",
			Values: map[string]interface{}{"vin": vin},
		})
		log.Printf("[DARK POOL] Monopolio otorgado. VIN: %s | Buyer: %s", vin, buyerID)
	} else if status == -1 {
		w.WriteHeader(http.StatusConflict)
		w.Write([]byte(`{"status": "SOLD_OUT"}`))
	} else if status == -2 {
		w.WriteHeader(http.StatusPreconditionFailed)
		w.Write([]byte(`{"status": "PRICE_MISMATCH"}`))
	}
}

func sseMarketStream(w http.ResponseWriter, r *http.Request) {
	flusher, ok := w.(http.Flusher)
	if !ok {
		http.Error(w, "SSE no soportado", http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")

	pubsub := rdb.Subscribe(context.Background(), "channel:live_market")
	defer pubsub.Close()

	for {
		select {
		case msg := <-pubsub.Channel():
			fmt.Fprintf(w, "data: %s\n\n", msg.Payload)
			flusher.Flush()
		case <-r.Context().Done():
			return
		}
	}
}

// Generación de TLS 1.3 Efímero para sortear dependencias locales de OpenSSL
func generateEphemeralTLS() *tls.Config {
	key, _ := rsa.GenerateKey(rand.Reader, 2048)
	template := x509.Certificate{
		SerialNumber:          big.NewInt(1),
		Subject:               pkix.Name{Organization: []string{"CARDEX EDGE"}},
		NotBefore:             time.Now(),
		NotAfter:              time.Now().Add(time.Hour * 24),
		KeyUsage:              x509.KeyUsageKeyEncipherment | x509.KeyUsageDigitalSignature,
		ExtKeyUsage:           []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth},
		BasicConstraintsValid: true,
	}
	certDER, _ := x509.CreateCertificate(rand.Reader, &template, &template, &key.PublicKey, key)
	keyPEM := pem.EncodeToMemory(&pem.Block{Type: "RSA PRIVATE KEY", Bytes: x509.MarshalPKCS1PrivateKey(key)})
	certPEM := pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: certDER})

	tlsCert, _ := tls.X509KeyPair(certPEM, keyPEM)
	return &tls.Config{
		Certificates: []tls.Certificate{tlsCert},
		NextProtos:   []string{"h3"},
	}
}

func main() {
	runtime.GOMAXPROCS(16)

	mux := http.NewServeMux()
	mux.HandleFunc("/reserve", handleReservation)
	mux.HandleFunc("/stream", sseMarketStream)

	server := &http3.Server{
		Addr:      "0.0.0.0:8443",
		Handler:   mux,
		TLSConfig: generateEphemeralTLS(),
	}

	log.Println("[V2.0] Edge Gateway QUIC HFT Activo (UDP:8443). Atomic LUA Mutex Armado.")
	if err := server.ListenAndServe(); err != nil {
		log.Fatal(err)
	}
}
