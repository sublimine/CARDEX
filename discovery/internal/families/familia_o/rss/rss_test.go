package rss_test

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"cardex.eu/discovery/internal/families/familia_o/rss"
	"cardex.eu/discovery/internal/kg"
)

type stubGraph struct {
	kg.KnowledgeGraph
	upserted    []*kg.DealerEntity
	discoveries []*kg.DiscoveryRecord
	signals     []*kg.DealerPressSignal
	nameMap     map[string][]string
	state       map[string]string
}

func (g *stubGraph) FindDealersByName(_ context.Context, norm, _ string) ([]string, error) {
	if g.nameMap != nil {
		return g.nameMap[norm], nil
	}
	return nil, nil
}
func (g *stubGraph) UpsertDealer(_ context.Context, e *kg.DealerEntity) error {
	g.upserted = append(g.upserted, e)
	return nil
}
func (g *stubGraph) RecordDiscovery(_ context.Context, r *kg.DiscoveryRecord) error {
	g.discoveries = append(g.discoveries, r)
	return nil
}
func (g *stubGraph) RecordPressSignal(_ context.Context, s *kg.DealerPressSignal) error {
	g.signals = append(g.signals, s)
	return nil
}
func (g *stubGraph) GetProcessingState(_ context.Context, _ string) (string, error) {
	return "", nil
}
func (g *stubGraph) SetProcessingState(_ context.Context, key, val string) error {
	if g.state == nil {
		g.state = map[string]string{}
	}
	g.state[key] = val
	return nil
}

const rss20Feed = `<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <title>KFZ-Betrieb News</title>
    <item>
      <title>Autohaus Muster GmbH eröffnet neuen Showroom in Berlin</title>
      <link>https://kfz-betrieb.example.com/news/1</link>
    </item>
    <item>
      <title>Marktentwicklung im KFZ-Handel 2024</title>
      <link>https://kfz-betrieb.example.com/news/2</link>
    </item>
  </channel>
</rss>`

const atomFeed = `<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Garage Dupont SARL ferme ses portes</title>
    <link rel="alternate" href="https://autoactu.example.com/1"/>
  </entry>
</feed>`

func TestRun_RSS2_ExtractsDealer(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/rss+xml")
		_, _ = w.Write([]byte(rss20Feed))
	}))
	defer srv.Close()

	// Override feed URL via a custom client that redirects to mock server.
	graph := &stubGraph{}
	poller := rss.NewWithClientAndFeeds(graph, srv.Client(),
		map[string][]string{"DE": {srv.URL + "/feed"}})

	result, err := poller.Run(context.Background(), "DE")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered == 0 {
		t.Error("want at least 1 discovered candidate from RSS item title")
	}
}

func TestRun_Atom_ExtractsDealer(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/atom+xml")
		_, _ = w.Write([]byte(atomFeed))
	}))
	defer srv.Close()

	graph := &stubGraph{}
	poller := rss.NewWithClientAndFeeds(graph, srv.Client(),
		map[string][]string{"FR": {srv.URL + "/feed"}})

	result, err := poller.Run(context.Background(), "FR")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered == 0 {
		t.Error("want at least 1 discovered candidate from Atom feed")
	}
}

func TestRun_ExistingDealer_RecordsSignal(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/rss+xml")
		_, _ = w.Write([]byte(rss20Feed))
	}))
	defer srv.Close()

	graph := &stubGraph{
		nameMap: map[string][]string{"muster": {"D1"}},
	}
	poller := rss.NewWithClientAndFeeds(graph, srv.Client(),
		map[string][]string{"DE": {srv.URL + "/feed"}})

	result, err := poller.Run(context.Background(), "DE")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// Discovered=0 because dealer already exists.
	if result.Discovered != 0 {
		t.Errorf("want 0 new dealers (already known), got %d", result.Discovered)
	}
	if len(graph.signals) == 0 {
		t.Error("want at least 1 press signal for known dealer")
	}
}

func TestRun_NoFeedsForCountry(t *testing.T) {
	graph := &stubGraph{}
	poller := rss.NewWithClientAndFeeds(graph, http.DefaultClient,
		map[string][]string{}) // no feeds

	result, err := poller.Run(context.Background(), "PL")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 0 {
		t.Errorf("want 0, got %d", result.Discovered)
	}
}
