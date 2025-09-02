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

type SyntheticApiInterface interface {
	GetQuestion() (GenerateQuestionResponse, error)
	GetCodegenAnswer(qaID string) (GenerateAnswerResponse[CodegenAnswer], error)
	GetAugmentedCodegenAnswer(qaID string) (GenerateAugmentedAnswerResponse[CodegenAnswer], error)
	GetQuestionAugment(baseQuestion string, numAugments int) (AugmentQuestionResponse, error)
	OrderAnswer(question string) (OrderAnswerResponse, error)
}

type SyntheticApi struct {
	cfg    *config.SyntheticApiEnvConfig
	client *resty.Client
}

func NewSyntheticApi(cfg *config.SyntheticApiEnvConfig) (*SyntheticApi, error) {
	if cfg == nil {
		return nil, fmt.Errorf("configuration cannot be nil")
	}

	client := resty.New().
		SetBaseURL(cfg.SyntheticApiUrl).
		SetJSONMarshaler(sonic.Marshal).
		SetJSONUnmarshaler(sonic.Unmarshal)

	return &SyntheticApi{
		cfg:    cfg,
		client: client,
	}, nil
}

func (s *SyntheticApi) GetQuestion() (GenerateQuestionResponse, error) {
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
		return GenerateQuestionResponse{}, fmt.Errorf("get-question status %d: %s", resp.StatusCode(), resp.String())
	}
	if !out.Success {
		return GenerateQuestionResponse{}, fmt.Errorf("get-question api returned success=false")
	}
	return out, nil
}

func (s *SyntheticApi) GetCodegenAnswer(qaID string) (GenerateAnswerResponse[CodegenAnswer], error) {
	if qaID == "" {
		return GenerateAnswerResponse[CodegenAnswer]{}, fmt.Errorf("taskType and qaID cannot be empty")
	}

	type rawResp struct {
		Success bool            `json:"success"`
		Answer  json.RawMessage `json:"answer"`
	}

	var raw rawResp
	payload := map[string]string{"qa_id": qaID}
	resp, err := s.client.R().
		SetHeader("Content-Type", "application/json").
		SetBody(payload).
		SetResult(&raw).
		Post("/api/generate-answer")
	if err != nil {
		log.Error().Err(err).Msg("generate-answer request failed")
		return GenerateAnswerResponse[CodegenAnswer]{}, fmt.Errorf("generate answer: %w", err)
	}
	if resp.IsError() {
		log.Error().Int("status", resp.StatusCode()).Str("body", resp.String()).Msg("generate-answer non-2xx")
		return GenerateAnswerResponse[CodegenAnswer]{}, fmt.Errorf("generate-answer status %d: %s", resp.StatusCode(), resp.String())
	}
	if !raw.Success {
		return GenerateAnswerResponse[CodegenAnswer]{}, fmt.Errorf("generate-answer api returned success=false")
	}

	var ans CodegenAnswer
	if len(raw.Answer) > 0 {
		if raw.Answer[0] == '"' {
			var sjson string
			if err := sonic.Unmarshal(raw.Answer, &sjson); err != nil {
				return GenerateAnswerResponse[CodegenAnswer]{}, fmt.Errorf("generate answer: unquote answer: %w", err)
			}
			if err := sonic.Unmarshal([]byte(sjson), &ans); err != nil {
				return GenerateAnswerResponse[CodegenAnswer]{}, fmt.Errorf("generate answer: decode stringified answer: %w", err)
			}
		} else {
			if err := sonic.Unmarshal(raw.Answer, &ans); err != nil {
				return GenerateAnswerResponse[CodegenAnswer]{}, fmt.Errorf("generate answer: decode answer: %w", err)
			}
		}
	}

	return GenerateAnswerResponse[CodegenAnswer]{Success: true, Answer: ans}, nil
}

func (s *SyntheticApi) GetAugmentedCodegenAnswer(qaID string) (GenerateAugmentedAnswerResponse[CodegenAnswer], error) {
	if qaID == "" {
		return GenerateAugmentedAnswerResponse[CodegenAnswer]{}, fmt.Errorf("taskType and qaID cannot be empty")
	}

	type rawResp struct {
		Success bool            `json:"success"`
		AnsID   json.RawMessage `json:"ans_id"`
	}

	var raw rawResp
	payload := map[string]string{"qa_id": qaID}
	resp, err := s.client.R().
		SetHeader("Content-Type", "application/json").
		SetBody(payload).
		SetResult(&raw).
		Post("/api/generate-answer")
	if err != nil {
		log.Error().Err(err).Msg("generate-answer request failed")
		return GenerateAugmentedAnswerResponse[CodegenAnswer]{}, fmt.Errorf("generate answer: %w", err)
	}
	if resp.IsError() {
		log.Error().Int("status", resp.StatusCode()).Str("body", resp.String()).Msg("generate-answer non-2xx")
		return GenerateAugmentedAnswerResponse[CodegenAnswer]{}, fmt.Errorf("generate-answer status %d: %s", resp.StatusCode(), resp.String())
	}
	if !raw.Success {
		return GenerateAugmentedAnswerResponse[CodegenAnswer]{}, fmt.Errorf("generate-answer api returned success=false")
	}

	var ans CodegenAnswer
	if len(raw.AnsID) > 0 {
		if raw.AnsID[0] == '"' {
			var sjson string
			if err := sonic.Unmarshal(raw.AnsID, &sjson); err != nil {
				return GenerateAugmentedAnswerResponse[CodegenAnswer]{}, fmt.Errorf("generate answer: unquote answer: %w", err)
			}
			if err := sonic.Unmarshal([]byte(sjson), &ans); err != nil {
				return GenerateAugmentedAnswerResponse[CodegenAnswer]{}, fmt.Errorf("generate answer: decode stringified answer: %w", err)
			}
		} else {
			if err := sonic.Unmarshal(raw.AnsID, &ans); err != nil {
				return GenerateAugmentedAnswerResponse[CodegenAnswer]{}, fmt.Errorf("generate answer: decode answer: %w", err)
			}
		}
	}

	return GenerateAugmentedAnswerResponse[CodegenAnswer]{Success: true, AnsID: ans}, nil
}

func (s *SyntheticApi) GetQuestionAugment(baseQuestion string, numAugments int) (AugmentQuestionResponse, error) {
	var out AugmentQuestionResponse

	payload := map[string]string{
		"question":     baseQuestion,
		"num_augments": strconv.Itoa(numAugments),
	}

	resp, err := s.client.R().
		SetHeader("Content-Type", "application/json").
		SetBody(payload).
		SetResult(&out).
		Post("/api/get-question-augment")
	if err != nil {
		log.Error().Err(err).Msg("get-question-augment request failed")
		return AugmentQuestionResponse{}, fmt.Errorf("get question augment: %w", err)
	}
	if resp.IsError() {
		log.Error().Int("status", resp.StatusCode()).Str("body", resp.String()).Msg("get-question-augment non-2xx")
		return AugmentQuestionResponse{}, fmt.Errorf("get-question-augment status %d: %s", resp.StatusCode(), resp.String())
	}
	if !out.Success {
		return AugmentQuestionResponse{}, fmt.Errorf("get-question-augment api returned success=false")
	}
	return out, nil
}

func (s *SyntheticApi) OrderAnswer(question string) (OrderAnswerResponse, error) {
	var out OrderAnswerResponse
	payload := map[string]string{"question": question}
	resp, err := s.client.R().
		SetHeader("Content-Type", "application/json").
		SetBody(payload).
		SetResult(&out).
		Post("/api/order-answer")
	if err != nil {
		log.Error().Err(err).Msg("order-answer request failed")
		return OrderAnswerResponse{}, fmt.Errorf("order answer: %w", err)
	}
	if resp.IsError() {
		log.Error().Int("status", resp.StatusCode()).Str("body", resp.String()).Msg("order-answer non-2xx")
		return OrderAnswerResponse{}, fmt.Errorf("order-answer status %d: %s", resp.StatusCode(), resp.String())
	}
	if !out.Success {
		return OrderAnswerResponse{}, fmt.Errorf("order-answer api returned success=false")
	}
	return out, nil
}
