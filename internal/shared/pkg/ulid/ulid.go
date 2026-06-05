package ulid

import (
	"crypto/rand"
	"time"

	ulidpkg "github.com/oklog/ulid/v2"
)

// New generates a new ULID string using crypto/rand for entropy.
//
// Replaces math/rand seeded from time.Now() which produced predictable IDs
// when generation rate was high or the seed was guessable. ULIDs are used as
// primary keys across the monorepo (vehicle_record, dealer_entity, etc.) — a
// predictable ID would let an attacker enumerate or collide records.
func New() string {
	ms := ulidpkg.Timestamp(time.Now())
	return ulidpkg.MustNew(ms, rand.Reader).String()
}
