package main

import (
	"context"
	"log/slog"
	"net/http"
	"os"
	"sync"
	"time"

	"github.com/gorilla/websocket"
	"github.com/redis/go-redis/v9"
)

var upgrader = websocket.Upgrader{
	CheckOrigin: func(r *http.Request) bool { return true },
}

type ClientManager struct {
	clients    map[*websocket.Conn]bool
	broadcast  chan []byte
	register   chan *websocket.Conn
	unregister chan *websocket.Conn
	mutex      sync.Mutex
}

var manager = ClientManager{
	broadcast:  make(chan []byte, 256),
	register:   make(chan *websocket.Conn),
	unregister: make(chan *websocket.Conn),
	clients:    make(map[*websocket.Conn]bool),
}

var rdb *redis.Client

func init() {
	addr := os.Getenv("REDIS_ADDR")
	if addr == "" {
		addr = "127.0.0.1:6379"
	}
	rdb = redis.NewClient(&redis.Options{Addr: addr, PoolSize: 100})
}

func (m *ClientManager) start() {
	for {
		select {
		case conn := <-m.register:
			m.mutex.Lock()
			m.clients[conn] = true
			m.mutex.Unlock()
			slog.Info("phase:hft_gateway client connected", "clients", len(m.clients))
		case conn := <-m.unregister:
			m.mutex.Lock()
			if _, ok := m.clients[conn]; ok {
				delete(m.clients, conn)
				_ = conn.Close()
				slog.Info("phase:hft_gateway client disconnected", "clients", len(m.clients))
			}
			m.mutex.Unlock()
		case msg := <-m.broadcast:
			m.mutex.Lock()
			for conn := range m.clients {
				if err := conn.WriteMessage(websocket.TextMessage, msg); err != nil {
					_ = conn.Close()
					delete(m.clients, conn)
				}
			}
			m.mutex.Unlock()
		}
	}
}

func wsPage(w http.ResponseWriter, r *http.Request) {
	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		slog.Error("phase:hft_gateway upgrade failed", "error", err)
		return
	}
	manager.register <- conn
	go func() {
		for {
			if _, _, err := conn.ReadMessage(); err != nil {
				manager.unregister <- conn
				return
			}
		}
	}()
}

// consumeRedisStream escucha stream:darkpool_ready con XREAD Block:0 y emite el JSON al WebSocket.
func consumeRedisStream() {
	ctx := context.Background()
	lastID := "$"

	slog.Info("phase:hft_gateway anchored to stream", "stream", "stream:darkpool_ready")

	for {
		streams, err := rdb.XRead(ctx, &redis.XReadArgs{
			Streams: []string{"stream:darkpool_ready", lastID},
			Count:   10,
			Block:   0,
		}).Result()

		if err != nil {
			slog.Error("phase:hft_gateway xread failed", "error", err)
			select {
			case <-time.After(1 * time.Second):
			}
			continue
		}

		for _, stream := range streams {
			for _, msg := range stream.Messages {
				lastID = msg.ID
				if dataStr, ok := msg.Values["data"].(string); ok {
					slog.Info("phase:hft_gateway stream forwarded", "id", msg.ID)
					manager.broadcast <- []byte(dataStr)
				}
			}
		}
	}
}

func main() {
	slog.SetDefault(slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo})))

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := rdb.Ping(ctx).Err(); err != nil {
		slog.Error("phase:hft_gateway redis unreachable", "error", err)
		os.Exit(1)
	}

	slog.Info("phase:hft_gateway listening", "port", 8084)
	go manager.start()
	go consumeRedisStream()

	http.HandleFunc("/ws", wsPage)
	if err := http.ListenAndServe(":8084", nil); err != nil {
		slog.Error("phase:hft_gateway listen failed", "error", err)
		os.Exit(1)
	}
}
