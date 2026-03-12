package vies

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestClient_CheckVAT(t *testing.T) {
	tests := []struct {
		name        string
		handler     http.HandlerFunc
		timeout     time.Duration
		wantValid   bool
		wantName    string
		wantErr     bool
		errSubstr   string
		errSubstrs  []string
	}{
		{
			name: "valid VAT",
			handler: func(w http.ResponseWriter, r *http.Request) {
				w.Header().Set("Content-Type", "text/xml")
				w.Write([]byte(`<?xml version="1.0"?><soap:Envelope><soap:Body><checkVatResponse><valid>true</valid><name>BMW AG</name></checkVatResponse></soap:Body></soap:Envelope>`))
			},
			timeout:   5 * time.Second,
			wantValid: true,
			wantName:  "BMW AG",
			wantErr:   false,
		},
		{
			name: "invalid VAT",
			handler: func(w http.ResponseWriter, r *http.Request) {
				w.Header().Set("Content-Type", "text/xml")
				w.Write([]byte(`<?xml version="1.0"?><soap:Envelope><soap:Body><checkVatResponse><valid>false</valid></checkVatResponse></soap:Body></soap:Envelope>`))
			},
			timeout:   5 * time.Second,
			wantValid: false,
			wantName:  "",
			wantErr:   false,
		},
		{
			name: "timeout",
			handler: func(w http.ResponseWriter, r *http.Request) {
				time.Sleep(2 * time.Second)
				w.Write([]byte(`<valid>true</valid>`))
			},
			timeout:    100 * time.Millisecond,
			wantValid:  false,
			wantName:   "",
			wantErr:    true,
			errSubstrs: []string{"timeout", "deadline"},
		},
		{
			name: "server error 500",
			handler: func(w http.ResponseWriter, r *http.Request) {
				w.WriteHeader(http.StatusInternalServerError)
				w.Write([]byte("internal server error"))
			},
			timeout:   5 * time.Second,
			wantValid: false,
			wantName:  "",
			wantErr:   true,
			errSubstr: "500",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			server := httptest.NewServer(tt.handler)
			defer server.Close()

			client := New(tt.timeout)
			client.BaseURL = server.URL

			valid, name, err := client.CheckVAT(context.Background(), "DE", "123456789")
			if tt.wantErr {
				if err == nil {
					t.Errorf("CheckVAT() expected error, got nil")
					return
				}
				if tt.errSubstr != "" && !strings.Contains(err.Error(), tt.errSubstr) {
					t.Errorf("CheckVAT() error = %v, want substring %q", err, tt.errSubstr)
				}
				if len(tt.errSubstrs) > 0 {
					got := err.Error()
					matched := false
					for _, sub := range tt.errSubstrs {
						if strings.Contains(got, sub) {
							matched = true
							break
						}
					}
					if !matched {
						t.Errorf("CheckVAT() error = %v, want substring %v", err, tt.errSubstrs)
					}
				}
				return
			}
			if err != nil {
				t.Errorf("CheckVAT() unexpected error: %v", err)
				return
			}
			if valid != tt.wantValid {
				t.Errorf("CheckVAT() valid = %v, want %v", valid, tt.wantValid)
			}
			if name != tt.wantName {
				t.Errorf("CheckVAT() name = %q, want %q", name, tt.wantName)
			}
		})
	}
}
