"""
Marker mining — surface the UNKNOWN platform families behind dealer sites.

``cms_fingerprint`` classifies what we already know; ~70-85% of probed dealers come
back 'unknown'. This module extracts platform-identifying MARKERS from a homepage so
that aggregating them across the unknown cluster reveals which families dominate —
each marker shared by N domains is a candidate ``cms_fingerprint`` signature and a
candidate family recipe (the 1-recipe-closes-N-dealers multiplier).

Pure functions, no I/O — the runner (``scripts/mine_unknown_cms.py``) owns transport.

Marker kinds:
  * ``generator``  — ``<meta name="generator">`` value, version-normalized
  * ``powered_by`` — visible "powered by X" credit, normalized
  * ``ext_host``   — registrable domain of an EXTERNAL script/css/img origin
                     (SaaS/DMS platform CDNs are the strongest dealer-vertical tell)
  * ``path_token`` — first path segment of an INTERNAL script/css asset
                     (``/wp-content/`` ⇒ wordpress, ``/fileadmin/`` ⇒ typo3, …)
  * ``js_marker``  — a known framework/CMS token present in the raw HTML
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from urllib.parse import urlparse

__all__ = ["extract_markers", "aggregate_markers"]

_GENERATOR_RE = re.compile(
    r"<meta[^>]+(?:name=[\"']generator[\"'][^>]+content=[\"']([^\"']{2,80})[\"']"
    r"|content=[\"']([^\"']{2,80})[\"'][^>]+name=[\"']generator[\"'])",
    re.IGNORECASE,
)
_POWERED_RE = re.compile(r"powered\s+by\s+([a-z0-9][a-z0-9 ._-]{2,40})", re.IGNORECASE)
_SRC_RE = re.compile(r"(?:src|href)=[\"']([^\"']{4,300})[\"']", re.IGNORECASE)

# Origins every site embeds — never a platform signal.
_NOISE_HOSTS = frozenset({
    "google.com", "googleapis.com", "gstatic.com", "googletagmanager.com",
    "google-analytics.com", "doubleclick.net", "facebook.com", "facebook.net",
    "fbcdn.net", "instagram.com", "twitter.com", "x.com", "linkedin.com",
    "youtube.com", "ytimg.com", "vimeo.com", "tiktok.com", "pinterest.com",
    "cloudflare.com", "cloudflareinsights.com", "jsdelivr.net", "cdnjs.com",
    "unpkg.com", "polyfill.io", "jquery.com", "bootstrapcdn.com",
    "fontawesome.com", "typekit.net", "fonts.com", "googleadservices.com",
    "cookiebot.com", "cookiefirst.com", "usercentrics.eu", "onetrust.com",
    "hotjar.com", "clarity.ms", "recaptcha.net", "gravatar.com", "w.org",
    "schema.org", "googletagservices.com", "addthis.com", "sharethis.com",
})

# First path segments too generic to identify anything.
_NOISE_TOKENS = frozenset({
    "css", "js", "img", "image", "images", "media", "assets", "asset", "static",
    "build", "dist", "public", "files", "fonts", "font", "favicon.ico", "style",
    "styles", "script", "scripts", "themes", "lib", "libs", "vendor", "storage",
    "uploads", "upload", "content", "data", "resources", "res", "cdn", "common",
    "shared", "core", "main", "app", "web", "site", "default", "html", "es", "nl",
    "de", "fr", "en",
})

# Known framework/CMS tokens findable in raw HTML. Each maps to a canonical marker
# value; presence is binary per domain. (wp-content lives in path_token already, but
# the explicit token catches inlined/absolute references on heavily proxied sites.)
_JS_MARKERS: tuple[tuple[str, str], ...] = (
    ("__next_data__", "nextjs"),
    ("__nuxt__", "nuxt"),
    ("window.__nuxt", "nuxt"),
    ("livewire", "livewire"),
    ("data-drupal-selector", "drupal"),
    ("drupal-settings-json", "drupal"),
    ("/sites/default/files", "drupal"),
    ("typo3conf", "typo3"),
    ("typo3temp", "typo3"),
    ("fileadmin/", "typo3"),
    ("/wp-content/", "wordpress"),
    ("/wp-json/", "wordpress"),
    ("joomla", "joomla"),
    ("com_content", "joomla"),
    ("sulu", "sulu"),
    ("craftcms", "craftcms"),
    ("data-craft", "craftcms"),
    ("shopware", "shopware"),
    ("prestashop", "prestashop"),
    ("magento", "magento"),
    ("woocommerce", "woocommerce"),
    ("squarespace", "squarespace"),
    ("webflow", "webflow"),
    ("wixstatic.com", "wix"),
    ("wix.com", "wix"),
    ("jimdo", "jimdo"),
    ("jouwweb", "jouwweb"),
    ("webnode", "webnode"),
    ("duda", "duda"),
    ("dudaone", "duda"),
    ("umbraco", "umbraco"),
    ("kirby", "kirby"),
    ("processwire", "processwire"),
    ("modx", "modx"),
    ("contao", "contao"),
    ("concrete5", "concrete5"),
    ("silverstripe", "silverstripe"),
    ("octobercms", "octobercms"),
    ("statamic", "statamic"),
    ("elementor", "elementor"),
    # Divi needs a STRICT marker — bare "divi" substring-matches Dutch words
    # ("divisie", "individuele") and false-fired on 15/122 NL dealers (2026-06-10).
    ("/themes/divi", "divi-theme"),
    ("et_pb_", "divi-theme"),
    ("gatsby", "gatsby"),
    ("data-sveltekit", "sveltekit"),
    ("ng-version", "angular"),
    ("data-vue-app", "vue"),
)


def _norm(value: str) -> str:
    """Lowercase, strip version digits/punctuation runs → one comparable token."""
    v = re.sub(r"[\d]+(?:\.[\d]+)*", "", value.lower())
    v = re.sub(r"[^a-z ._-]", "", v)
    return re.sub(r"\s+", " ", v).strip(" ._-")


def _registrable(host: str) -> str:
    """Last two DNS labels — good enough for EU TLDs this pipeline scopes to."""
    labels = host.lower().strip(".").split(".")
    return ".".join(labels[-2:]) if len(labels) >= 2 else host.lower()


def extract_markers(html: str, *, site_host: str) -> frozenset[tuple[str, str]]:
    """All platform markers found in ``html`` for a site served from ``site_host``.

    Returns ``(kind, value)`` pairs, deduplicated. Pure — no network, no exceptions
    for garbage input (empty/binary-ish HTML yields an empty set).
    """
    if not html:
        return frozenset()
    out: set[tuple[str, str]] = set()
    low = html.lower()
    site_reg = _registrable(site_host)

    for m in _GENERATOR_RE.finditer(html):
        raw = m.group(1) or m.group(2) or ""
        norm = _norm(raw)
        if norm:
            out.add(("generator", norm))

    for m in _POWERED_RE.finditer(html):
        norm = _norm(m.group(1))
        if len(norm) >= 3:
            out.add(("powered_by", norm))

    for m in _SRC_RE.finditer(html):
        url = m.group(1)
        if url.startswith("data:") or url.startswith("mailto:") or url.startswith("tel:"):
            continue
        if url.startswith("//"):
            url = "https:" + url
        if url.startswith(("http://", "https://")):
            host = urlparse(url).netloc.split("@")[-1].split(":")[0]
            if not host:
                continue
            reg = _registrable(host)
            if reg == site_reg or reg in _NOISE_HOSTS:
                continue
            out.add(("ext_host", reg))
        elif url.startswith("/") and not url.startswith("//"):
            seg = url.split("/", 2)[1].split("?")[0].lower()
            if seg and seg not in _NOISE_TOKENS and 2 <= len(seg) <= 30:
                out.add(("path_token", seg))

    for needle, family in _JS_MARKERS:
        if needle in low:
            out.add(("js_marker", family))

    return frozenset(out)


def aggregate_markers(
    per_domain: dict[str, frozenset[tuple[str, str]]],
    *,
    min_domains: int = 2,
    sample_size: int = 8,
) -> list[dict]:
    """Rank markers by how many DOMAINS share them (a platform = a shared marker).

    Returns ``[{kind, value, domains, sample}]`` sorted by reach desc — the shortlist
    a signature author works from. Markers below ``min_domains`` are noise and drop.
    """
    counts: Counter[tuple[str, str]] = Counter()
    samples: dict[tuple[str, str], list[str]] = defaultdict(list)
    for domain, markers in per_domain.items():
        for marker in markers:
            counts[marker] += 1
            if len(samples[marker]) < sample_size:
                samples[marker].append(domain)
    return [
        {"kind": kind, "value": value, "domains": n, "sample": sorted(samples[(kind, value)])}
        for (kind, value), n in counts.most_common()
        if n >= min_domains
    ]
