package syntheticapi

import (
	"os"
	"testing"

	"github.com/tensorplex-labs/dojo/internal/config"
)

// Integration test that queries a real Synthetic API. This test is skipped unless
// the SYNTHETIC_API_URL environment variable is set to the API base URL.
func TestSyntheticApi_Integration(t *testing.T) {
	url := os.Getenv("SYNTHETIC_API_URL")
	if url == "" {
		t.Skip("SYNTHETIC_API_URL not set; skipping integration test")
	}

	cfg := &config.SyntheticApiEnvConfig{SyntheticApiUrl: url}
	sa, err := NewSyntheticApi(cfg)
	if err != nil {
		t.Fatalf("NewSyntheticApi failed: %v", err)
	}

	q, err := sa.GetQuestion()
	if err != nil {
		t.Fatalf("GetQuestion failed: %v", err)
	}
	if q.Qa_Id == "" {
		t.Fatalf("GetQuestion returned empty qa_id: %+v", q)
	}

	_, err = sa.GetAnswer(q.Qa_Id)
	if err != nil {
		t.Fatalf("GetAnswer failed: %v", err)
	}

	// OrderAnswer may accept the prompt; ensure it doesn't error.
	_, err = sa.OrderAnswer(q.Prompt)
	if err != nil {
		t.Fatalf("OrderAnswer failed: %v", err)
	}
}
