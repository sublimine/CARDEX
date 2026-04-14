package traxio_test

import (
	"strings"
	"testing"

	"github.com/PuerkitoBio/goquery"

	"cardex.eu/discovery/internal/families/familia_g/traxio"
)

// ── ParseMemberPage ───────────────────────────────────────────────────────────

func TestParseMemberPage_MemberCards(t *testing.T) {
	html := `<!DOCTYPE html><html><body>
<ul class="members">
  <li class="member-card">
    <h3>Garage Dubois SA</h3>
    <div class="address">Rue de la Loi 42<br/>1000 Bruxelles</div>
    <a href="/fr/membres/garage-dubois">Voir</a>
  </li>
  <li class="member-card">
    <h3>Auto Center Liège</h3>
    <div class="address">Boulevard de la Sauvenière 10<br/>4000 Liège</div>
    <a href="/fr/membres/auto-center-liege">Voir</a>
    <a href="https://www.autoliege.be">Site web</a>
  </li>
</ul>
<a rel="next" href="/fr/membres?page=2">Suivant</a>
</body></html>`

	doc, err := goquery.NewDocumentFromReader(strings.NewReader(html))
	if err != nil {
		t.Fatalf("parse HTML: %v", err)
	}

	members, hasMore, err := traxio.ParseMemberPage(doc, "https://www.traxio.be")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(members) != 2 {
		t.Fatalf("want 2 members, got %d", len(members))
	}
	if hasMore != true {
		t.Error("want hasMore=true (next link present)")
	}

	m0 := members[0]
	if m0.Name != "Garage Dubois SA" {
		t.Errorf("members[0].Name = %q, want Garage Dubois SA", m0.Name)
	}
	if m0.PostalCode != "1000" {
		t.Errorf("members[0].PostalCode = %q, want 1000", m0.PostalCode)
	}
	if m0.City != "Bruxelles" {
		t.Errorf("members[0].City = %q, want Bruxelles", m0.City)
	}
	if !strings.Contains(m0.DetailURL, "garage-dubois") {
		t.Errorf("members[0].DetailURL = %q, want contains garage-dubois", m0.DetailURL)
	}

	m1 := members[1]
	if m1.Website != "https://www.autoliege.be" {
		t.Errorf("members[1].Website = %q, want https://www.autoliege.be", m1.Website)
	}
}

func TestParseMemberPage_NoMembers(t *testing.T) {
	html := `<!DOCTYPE html><html><body><p>Aucun résultat.</p></body></html>`
	doc, _ := goquery.NewDocumentFromReader(strings.NewReader(html))

	members, hasMore, err := traxio.ParseMemberPage(doc, "https://www.traxio.be")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(members) != 0 {
		t.Errorf("want 0 members, got %d", len(members))
	}
	if hasMore {
		t.Error("want hasMore=false for empty page")
	}
}

func TestParseMemberPage_NoNextPage(t *testing.T) {
	html := `<!DOCTYPE html><html><body>
<ul class="members">
  <li class="member-card"><h3>Last Garage</h3><div class="address">5000 Namur</div></li>
</ul>
</body></html>`
	doc, _ := goquery.NewDocumentFromReader(strings.NewReader(html))

	members, hasMore, err := traxio.ParseMemberPage(doc, "https://www.traxio.be")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(members) != 1 {
		t.Errorf("want 1 member, got %d", len(members))
	}
	if hasMore {
		t.Error("want hasMore=false (no next link)")
	}
}
