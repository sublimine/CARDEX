package youtube_test

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"cardex.eu/discovery/internal/families/familia_l/youtube"
	"cardex.eu/discovery/internal/kg"
)

// -- KG stub ------------------------------------------------------------------

type stubGraph struct {
	kg.KnowledgeGraph
	domainMap  map[string]string // domain -> dealerID
	profiles   []*kg.DealerSocialProfile
}

func (g *stubGraph) FindDealerIDByDomain(_ context.Context, domain string) (string, error) {
	id := g.domainMap[domain]
	return id, nil
}

func (g *stubGraph) UpsertSocialProfile(_ context.Context, p *kg.DealerSocialProfile) error {
	g.profiles = append(g.profiles, p)
	return nil
}

// -- Helpers ------------------------------------------------------------------

// youtubeServer returns a test server that serves canned search + channel responses.
func youtubeServer(t *testing.T,
	searchItems []map[string]interface{},
	channelItems []map[string]interface{},
) *httptest.Server {
	t.Helper()
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.URL.Path == "/search":
			items := make([]map[string]interface{}, 0)
			for _, si := range searchItems {
				items = append(items, si)
			}
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"items": items})
		case r.URL.Path == "/channels":
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"items": channelItems})
		default:
			http.NotFound(w, r)
		}
	}))
}

// -- Tests --------------------------------------------------------------------

func TestRun_NoAPIKey_SkipsGracefully(t *testing.T) {
	graph := &stubGraph{}
	yt := youtube.New(graph, "") // empty API key
	result, err := yt.Run(context.Background(), "DE")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 0 {
		t.Errorf("want 0 discovered without API key, got %d", result.Discovered)
	}
	if len(graph.profiles) != 0 {
		t.Errorf("want 0 profiles, got %d", len(graph.profiles))
	}
}

func TestRun_ChannelLinkedToDealer(t *testing.T) {
	searchItems := []map[string]interface{}{
		{
			"id":      map[string]interface{}{"kind": "youtube#channel", "channelId": "UCabc123"},
			"snippet": map[string]interface{}{"title": "Autohaus Müller", "channelId": "UCabc123"},
		},
	}
	channelItems := []map[string]interface{}{
		{
			"id": "UCabc123",
			"snippet": map[string]interface{}{
				"title":       "Autohaus Müller GmbH",
				"description": "Ihr Autohaus in München! Besuchen Sie uns: https://autohaus-mueller.de",
				"country":     "DE",
				"customUrl":   "@autohaus-mueller",
			},
		},
	}

	srv := youtubeServer(t, searchItems, channelItems)
	defer srv.Close()

	graph := &stubGraph{
		domainMap: map[string]string{
			"autohaus-mueller.de": "dealer-001",
		},
	}
	yt := youtube.NewWithClient(graph, "fake-key", srv.URL, &http.Client{Timeout: 5 * time.Second})

	result, err := yt.Run(context.Background(), "DE")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 1 {
		t.Errorf("want 1 discovered, got %d", result.Discovered)
	}
	if len(graph.profiles) != 1 {
		t.Fatalf("want 1 social profile, got %d", len(graph.profiles))
	}
	p := graph.profiles[0]
	if p.Platform != "youtube" {
		t.Errorf("Platform = %q, want youtube", p.Platform)
	}
	if p.DealerID != "dealer-001" {
		t.Errorf("DealerID = %q, want dealer-001", p.DealerID)
	}
	if p.ExternalID == nil || *p.ExternalID != "UCabc123" {
		t.Errorf("ExternalID = %v, want UCabc123", p.ExternalID)
	}
}

func TestRun_ChannelNoDomainMatch(t *testing.T) {
	searchItems := []map[string]interface{}{
		{
			"id":      map[string]interface{}{"kind": "youtube#channel", "channelId": "UCxyz999"},
			"snippet": map[string]interface{}{"title": "Random Channel", "channelId": "UCxyz999"},
		},
	}
	channelItems := []map[string]interface{}{
		{
			"id": "UCxyz999",
			"snippet": map[string]interface{}{
				"title":       "Random Channel",
				"description": "No website here.",
				"country":     "DE",
			},
		},
	}

	srv := youtubeServer(t, searchItems, channelItems)
	defer srv.Close()

	// domain not in KG
	graph := &stubGraph{domainMap: map[string]string{}}
	yt := youtube.NewWithClient(graph, "fake-key", srv.URL, &http.Client{Timeout: 5 * time.Second})

	result, err := yt.Run(context.Background(), "DE")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 0 {
		t.Errorf("want 0 discovered, got %d", result.Discovered)
	}
	if len(graph.profiles) != 0 {
		t.Errorf("want 0 profiles, got %d", len(graph.profiles))
	}
}

func TestRun_UnsupportedCountry(t *testing.T) {
	graph := &stubGraph{}
	yt := youtube.New(graph, "fake-key")
	result, err := yt.Run(context.Background(), "XX")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 0 {
		t.Errorf("want 0 discovered for unsupported country, got %d", result.Discovered)
	}
}
