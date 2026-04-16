// Package server implements the E12 Edge Push gRPC server.
//
// # Architecture
//
//   - Dealers authenticate via their dealer_id + api_key embedded in each
//     ListingBatch message.  The api_key is validated against the SHA-256 hash
//     stored in the edge_dealers SQLite table.
//   - Listings are rate-limited to 1000 per dealer per minute.
//   - Accepted listings are written to the edge_inventory_staging table and
//     converted to pipeline.VehicleRaw format for immediate persistence via
//     the extraction storage layer.
//   - Rejected listings get a per-VIN reason in the PushResponse.
//   - Prometheus metrics: cardex_edge_push_listings_total{dealer,status},
//     cardex_edge_push_latency_seconds.
//
// # TLS
//
// The server requires TLS in production.  Pass grpc.Creds(credentials.NewTLS(cfg))
// in the server options.  For tests, use insecure.NewCredentials().
package server

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net"
	"time"

	"github.com/oklog/ulid/v2"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	_ "modernc.org/sqlite"

	"cardex.eu/extraction/api/edgepb"
	"cardex.eu/extraction/internal/pipeline"
)

// ─── Prometheus metrics ───────────────────────────────────────────────────────

var (
	metricListingsTotal = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "cardex_edge_push_listings_total",
		Help: "Total listings received via Edge Push, partitioned by dealer and status.",
	}, []string{"dealer", "status"})

	metricLatency = promauto.NewHistogramVec(prometheus.HistogramOpts{
		Name:    "cardex_edge_push_latency_seconds",
		Help:    "End-to-end latency of PushListings RPC calls.",
		Buckets: prometheus.DefBuckets,
	}, []string{"dealer"})
)

// ─── Server ──────────────────────────────────────────────────────────────────

// Storage is the subset of pipeline.Storage required by the Edge Push server.
type Storage interface {
	PersistVehicles(ctx context.Context, dealerID string, vehicles []*pipeline.VehicleRaw) (int, error)
}

// Server implements edgepb.EdgePushServer.
type Server struct {
	db      *DB
	store   Storage
	rl      *rateLimiter
	log     *slog.Logger
	nowFn   func() time.Time // injectable for tests
}

// New constructs an Edge Push server.
//   - db is the edge_dealers / edge_inventory_staging SQLite store.
//   - store is used to persist accepted vehicles to the knowledge graph.
func New(db *DB, store Storage) *Server {
	return &Server{
		db:    db,
		store: store,
		rl:    newRateLimiter(1000),
		log:   slog.Default().With("component", "edge-push-server"),
		nowFn: time.Now,
	}
}

// ─── PushListings ─────────────────────────────────────────────────────────────

// PushListings implements edgepb.EdgePushServer.
func (s *Server) PushListings(stream edgepb.EdgePush_PushListingsServer) error {
	var (
		dealerID    string
		authenticated bool
		accepted    int32
		rejected    int32
		rejections  []*edgepb.RejectionDetail
		allVehicles []*pipeline.VehicleRaw
		start       = s.nowFn()
	)

	for {
		batch, err := stream.Recv()
		if err != nil {
			// io.EOF is the normal stream end.
			break
		}

		// ── First batch: authenticate ────────────────────────────────────────
		if !authenticated {
			dealerID = batch.DealerID
			ok, authErr := s.db.ValidateAPIKey(stream.Context(), batch.DealerID, batch.APIKey)
			if authErr != nil {
				s.log.Warn("ValidateAPIKey error", "dealer_id", batch.DealerID, "err", authErr)
				return status.Errorf(codes.Internal, "authentication error")
			}
			if !ok {
				return status.Errorf(codes.Unauthenticated, "invalid dealer_id or api_key")
			}
			authenticated = true
		} else if batch.DealerID != dealerID {
			// Dealer ID must not change mid-stream.
			return status.Errorf(codes.InvalidArgument, "dealer_id changed mid-stream")
		}

		// ── Rate limit ────────────────────────────────────────────────────────
		if !s.rl.Allow(dealerID, len(batch.Listings)) {
			for _, l := range batch.Listings {
				metricListingsTotal.WithLabelValues(dealerID, "rejected").Inc()
				rejections = append(rejections, &edgepb.RejectionDetail{
					VIN:    l.VIN,
					Reason: "rate_limit_exceeded",
				})
				rejected++
			}
			continue
		}

		// ── Validate and convert ──────────────────────────────────────────────
		for _, l := range batch.Listings {
			if err := validateListing(l); err != nil {
				metricListingsTotal.WithLabelValues(dealerID, "rejected").Inc()
				rejections = append(rejections, &edgepb.RejectionDetail{
					VIN:    l.VIN,
					Reason: err.Error(),
				})
				rejected++
				continue
			}
			allVehicles = append(allVehicles, listingToVehicleRaw(l))
			metricListingsTotal.WithLabelValues(dealerID, "accepted").Inc()
			accepted++
		}
	}

	if !authenticated {
		return status.Errorf(codes.Unauthenticated, "no batches received")
	}

	// ── Persist accepted vehicles ─────────────────────────────────────────────
	if len(allVehicles) > 0 {
		// Mark extraction method before persisting.
		for _, v := range allVehicles {
			if v.AdditionalFields == nil {
				v.AdditionalFields = make(map[string]interface{})
			}
			v.AdditionalFields["extraction_method"] = "e12_edge_push"
		}

		// Stage the raw JSON for the e12_edge strategy to pick up.
		if err := s.stageVehicles(stream.Context(), dealerID, allVehicles); err != nil {
			s.log.Warn("stageVehicles failed", "dealer_id", dealerID, "err", err)
		}

		// Also persist directly via storage (immediate path).
		if s.store != nil {
			if _, err := s.store.PersistVehicles(stream.Context(), dealerID, allVehicles); err != nil {
				s.log.Warn("PersistVehicles failed", "dealer_id", dealerID, "err", err)
			}
		}
	}

	metricLatency.WithLabelValues(dealerID).Observe(s.nowFn().Sub(start).Seconds())

	s.log.Info("PushListings complete",
		"dealer_id", dealerID,
		"accepted", accepted,
		"rejected", rejected,
	)

	return stream.SendAndClose(&edgepb.PushResponse{
		Accepted:   accepted,
		Rejected:   rejected,
		Rejections: rejections,
	})
}

// ─── Heartbeat ────────────────────────────────────────────────────────────────

// Heartbeat implements edgepb.EdgePushServer.
func (s *Server) Heartbeat(_ context.Context, req *edgepb.HeartbeatRequest) (*edgepb.HeartbeatResponse, error) {
	s.log.Debug("heartbeat", "dealer_id", req.DealerID)
	return &edgepb.HeartbeatResponse{
		ServerTimeUnix: s.nowFn().Unix(),
	}, nil
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

func validateListing(l *edgepb.VehicleListing) error {
	if l.VIN == "" {
		return fmt.Errorf("vin required")
	}
	if len(l.VIN) != 17 {
		return fmt.Errorf("vin must be 17 characters, got %d", len(l.VIN))
	}
	if l.Make == "" {
		return fmt.Errorf("make required")
	}
	if l.Model == "" {
		return fmt.Errorf("model required")
	}
	if l.Year < 1900 || l.Year > int32(time.Now().Year()+2) {
		return fmt.Errorf("year %d out of range", l.Year)
	}
	return nil
}

func listingToVehicleRaw(l *edgepb.VehicleListing) *pipeline.VehicleRaw {
	v := &pipeline.VehicleRaw{
		SourceURL:  l.SourceURL,
		ImageURLs:  l.ImageURLs,
	}
	if l.VIN != "" {
		v.VIN = &l.VIN
	}
	if l.Make != "" {
		v.Make = &l.Make
	}
	if l.Model != "" {
		v.Model = &l.Model
	}
	if l.Year != 0 {
		yr := int(l.Year)
		v.Year = &yr
	}
	if l.PriceCents != 0 {
		price := float64(l.PriceCents) / 100.0
		v.PriceGross = &price
	}
	if l.Currency != "" {
		v.Currency = &l.Currency
	}
	if l.MileageKm != 0 {
		km := int(l.MileageKm)
		v.Mileage = &km
	}
	if l.FuelType != "" {
		v.FuelType = &l.FuelType
	}
	if l.Transmission != "" {
		v.Transmission = &l.Transmission
	}
	if l.Color != "" {
		v.Color = &l.Color
	}
	if l.Description != "" {
		v.AdditionalFields = map[string]interface{}{"description": l.Description}
	}
	return v
}

// stageVehicles writes allVehicles as JSON to the edge_inventory_staging table.
func (s *Server) stageVehicles(ctx context.Context, dealerID string, vehicles []*pipeline.VehicleRaw) error {
	data, err := json.Marshal(vehicles)
	if err != nil {
		return err
	}
	_, err = s.db.db.ExecContext(ctx,
		`INSERT INTO edge_inventory_staging (id, dealer_id, vehicles_json, received_at)
		 VALUES (?, ?, ?, ?)`,
		ulid.Make().String(), dealerID, string(data), time.Now().UTC().Format(time.RFC3339),
	)
	return err
}

// ─── Listener helper ─────────────────────────────────────────────────────────

// ListenAndServe starts the gRPC server on addr with the provided options.
// This is a blocking call; cancel ctx to stop.
func ListenAndServe(ctx context.Context, addr string, srv *Server, opts ...grpc.ServerOption) error {
	lis, err := net.Listen("tcp", addr)
	if err != nil {
		return fmt.Errorf("edge-push-server: listen %s: %w", addr, err)
	}

	gs := grpc.NewServer(opts...)
	edgepb.RegisterEdgePushServer(gs, srv)

	go func() {
		<-ctx.Done()
		gs.GracefulStop()
	}()

	slog.Info("edge-push-server listening", "addr", addr)
	return gs.Serve(lis)
}
