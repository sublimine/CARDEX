package robots

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestAllowed_DisallowAll(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte("User-agent: *\nDisallow: /\n"))
	}))
	defer srv.Close()

	c := New(srv.Client(), 0)
	if c.Allowed(context.Background(), "CardexBot/1.0", srv.URL+"/inventory") {
		t.Error("want Allowed=false for Disallow: /, got true")
	}
}

func TestAllowed_AllowAll(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte("User-agent: *\nDisallow:\n"))
	}))
	defer srv.Close()

	c := New(srv.Client(), 0)
	if !c.Allowed(context.Background(), "CardexBot/1.0", srv.URL+"/inventory") {
		t.Error("want Allowed=true for Disallow: (empty), got false")
	}
}

func TestAllowed_SpecificUAOverridesWildcard(t *testing.T) {
	body := "User-agent: *\nDisallow: /\n\nUser-agent: CardexBot\nDisallow:\n"
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte(body))
	}))
	defer srv.Close()

	c := New(srv.Client(), 0)
	// CardexBot/1.0 matches "cardexbot" rule — should be allowed.
	if !c.Allowed(context.Background(), "CardexBot/1.0", srv.URL+"/inventory") {
		t.Error("want Allowed=true for CardexBot specific rule, got false")
	}
}

func TestAllowed_FailOpen_On404(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNotFound)
	}))
	defer srv.Close()

	c := New(srv.Client(), 0)
	if !c.Allowed(context.Background(), "CardexBot/1.0", srv.URL+"/page") {
		t.Error("want Allowed=true (fail-open) when robots.txt returns 404, got false")
	}
}

func TestAllowed_TTLCache(t *testing.T) {
	calls := 0
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls++
		w.Write([]byte("User-agent: *\nDisallow:\n"))
	}))
	defer srv.Close()

	c := New(srv.Client(), time.Hour)
	c.Allowed(context.Background(), "CardexBot/1.0", srv.URL+"/a")
	c.Allowed(context.Background(), "CardexBot/1.0", srv.URL+"/b")
	if calls != 1 {
		t.Errorf("want robots.txt fetched once (TTL cache), got %d fetches", calls)
	}
}

func TestParseRobots_AllowOverridesDisallow(t *testing.T) {
	body := "User-agent: *\nDisallow: /private/\nAllow: /private/public/\n"
	rules := parseRobots(strings.NewReader(body))
	if len(rules) == 0 {
		t.Fatal("no rules parsed")
	}
	r := rules[0]
	if len(r.disallowed) == 0 || r.disallowed[0] != "/private/" {
		t.Errorf("unexpected disallow: %v", r.disallowed)
	}
	if len(r.allowed) == 0 || r.allowed[0] != "/private/public/" {
		t.Errorf("unexpected allow: %v", r.allowed)
	}
}
