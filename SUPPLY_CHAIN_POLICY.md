# Supply Chain Security Policy

## Dependency review process

Before adding any new direct dependency:

1. Check stars: must have >500 GitHub stars OR be from a known org (Google, Hashicorp, etc.)
2. Check maintenance: last commit within 12 months
3. Check maintainers: prefer projects with >1 active maintainer
4. Check license: must be MIT, BSD, Apache 2.0, or MPL 2.0
5. Run govulncheck after adding: zero known vulnerabilities
6. Verify go.sum checksum: `GOFLAGS="-mod=verify" go build ./...`

## High-risk dependencies (monitor closely)

| Package | Risk | Mitigation |
|---------|------|------------|
| `modernc.org/sqlite` | Single maintainer (Thomas B.) | Pin version, have migration path to mattn/go-sqlite3 |
| `playwright-community/playwright-go` | Community fork, not official | Pin version, fallback to E12 if unavailable |
| `github.com/ledongthuc/pdf` | Small project, single maintainer | Pin version |
| `github.com/mohae/deepcopy` | Abandoned 2017 | Consider replacing with stdlib deep copy |

## Weekly scan

The `.forgejo/workflows/weekly-supply-chain.yml` runs every Monday.
Results are visible in Forgejo → Actions → Weekly Supply Chain Audit.
