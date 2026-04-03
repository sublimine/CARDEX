// Package reservation implements atomic vehicle reservation via Redis Lua mutex.
package reservation

import (
	"context"
	"fmt"
	"strconv"
	"time"

	"github.com/redis/go-redis/v9"
)

const vehicleStatePrefix = "vehicle_state:"

// ReservationResult holds the result of a reservation attempt.
type ReservationResult struct {
	Granted       bool
	ReservationID string
	ExpiresAt     time.Time
}

// reserveScript atomically checks vehicle_state and sets reservation if free or same entity.
// KEYS[1] = vehicle_state:<vehicleULID>
// ARGV[1]=entityULID, ARGV[2]=quoteID, ARGV[3]=ttl_ms, ARGV[4]=reserved_at, ARGV[5]=vehicleULID
// Returns: {1, reservation_id} on success, {0} on denied.
const reserveScript = `
local key = KEYS[1]
local entity_ulid = ARGV[1]
local quote_id = ARGV[2]
local ttl_ms = tonumber(ARGV[3])
local reserved_at = ARGV[4]
local vehicle_ulid = ARGV[5]

local reserved_by = redis.call("HGET", key, "reserved_by")
if reserved_by ~= false and reserved_by ~= entity_ulid then
    return {0}
end

redis.call("HSET", key, "reserved_by", entity_ulid, "quote_id", quote_id, "reserved_at", reserved_at)
redis.call("PEXPIRE", key, ttl_ms)

local reservation_id = vehicle_ulid .. ":" .. entity_ulid .. ":" .. reserved_at
return {1, reservation_id}
`

// releaseScript atomically removes reservation only if reserved_by matches.
// KEYS[1] = vehicle_state:<vehicleULID>
// ARGV[1] = entityULID
// Returns: 1 on success, -1 if wrong entity, 0 if not reserved.
const releaseScript = `
local key = KEYS[1]
local entity_ulid = ARGV[1]

local reserved_by = redis.call("HGET", key, "reserved_by")
if reserved_by == false then
    return 0
end
if reserved_by ~= entity_ulid then
    return -1
end

redis.call("HDEL", key, "reserved_by", "quote_id", "reserved_at")
return 1
`

// Mutex provides atomic vehicle reservation via Redis Lua.
type Mutex struct {
	rdb        *redis.Client
	reserveSHA string
	releaseSHA string
}

// New creates a Mutex using the given Redis client.
// Loads the Lua script SHAs if available; falls back to EVAL on each call.
func New(rdb *redis.Client) *Mutex {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	reserveSHA, _ := rdb.ScriptLoad(ctx, reserveScript).Result()
	releaseSHA, _ := rdb.ScriptLoad(ctx, releaseScript).Result()

	return &Mutex{rdb: rdb, reserveSHA: reserveSHA, releaseSHA: releaseSHA}
}

// Reserve atomically reserves a vehicle for the given entity.
// If the vehicle has no reservation or is already reserved by the same entity, Granted=true.
// If reserved by a different entity, Granted=false.
func (m *Mutex) Reserve(ctx context.Context, vehicleULID string, entityULID string, quoteID string, ttl time.Duration) (ReservationResult, error) {
	key := vehicleStatePrefix + vehicleULID
	ttlMs := ttl.Milliseconds()
	now := time.Now()
	reservedAt := strconv.FormatInt(now.UnixMilli(), 10)
	expiresAt := now.Add(ttl)

	args := []interface{}{entityULID, quoteID, ttlMs, reservedAt, vehicleULID}

	var result []interface{}
	var err error

	if m.reserveSHA != "" {
		result, err = m.rdb.EvalSha(ctx, m.reserveSHA, []string{key}, args...).Slice()
	} else {
		result, err = m.rdb.Eval(ctx, reserveScript, []string{key}, args...).Slice()
	}

	if err != nil {
		return ReservationResult{}, fmt.Errorf("reservation: %w", err)
	}

	granted := int64(0)
	if len(result) > 0 {
		if g, ok := result[0].(int64); ok {
			granted = g
		}
	}

	if granted == 0 {
		return ReservationResult{Granted: false}, nil
	}

	reservationID := ""
	if len(result) > 1 {
		if rid, ok := result[1].(string); ok {
			reservationID = rid
		}
	}

	return ReservationResult{
		Granted:       true,
		ReservationID: reservationID,
		ExpiresAt:     expiresAt,
	}, nil
}

// Release removes the reservation only if reserved_by matches entityULID.
// Returns error if reserved by a different entity.
func (m *Mutex) Release(ctx context.Context, vehicleULID string, entityULID string) error {
	key := vehicleStatePrefix + vehicleULID

	var result int64
	var err error

	if m.releaseSHA != "" {
		result, err = m.rdb.EvalSha(ctx, m.releaseSHA, []string{key}, entityULID).Int64()
	} else {
		result, err = m.rdb.Eval(ctx, releaseScript, []string{key}, entityULID).Int64()
	}

	if err != nil {
		return fmt.Errorf("reservation: %w", err)
	}

	if result == -1 {
		return fmt.Errorf("reservation: release denied, vehicle reserved by different entity")
	}

	return nil
}
