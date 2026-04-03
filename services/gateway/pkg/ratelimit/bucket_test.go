//go:build integration

package ratelimit

import (
	"context"
	"testing"
	"time"

	"github.com/redis/go-redis/v9"
)

func newTestLimiter(t *testing.T) *Limiter {
	t.Helper()
	rdb := redis.NewClient(&redis.Options{
		Addr: "localhost:6379",
	})
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := rdb.Ping(ctx).Err(); err != nil {
		t.Skipf("Redis not available at localhost:6379: %v", err)
	}
	return New(rdb)
}

func TestLimiter_Allow(t *testing.T) {
	limiter := newTestLimiter(t)
	ctx := context.Background()

	tests := []struct {
		name       string
		key        string
		maxTokens  int
		refillRate float64
		run        func(t *testing.T, l *Limiter, key string, maxTokens int, refillRate float64) bool
		want       bool
	}{
		{
			name:       "allow when bucket is full",
			key:        "ratelimit:full:" + time.Now().Format("20060102150405.000"),
			maxTokens:  10,
			refillRate: 1.0,
			run: func(t *testing.T, l *Limiter, key string, maxTokens int, refillRate float64) bool {
				allowed, err := l.Allow(ctx, key, maxTokens, refillRate)
				if err != nil {
					t.Fatalf("Allow() error = %v", err)
				}
				return allowed
			},
			want: true,
		},
		{
			name:       "deny when bucket is empty",
			key:        "ratelimit:empty:" + time.Now().Format("20060102150405.000"),
			maxTokens:  3,
			refillRate: 1.0,
			run: func(t *testing.T, l *Limiter, key string, maxTokens int, refillRate float64) bool {
				for i := 0; i < maxTokens; i++ {
					allowed, err := l.Allow(ctx, key, maxTokens, refillRate)
					if err != nil {
						t.Fatalf("Allow() error = %v", err)
					}
					if !allowed {
						t.Fatalf("Allow() call %d expected true, got false", i+1)
					}
				}
				allowed, err := l.Allow(ctx, key, maxTokens, refillRate)
				if err != nil {
					t.Fatalf("Allow() error = %v", err)
				}
				return allowed
			},
			want: false,
		},
		{
			name:       "bucket refills after time passes",
			key:        "ratelimit:refill:" + time.Now().Format("20060102150405.000"),
			maxTokens:  1,
			refillRate: 1.0,
			run: func(t *testing.T, l *Limiter, key string, maxTokens int, refillRate float64) bool {
				allowed, err := l.Allow(ctx, key, maxTokens, refillRate)
				if err != nil {
					t.Fatalf("Allow() error = %v", err)
				}
				if !allowed {
					t.Fatalf("Allow() first call expected true, got false")
				}
				allowed, err = l.Allow(ctx, key, maxTokens, refillRate)
				if err != nil {
					t.Fatalf("Allow() error = %v", err)
				}
				if allowed {
					t.Fatalf("Allow() second call (exhausted) expected false, got true")
				}
				time.Sleep(1500 * time.Millisecond)
				allowed, err = l.Allow(ctx, key, maxTokens, refillRate)
				if err != nil {
					t.Fatalf("Allow() error = %v", err)
				}
				return allowed
			},
			want: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := tt.run(t, limiter, tt.key, tt.maxTokens, tt.refillRate)
			if got != tt.want {
				t.Errorf("Allow() = %v, want %v", got, tt.want)
			}
		})
	}
}
