// Package syntheticapi provides a client to interact with the local synthetic
// task/question generator service used by the validator.
package syntheticapi

import (
	"encoding/json"
	"fmt"
	"strconv"

	"github.com/bytedance/sonic"
	"github.com/go-resty/resty/v2"
	"github.com/rs/zerolog/log"

	"github.com/tensorplex-labs/dojo/internal/config"
)

func decodePossiblyStringified[T any](raw json.RawMessage, out *T) error {
	if len(raw) == 0 {
		return nil
	}
	if raw[0] == '"' {
		var sjson string
		if err := sonic.Unmarshal(raw, &sjson); err != nil {
			return fmt.Errorf("unquote: %w", err)
		}
		if err := sonic.Unmarshal([]byte(sjson), out); err != nil {
			return fmt.Errorf("decode stringified: %w", err)
		}
		return nil
	}
	if err := sonic.Unmarshal(raw, out); err != nil {
		return fmt.Errorf("decode: %w", err)
	}
	return nil
}

// SyntheticAPIInterface describes the synthetic API client methods used.
type SyntheticAPIInterface interface {
	GetQuestion() (GenerateQuestionResponse, error)
	GetCodegenAnswer(qaID string) (GenerateAnswerResponse[CodegenAnswer], error)
	GetQuestionAugment(baseQuestion string, numAugments int) (AugmentQuestionResponse, error)
	OrderAnswer(question string) (OrderAnswerResponse, error)
}

// SyntheticAPI wraps a REST client for the synthetic service.
type SyntheticAPI struct {
	cfg    *config.SyntheticAPIEnvConfig
	client *resty.Client
}

// NewSyntheticAPI creates a new synthetic API client bound to the configured URL.
func NewSyntheticAPI(cfg *config.SyntheticAPIEnvConfig) (*SyntheticAPI, error) {
	if cfg == nil {
		return nil, fmt.Errorf("configuration cannot be nil")
	}

	client := resty.New().
		SetBaseURL(cfg.SyntheticAPIUrl).
		SetJSONMarshaler(sonic.Marshal).
		SetJSONUnmarshaler(sonic.Unmarshal)

	return &SyntheticAPI{
		cfg:    cfg,
		client: client,
	}, nil
}

func (s *SyntheticAPI) postJSON(path string, payload, out any) (*resty.Response, error) {
	return s.client.R().
		SetHeader("Content-Type", "application/json").
		SetBody(payload).
		SetResult(out).
		Post(path)
}

// GetQuestion requests a new synthetic question.
func (s *SyntheticAPI) GetQuestion() (GenerateQuestionResponse, error) {
	var out GenerateQuestionResponse

	resp, err := s.client.R().
		SetResult(&out).
		Get("/api/generate-question")
	if err != nil {
		log.Error().Err(err).Msg("get-question request failed")
		return GenerateQuestionResponse{}, fmt.Errorf("get question: %w", err)
	}
	if resp.IsError() {
		log.Error().Int("status", resp.StatusCode()).Str("body", resp.String()).Msg("get-question non-2xx")
		return GenerateQuestionResponse{}, fmt.Errorf(
			"get-question status %d: %s",
			resp.StatusCode(), resp.String(),
		)
	}
	if !out.Success {
		return GenerateQuestionResponse{}, fmt.Errorf("get-question api returned success=false")
	}
	return out, nil
}

func (s *SyntheticAPI) fetchCodegenFromField(qaID, field string) (CodegenAnswer, error) {
	payload := map[string]string{"qa_id": qaID}
	type raw map[string]json.RawMessage
	var r raw
	resp, err := s.postJSON("/api/generate-answer", payload, &r)
	if err != nil {
		return CodegenAnswer{}, fmt.Errorf("generate answer: %w", err)
	}
	if resp.IsError() {
		return CodegenAnswer{}, fmt.Errorf("generate-answer status %d: %s", resp.StatusCode(), resp.String())
	}

	var ok bool
	if err := decodePossiblyStringified(r["success"], &ok); err != nil {
		return CodegenAnswer{}, fmt.Errorf("generate-answer decode success: %w", err)
	}
	if !ok {
		return CodegenAnswer{}, fmt.Errorf("generate-answer api returned success=false")
	}
	var ans CodegenAnswer
	if err := decodePossiblyStringified(r[field], &ans); err == nil && (ans.Prompt != "" || len(ans.Responses) > 0) {
		return ans, nil
	}
	alt := "answer"
	if field == "answer" {
		alt = "ans_id"
	}
	if err := decodePossiblyStringified(r[alt], &ans); err != nil {
		return CodegenAnswer{}, fmt.Errorf("generate answer decode (%s/%s): %w", field, alt, err)
	}
	return ans, nil
}

// GetCodegenAnswer fetches a codegen answer by question ID.
func (s *SyntheticAPI) GetCodegenAnswer(qaID string) (GenerateAnswerResponse[CodegenAnswer], error) {
	if qaID == "" {
		return GenerateAnswerResponse[CodegenAnswer]{}, fmt.Errorf("qaID cannot be empty")
	}
	ans, err := s.fetchCodegenFromField(qaID, "answer")
	if err != nil {
		log.Error().Err(err).Msg("generate-answer request failed")
		return GenerateAnswerResponse[CodegenAnswer]{}, err
	}
	return GenerateAnswerResponse[CodegenAnswer]{Success: true, Answer: ans}, nil
}

// GetQuestionAugment asks the service to generate augmented variations of a question.
func (s *SyntheticAPI) GetQuestionAugment(baseQuestion string, numAugments int) (AugmentQuestionResponse, error) {
	var out AugmentQuestionResponse

	payload := map[string]string{
		"question":     baseQuestion,
		"num_augments": strconv.Itoa(numAugments),
	}

	resp, err := s.postJSON("/api/get-question-augment", payload, &out)
	if err != nil {
		log.Error().Err(err).Msg("get-question-augment request failed")
		return AugmentQuestionResponse{}, fmt.Errorf("get question augment: %w", err)
	}
	if resp.IsError() {
		log.Error().Int("status", resp.StatusCode()).Str("body", resp.String()).Msg("get-question-augment non-2xx")
		return AugmentQuestionResponse{}, fmt.Errorf(
			"get-question-augment status %d: %s",
			resp.StatusCode(), resp.String(),
		)
	}
	if !out.Success {
		return AugmentQuestionResponse{}, fmt.Errorf("get-question-augment api returned success=false")
	}
	return out, nil
}

// OrderAnswer requests the service to generate an answer for the given question.
func (s *SyntheticAPI) OrderAnswer(question string) (OrderAnswerResponse, error) {
	var out OrderAnswerResponse
	payload := map[string]string{"question": question}
	resp, err := s.postJSON("/api/order-answer", payload, &out)
	if err != nil {
		log.Error().Err(err).Msg("order-answer request failed")
		return OrderAnswerResponse{}, fmt.Errorf("order answer: %w", err)
	}
	if resp.IsError() {
		log.Error().Int("status", resp.StatusCode()).Str("body", resp.String()).Msg("order-answer non-2xx")
		return OrderAnswerResponse{}, fmt.Errorf(
			"order-answer status %d: %s",
			resp.StatusCode(), resp.String(),
		)
	}
	if !out.Success {
		return OrderAnswerResponse{}, fmt.Errorf("order-answer api returned success=false")
	}
	return out, nil
}
