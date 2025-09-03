package syntheticapi

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strconv"
	"testing"

	"github.com/tensorplex-labs/dojo/internal/config"
)

func TestNewSyntheticApi_NilConfig(t *testing.T) {
	_, err := NewSyntheticApi(nil)
	if err == nil {
		t.Fatal("expected error when cfg is nil")
	}
}

func TestGetQuestion_Success(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet || r.URL.Path != "/api/generate-question" {
			w.WriteHeader(http.StatusNotFound)
			return
		}
		resp := GenerateQuestionResponse{Success: true, Prompt: "what?", QaID: "qa-1"}
		w.Header().Set("Content-Type", "application/json")
		if err := json.NewEncoder(w).Encode(resp); err != nil {
			panic(err)
		}
	}))
	defer ts.Close()

	cfg := &config.SyntheticApiEnvConfig{SyntheticApiUrl: ts.URL}
	sa, err := NewSyntheticApi(cfg)
	if err != nil {
		t.Fatalf("unexpected new error: %v", err)
	}

	out, err := sa.GetQuestion()
	if err != nil {
		t.Fatalf("GetQuestion failed: %v", err)
	}
	if out.Prompt != "what?" || out.QaID != "qa-1" || !out.Success {
		t.Fatalf("unexpected response: %+v", out)
	}
}

func TestGetQuestion_Non2xx(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		if _, err := fmt.Fprint(w, "boom"); err != nil {
			panic(err)
		}
	}))
	defer ts.Close()

	cfg := &config.SyntheticApiEnvConfig{SyntheticApiUrl: ts.URL}
	sa, err := NewSyntheticApi(cfg)
	if err != nil {
		panic(err)
	}
	_, err = sa.GetQuestion()
	if err == nil {
		t.Fatal("expected error for non-2xx response")
	}
}

func TestGetCodegenAnswer_Success(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || r.URL.Path != "/api/generate-answer" {
			w.WriteHeader(http.StatusNotFound)
			return
		}
		var body map[string]string
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			w.WriteHeader(http.StatusBadRequest)
			return
		}
		qa := body["qa_id"]
		if qa != "qa-1" {
			w.WriteHeader(http.StatusBadRequest)
			return
		}
		resp := GenerateAnswerResponse[CodegenAnswer]{Success: true, Answer: CodegenAnswer{Prompt: "p"}}
		w.Header().Set("Content-Type", "application/json")
		if err := json.NewEncoder(w).Encode(resp); err != nil {
			panic(err)
		}
	}))
	defer ts.Close()

	cfg := &config.SyntheticApiEnvConfig{SyntheticApiUrl: ts.URL}
	sa, err := NewSyntheticApi(cfg)
	if err != nil {
		panic(err)
	}
	out, err := sa.GetCodegenAnswer("qa-1")
	if err != nil {
		t.Fatalf("GetCodegenAnswer failed: %v", err)
	}
	if !out.Success {
		t.Fatalf("unexpected response: %+v", out)
	}
}

func TestGetQuestionAugment_Success(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || r.URL.Path != "/api/get-question-augment" {
			w.WriteHeader(http.StatusNotFound)
			return
		}
		var body map[string]string
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			w.WriteHeader(http.StatusBadRequest)
			return
		}
		base := body["question"]
		num := body["num_augments"]
		n, err := strconv.Atoi(num)
		if err != nil {
			panic(err)
		}
		if base == "" || n <= 0 {
			w.WriteHeader(http.StatusBadRequest)
			return
		}
		aug := make([]string, n)
		for i := 0; i < n; i++ {
			aug[i] = fmt.Sprintf("%s-%d", base, i)
		}
		resp := AugmentQuestionResponse{Success: true, Augments: aug}
		w.Header().Set("Content-Type", "application/json")
		if err := json.NewEncoder(w).Encode(resp); err != nil {
			panic(err)
		}
	}))
	defer ts.Close()

	cfg := &config.SyntheticApiEnvConfig{SyntheticApiUrl: ts.URL}
	sa, err := NewSyntheticApi(cfg)
	if err != nil {
		panic(err)
	}
	out, err := sa.GetQuestionAugment("hello", 3)
	if err != nil {
		t.Fatalf("GetQuestionAugment failed: %v", err)
	}
	if len(out.Augments) != 3 || out.Augments[0] != "hello-0" {
		t.Fatalf("unexpected augments: %+v", out.Augments)
	}
}

func TestOrderAnswer_Success(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || r.URL.Path != "/api/order-answer" {
			w.WriteHeader(http.StatusNotFound)
			return
		}
		var body map[string]string
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			w.WriteHeader(http.StatusBadRequest)
			return
		}
		q := body["question"]
		if q == "" {
			w.WriteHeader(http.StatusBadRequest)
			return
		}
		resp := OrderAnswerResponse{Success: true, AnswerID: q + "-ordered"}
		w.Header().Set("Content-Type", "application/json")
		if err := json.NewEncoder(w).Encode(resp); err != nil {
			panic(err)
		}
	}))
	defer ts.Close()

	cfg := &config.SyntheticApiEnvConfig{SyntheticApiUrl: ts.URL}
	sa, err := NewSyntheticApi(cfg)
	if err != nil {
		panic(err)
	}
	out, err := sa.OrderAnswer("how")
	if err != nil {
		t.Fatalf("OrderAnswer failed: %v", err)
	}
	if out.AnswerID != "how-ordered" {
		t.Fatalf("unexpected response: %+v", out)
	}
}
