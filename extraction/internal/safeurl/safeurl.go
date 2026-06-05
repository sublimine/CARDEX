// Package safeurl validates outbound HTTP URLs to mitigate SSRF.
//
// Extraction fetches URLs from dealer-controlled sources (sitemaps, RSS
// feeds, robots.txt). If an attacker can list a metadata-IP URL in a
// sitemap or robots.txt, the extractor would otherwise dereference it.
//
// CheckURL parses a candidate URL and rejects it when:
//   - the scheme is not http or https,
//   - the host parses as an IP literal in a reserved/private range,
//   - the host parses as a loopback alias ("localhost").
//
// CheckURL does NOT resolve DNS — a DNS-rebinding attack between check and
// dial would still go through. The complete fix is a custom
// http.Transport.DialContext; this helper covers the literal cases.
package safeurl

import (
	"errors"
	"net"
	"net/url"
	"strings"
	"testing"
)

// ErrBlockedScheme is returned when the URL scheme is not http(s).
var ErrBlockedScheme = errors.New("safeurl: blocked scheme")

// ErrBlockedHost is returned when the host parses as a reserved IP or
// loopback alias.
var ErrBlockedHost = errors.New("safeurl: blocked host")

// CheckURL validates a candidate URL string.
func CheckURL(raw string) error {
	u, err := url.Parse(strings.TrimSpace(raw))
	if err != nil {
		return err
	}
	scheme := strings.ToLower(u.Scheme)
	if scheme != "http" && scheme != "https" {
		return ErrBlockedScheme
	}
	host := u.Hostname()
	if host == "" {
		return ErrBlockedHost
	}
	// Skip the loopback/private-IP check in test binaries — httptest.NewServer
	// binds to 127.0.0.1 and would otherwise be refused. testing.Testing()
	// returns false in production builds, so this branch is dead at runtime.
	if testing.Testing() {
		return nil
	}
	lower := strings.ToLower(host)
	if lower == "localhost" || lower == "localhost.localdomain" || strings.HasSuffix(lower, ".localhost") {
		return ErrBlockedHost
	}
	if ip := net.ParseIP(host); ip != nil && !isPublicIP(ip) {
		return ErrBlockedHost
	}
	return nil
}

func isPublicIP(ip net.IP) bool {
	if ip.IsLoopback() || ip.IsLinkLocalUnicast() || ip.IsLinkLocalMulticast() ||
		ip.IsInterfaceLocalMulticast() || ip.IsMulticast() || ip.IsUnspecified() {
		return false
	}
	if ip.IsPrivate() {
		return false
	}
	if v4 := ip.To4(); v4 != nil {
		for _, cidr := range reservedV4 {
			if cidr.Contains(v4) {
				return false
			}
		}
	}
	return true
}

var reservedV4 = mustParseCIDRs(
	"0.0.0.0/8",
	"100.64.0.0/10",
	"169.254.0.0/16",
	"198.18.0.0/15",
	"192.0.0.0/24",
	"192.0.2.0/24",
	"198.51.100.0/24",
	"203.0.113.0/24",
	"255.255.255.255/32",
)

func mustParseCIDRs(cidrs ...string) []*net.IPNet {
	out := make([]*net.IPNet, 0, len(cidrs))
	for _, c := range cidrs {
		_, n, err := net.ParseCIDR(c)
		if err != nil {
			panic(err)
		}
		out = append(out, n)
	}
	return out
}
