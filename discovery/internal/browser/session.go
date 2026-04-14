package browser

import (
	"fmt"
	"log/slog"
	"sync"

	"github.com/playwright-community/playwright-go"
)

// contextPool maintains one BrowserContext per host, isolating cookies and
// storage between different target sites.
//
// Using a per-host context (rather than per-page) ensures that login state or
// session cookies set by one page on a host are available to subsequent pages
// on the same host — useful for associations requiring soft auth (e.g. TRAXIO,
// AGVS). Contexts are created lazily and reused.
type contextPool struct {
	mu       sync.Mutex
	browser  playwright.Browser
	contexts map[string]playwright.BrowserContext // host → context
	cfg      *BrowserConfig
	log      *slog.Logger
}

func newContextPool(b playwright.Browser, cfg *BrowserConfig) *contextPool {
	return &contextPool{
		browser:  b,
		contexts: make(map[string]playwright.BrowserContext),
		cfg:      cfg,
		log:      slog.Default().With("component", "browser.contextPool"),
	}
}

// acquire returns (or lazily creates) the BrowserContext for the given host.
func (p *contextPool) acquire(host string) (playwright.BrowserContext, error) {
	p.mu.Lock()
	defer p.mu.Unlock()

	if ctx, ok := p.contexts[host]; ok {
		return ctx, nil
	}

	ctx, err := p.browser.NewContext(playwright.BrowserNewContextOptions{
		UserAgent:        playwright.String(p.cfg.UserAgent),
		Locale:           playwright.String(p.cfg.Locale),
		TimezoneId:       playwright.String(p.cfg.TimezoneID),
		ExtraHttpHeaders: p.cfg.ExtraHeaders,
		Viewport: &playwright.Size{
			Width:  p.cfg.ViewportWidth,
			Height: p.cfg.ViewportHeight,
		},
		// BypassCSP is intentionally NOT set (defaults to false) — we respect CSP.
	})
	if err != nil {
		return nil, fmt.Errorf("contextPool.acquire: new context for %q: %w", host, err)
	}

	p.contexts[host] = ctx
	p.log.Debug("browser: new context created", "host", host)
	return ctx, nil
}

// closeAll gracefully closes every context in the pool.
// Called during Browser.Close().
func (p *contextPool) closeAll() {
	p.mu.Lock()
	defer p.mu.Unlock()

	for host, ctx := range p.contexts {
		if err := ctx.Close(); err != nil {
			p.log.Warn("browser: context close error", "host", host, "err", err)
		}
	}
	p.contexts = make(map[string]playwright.BrowserContext)
}

// pageSemaphore is a counting semaphore that caps the number of simultaneously
// open pages to BrowserConfig.MaxConcurrentPages.
type pageSemaphore struct {
	ch chan struct{}
}

func newPageSemaphore(max int) *pageSemaphore {
	ch := make(chan struct{}, max)
	for i := 0; i < max; i++ {
		ch <- struct{}{}
	}
	return &pageSemaphore{ch: ch}
}

// acquire blocks until a slot is available.
func (s *pageSemaphore) acquire() { <-s.ch }

// release returns a slot to the pool.
func (s *pageSemaphore) release() { s.ch <- struct{}{} }
