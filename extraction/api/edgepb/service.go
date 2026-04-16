package edgepb

import (
	"context"
	"encoding/json"

	"google.golang.org/grpc"
	"google.golang.org/grpc/encoding"
)

func init() {
	// Register a JSON codec under the name "proto" so that grpc uses JSON
	// serialisation for all EdgePush messages in the MVP.  This allows the
	// server and tests to function without running protoc.
	//
	// Upgrade path: once `make proto` has been run the generated types
	// implement proto.Message and the default proto codec takes over;
	// remove this init() block at that point.
	encoding.RegisterCodec(jsonCodec{})
}

// jsonCodec is a gRPC codec that marshals/unmarshals using encoding/json.
// It registers itself under the name "proto" to override the default codec.
type jsonCodec struct{}

func (jsonCodec) Name() string { return "proto" }

func (jsonCodec) Marshal(v interface{}) ([]byte, error) {
	return json.Marshal(v)
}

func (jsonCodec) Unmarshal(data []byte, v interface{}) error {
	return json.Unmarshal(data, v)
}

// ─── Server interface ────────────────────────────────────────────────────────

// EdgePushServer is the server-side interface for the EdgePush service.
// Implement this interface and call RegisterEdgePushServer to register it.
type EdgePushServer interface {
	// PushListings receives a stream of ListingBatch messages and returns a
	// PushResponse summarising accepted/rejected counts.
	PushListings(EdgePush_PushListingsServer) error
	// Heartbeat returns the server clock.
	Heartbeat(context.Context, *HeartbeatRequest) (*HeartbeatResponse, error)
}

// EdgePush_PushListingsServer is the server-side stream for PushListings.
type EdgePush_PushListingsServer interface {
	SendAndClose(*PushResponse) error
	Recv() (*ListingBatch, error)
	grpc.ServerStream
}

type edgePushPushListingsServer struct{ grpc.ServerStream }

func (s *edgePushPushListingsServer) SendAndClose(r *PushResponse) error {
	return s.ServerStream.SendMsg(r)
}

func (s *edgePushPushListingsServer) Recv() (*ListingBatch, error) {
	m := new(ListingBatch)
	if err := s.ServerStream.RecvMsg(m); err != nil {
		return nil, err
	}
	return m, nil
}

// ─── Client interface ────────────────────────────────────────────────────────

// EdgePushClient is the client-side interface for the EdgePush service.
type EdgePushClient interface {
	PushListings(ctx context.Context, opts ...grpc.CallOption) (EdgePush_PushListingsClient, error)
	Heartbeat(ctx context.Context, req *HeartbeatRequest, opts ...grpc.CallOption) (*HeartbeatResponse, error)
}

// EdgePush_PushListingsClient is the client-side stream for PushListings.
type EdgePush_PushListingsClient interface {
	Send(*ListingBatch) error
	CloseAndRecv() (*PushResponse, error)
	grpc.ClientStream
}

type edgePushPushListingsClient struct{ grpc.ClientStream }

func (c *edgePushPushListingsClient) Send(b *ListingBatch) error {
	return c.ClientStream.SendMsg(b)
}

func (c *edgePushPushListingsClient) CloseAndRecv() (*PushResponse, error) {
	if err := c.ClientStream.CloseSend(); err != nil {
		return nil, err
	}
	r := new(PushResponse)
	if err := c.ClientStream.RecvMsg(r); err != nil {
		return nil, err
	}
	return r, nil
}

// ─── Client constructor ──────────────────────────────────────────────────────

type edgePushClient struct{ cc grpc.ClientConnInterface }

// NewEdgePushClient returns a new EdgePushClient backed by cc.
func NewEdgePushClient(cc grpc.ClientConnInterface) EdgePushClient {
	return &edgePushClient{cc}
}

func (c *edgePushClient) PushListings(ctx context.Context, opts ...grpc.CallOption) (EdgePush_PushListingsClient, error) {
	stream, err := c.cc.NewStream(ctx, &_EdgePush_serviceDesc.Streams[0], "/cardex.edge.EdgePush/PushListings", opts...)
	if err != nil {
		return nil, err
	}
	return &edgePushPushListingsClient{stream}, nil
}

func (c *edgePushClient) Heartbeat(ctx context.Context, req *HeartbeatRequest, opts ...grpc.CallOption) (*HeartbeatResponse, error) {
	out := new(HeartbeatResponse)
	err := c.cc.Invoke(ctx, "/cardex.edge.EdgePush/Heartbeat", req, out, opts...)
	if err != nil {
		return nil, err
	}
	return out, nil
}

// ─── Server registration ─────────────────────────────────────────────────────

// RegisterEdgePushServer registers the given EdgePushServer with s.
func RegisterEdgePushServer(s grpc.ServiceRegistrar, srv EdgePushServer) {
	s.RegisterService(&_EdgePush_serviceDesc, srv)
}

func _EdgePush_PushListings_Handler(srv interface{}, stream grpc.ServerStream) error {
	return srv.(EdgePushServer).PushListings(&edgePushPushListingsServer{stream})
}

func _EdgePush_Heartbeat_Handler(srv interface{}, ctx context.Context, dec func(interface{}) error, interceptor grpc.UnaryServerInterceptor) (interface{}, error) {
	in := new(HeartbeatRequest)
	if err := dec(in); err != nil {
		return nil, err
	}
	if interceptor == nil {
		return srv.(EdgePushServer).Heartbeat(ctx, in)
	}
	info := &grpc.UnaryServerInfo{Server: srv, FullMethod: "/cardex.edge.EdgePush/Heartbeat"}
	handler := func(ctx context.Context, req interface{}) (interface{}, error) {
		return srv.(EdgePushServer).Heartbeat(ctx, req.(*HeartbeatRequest))
	}
	return interceptor(ctx, in, info, handler)
}

var _EdgePush_serviceDesc = grpc.ServiceDesc{
	ServiceName: "cardex.edge.EdgePush",
	HandlerType: (*EdgePushServer)(nil),
	Methods: []grpc.MethodDesc{
		{
			MethodName: "Heartbeat",
			Handler:    _EdgePush_Heartbeat_Handler,
		},
	},
	Streams: []grpc.StreamDesc{
		{
			StreamName:    "PushListings",
			Handler:       _EdgePush_PushListings_Handler,
			ClientStreams: true,
		},
	},
	Metadata: "edge_push.proto",
}
