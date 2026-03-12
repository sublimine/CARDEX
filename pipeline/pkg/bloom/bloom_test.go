//go:build integration

package bloom

import (
	"context"
	"fmt"
	"strings"
	"testing"
	"time"

	"github.com/redis/go-redis/v9"
)

func newTestBloom(t *testing.T, key string) *Bloom {
	t.Helper()
	rdb := redis.NewClient(&redis.Options{
		Addr: "localhost:6379",
	})
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := rdb.Ping(ctx).Err(); err != nil {
		t.Skipf("Redis not available at localhost:6379: %v", err)
	}
	return New(rdb, key)
}

func uniqueFingerprint(prefix string) string {
	return fmt.Sprintf("%s%060x", prefix, time.Now().UnixNano())
}

func TestBloom_Exists_Add(t *testing.T) {
	ctx := context.Background()
	ts := time.Now().Format("20060102150405.000")

	tests := []struct {
		name string
		run  func(t *testing.T, b *Bloom)
	}{
		{
			name: "new fingerprint not exists",
			run: func(t *testing.T, b *Bloom) {
				fp := uniqueFingerprint("new_")
				exists, err := b.Exists(ctx, fp)
				if err != nil {
					t.Fatalf("Exists() error = %v", err)
				}
				if exists {
					t.Errorf("Exists() = true, want false for new fingerprint")
				}
			},
		},
		{
			name: "add then exists",
			run: func(t *testing.T, b *Bloom) {
				fp := uniqueFingerprint("add_")
				if err := b.Add(ctx, fp); err != nil {
					t.Fatalf("Add() error = %v", err)
				}
				exists, err := b.Exists(ctx, fp)
				if err != nil {
					t.Fatalf("Exists() error = %v", err)
				}
				if !exists {
					t.Errorf("Exists() = false, want true after Add")
				}
			},
		},
		{
			name: "different fingerprint not exists",
			run: func(t *testing.T, b *Bloom) {
				fpA := strings.Repeat("a", 64)
				fpB := strings.Repeat("b", 64)
				if err := b.Add(ctx, fpA); err != nil {
					t.Fatalf("Add() error = %v", err)
				}
				exists, err := b.Exists(ctx, fpB)
				if err != nil {
					t.Fatalf("Exists() error = %v", err)
				}
				if exists {
					t.Errorf("Exists(bbb...) = true, want false for different fingerprint")
				}
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			key := fmt.Sprintf("bloom:test:%s:%s", strings.ReplaceAll(tt.name, " ", "_"), ts)
			b := newTestBloom(t, key)
			tt.run(t, b)
		})
	}
}
