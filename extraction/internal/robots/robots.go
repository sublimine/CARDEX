// Package robots provides robots.txt compliance checking for HTTP crawl strategies.
//
// # Usage
//
//	checker := robots.New(&http.Client{Timeout: 10 * time.Second}, 24*time.Hour)
//	if !checker.Allowed(ctx, "CardexBot/1.0", "https://dealer.example.de/inventory") {
//	    // skip — robots.txt disallows this path for our user-agent
//	}
//
// # Caching
//
// robots.txt files are fetched once per host and cached for the configured TTL
// (default 24 h). If the host is unreachable or returns a non-200 status the
// result is treated as "allow all" — a conservative choice that avoids blocking
// legitimate crawl targets due to transient network errors.
//
// # Spec compliance
//
// Parser implements the subset of the Robots Exclusion Protocol used in
// production: User-agent, Disallow, Allow directives. Wildcard * in paths is
// NOT supported (rarely used, avoids catastrophic backtracking). CrawlDelay is
// parsed but not enforced (rate limiting is handled at the strategy level).
package robots

import (
	"bufio"
	"context"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"time"
)

// Checker fetches, parses, and caches robots.txt files.
type Checker struct {
	client *http.Client
	ttl    time.Duration

	mu    sync.RWMutex
	cache map[string]cachedRobots // keyed by host (scheme+host)
}

type cachedRobots struct {
	rules     []rule
	fetchedAt time.Time
}

type rule struct {
	userAgent string // lowercase; "*" means wildcard
	allowed   []string
	disallowed []string
}

// New constructs a Checker with the given HTTP client and cache TTL.
// A TTL of 0 disables caching (re-fetches on every call — for tests only).
func New(client *http.Client, ttl time.Duration) *Checker {
	return &Checker{
		client: client,
		ttl:    ttl,
		cache:  make(map[string]cachedRobots),
	}
}

// Allowed returns true if the given userAgent is permitted to fetch the URL
// according to the host's robots.txt. Returns true on any fetch or parse error
// (fail-open — transient errors must not block legitimate crawling).
func (c *Checker) Allowed(ctx context.Context, userAgent, rawURL string) bool {
	u, err := url.Parse(rawURL)
	if err != nil {
		return true
	}
	host := u.Scheme + "://" + u.Host

	rules, ok := c.cachedRules(host)
	if !ok {
		rules = c.fetch(ctx, host)
		c.storeRules(host, rules)
	}

	path := u.RequestURI()
	ua := strings.ToLower(userAgent)

	// Check specific user-agent rules first, then wildcard.
	// Per robots.txt convention, match if the rule's UA token is a case-insensitive
	// substring of the actual UA string (e.g. "CardexBot" matches "CardexBot/1.0").
	for _, ag := range []string{ua, "*"} {
		for _, r := range rules {
			match := r.userAgent == "*" && ag == "*"
			if !match && ag != "*" {
				match = strings.Contains(ua, r.userAgent) && r.userAgent != "*"
			}
			if !match {
				continue
			}
			// Longer (more specific) matches win; scan all rules for this agent.
			// Simple implementation: last matching rule wins (standard behaviour).
			allowed := true
			for _, d := range r.disallowed {
				if d != "" && strings.HasPrefix(path, d) {
					allowed = false
				}
			}
			for _, a := range r.allowed {
				if a != "" && strings.HasPrefix(path, a) {
					allowed = true
				}
			}
			return allowed
		}
	}

	return true // no applicable rule → allow
}

// cachedRules returns cached rules if they exist and haven't expired.
func (c *Checker) cachedRules(host string) ([]rule, bool) {
	if c.ttl == 0 {
		return nil, false
	}
	c.mu.RLock()
	defer c.mu.RUnlock()
	cr, ok := c.cache[host]
	if !ok || time.Since(cr.fetchedAt) > c.ttl {
		return nil, false
	}
	return cr.rules, true
}

func (c *Checker) storeRules(host string, rules []rule) {
	if c.ttl == 0 {
		return
	}
	c.mu.Lock()
	defer c.mu.Unlock()
	c.cache[host] = cachedRobots{rules: rules, fetchedAt: time.Now()}
}

// fetch retrieves and parses robots.txt for the given host.
// Returns empty rules (allow all) on any error.
func (c *Checker) fetch(ctx context.Context, host string) []rule {
	robotsURL := host + "/robots.txt"
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, robotsURL, nil)
	if err != nil {
		return nil
	}
	resp, err := c.client.Do(req)
	if err != nil || resp.StatusCode != http.StatusOK {
		if resp != nil {
			resp.Body.Close()
		}
		return nil
	}
	defer resp.Body.Close()
	return parseRobots(resp.Body)
}

// parseRobots parses a robots.txt body from r.
func parseRobots(r interface{ Read([]byte) (int, error) }) []rule {
	var rules []rule
	var current *rule

	scanner := bufio.NewScanner(r.(interface {
		Read([]byte) (int, error)
	}))
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		// Strip inline comments.
		if i := strings.Index(line, "#"); i >= 0 {
			line = strings.TrimSpace(line[:i])
		}
		if line == "" {
			current = nil
			continue
		}
		key, val, ok := strings.Cut(line, ":")
		if !ok {
			continue
		}
		key = strings.TrimSpace(strings.ToLower(key))
		val = strings.TrimSpace(val)

		switch key {
		case "user-agent":
			r := rule{userAgent: strings.ToLower(val)}
			rules = append(rules, r)
			current = &rules[len(rules)-1]
		case "disallow":
			if current != nil {
				current.disallowed = append(current.disallowed, val)
			}
		case "allow":
			if current != nil {
				current.allowed = append(current.allowed, val)
			}
		}
	}
	return rules
}
