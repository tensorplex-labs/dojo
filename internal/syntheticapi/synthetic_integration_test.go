package syntheticapi

import (
	"fmt"
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

	cfg := &config.SyntheticAPIEnvConfig{SyntheticAPIUrl: url}
	sa, err := NewSyntheticAPI(cfg)
	if err != nil {
		t.Fatalf("NewSyntheticApi failed: %v", err)
	}

	q, err := sa.GetQuestion()
	if err != nil {
		t.Fatalf("GetQuestion failed: %v", err)
	}
	if q.QaID == "" {
		t.Fatalf("GetQuestion returned empty qa_id: %+v", q)
	}

	fmt.Printf("Got question: %+v\n", q)

	_, err = sa.GetCodegenAnswer(q.QaID)
	if err != nil {
		t.Fatalf("GetCodegenAnswer failed: %v", err)
	}

	_, err = sa.GetCodegenAnswer(q.AnsAugID)
	if err != nil {
		t.Fatalf("GetCodegenAnswer failed: %v", err)
	}

	_, err = sa.OrderAnswer(q.Prompt)
	if err != nil {
		t.Fatalf("OrderAnswer failed: %v", err)
	}
}
