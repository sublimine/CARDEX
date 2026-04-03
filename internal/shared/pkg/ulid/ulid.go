package ulid

import (
	"math/rand"
	"time"

	ulidpkg "github.com/oklog/ulid/v2"
)

// New generates a new ULID string.
func New() string {
	entropy := rand.New(rand.NewSource(time.Now().UnixNano()))
	ms := ulidpkg.Timestamp(time.Now())
	return ulidpkg.MustNew(ms, entropy).String()
}
