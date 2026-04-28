package e13_vlm_vision

import (
	"context"
	"errors"
)

// MockClient is a deterministic VLMClient implementation for unit tests.
// It returns a pre-configured response or error without any network I/O.
//
// Usage:
//
//	mock := &MockClient{Response: `{"make":"BMW","model":"320d","year":2020}`}
//	extractor := New(cfg, mock, nil)
type MockClient struct {
	// Response is returned verbatim by SendImage when Err is nil.
	Response string

	// Err, if non-nil, is returned by SendImage instead of Response.
	Err error

	// Calls records how many times SendImage was called.
	Calls int
}

// ErrMockTimeout is a sentinel error that simulates a context deadline / VLM timeout.
var ErrMockTimeout = errors.New("mock: VLM timeout")

// SendImage records the call and returns the configured Response or Err.
// It does NOT inspect image or prompt — tests control behaviour via mock fields.
func (m *MockClient) SendImage(_ context.Context, _ []byte, _ string) (string, error) {
	m.Calls++
	if m.Err != nil {
		return "", m.Err
	}
	return m.Response, nil
}
