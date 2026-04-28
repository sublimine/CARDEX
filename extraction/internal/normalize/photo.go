package normalize

import (
	"net/url"
	"strings"
)

// CanonicalizePhotoURL makes a photo URL absolute given the base URL of the
// dealer's website. Returns the original URL unchanged if it is already
// absolute or cannot be resolved.
func CanonicalizePhotoURL(rawURL, baseURL string) string {
	rawURL = strings.TrimSpace(rawURL)
	if rawURL == "" {
		return ""
	}

	// Already absolute.
	if strings.HasPrefix(rawURL, "http://") || strings.HasPrefix(rawURL, "https://") {
		return rawURL
	}

	// Protocol-relative.
	if strings.HasPrefix(rawURL, "//") {
		return "https:" + rawURL
	}

	// Relative URL — resolve against base.
	base, err := url.Parse(baseURL)
	if err != nil {
		return rawURL
	}
	ref, err := url.Parse(rawURL)
	if err != nil {
		return rawURL
	}
	return base.ResolveReference(ref).String()
}

// DedupePhotoURLs removes duplicate URLs from the list, preserving order.
func DedupePhotoURLs(urls []string) []string {
	seen := make(map[string]bool, len(urls))
	out := make([]string, 0, len(urls))
	for _, u := range urls {
		if u != "" && !seen[u] {
			seen[u] = true
			out = append(out, u)
		}
	}
	return out
}

// FilterPhotoURLs removes URLs that are clearly not images (data URIs, SVG
// icons, tracking pixels).
func FilterPhotoURLs(urls []string) []string {
	out := make([]string, 0, len(urls))
	for _, u := range urls {
		lower := strings.ToLower(u)
		if strings.HasPrefix(lower, "data:") {
			continue // inline data URI — never stored
		}
		if strings.Contains(lower, "1x1") || strings.Contains(lower, "pixel") {
			continue // tracking pixel
		}
		if strings.HasSuffix(lower, ".svg") {
			continue // vector icon
		}
		out = append(out, u)
	}
	return out
}
