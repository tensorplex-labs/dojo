package syntheticapi

import (
	"fmt"
	"strconv"

	"github.com/bytedance/sonic"
	"github.com/go-resty/resty/v2"
	"github.com/rs/zerolog/log"

	"github.com/tensorplex-labs/dojo/internal/config"
)

type SyntheticApiInterface interface {
	GetQuestion() (GenerateQuestionResponse, error)
	GetAnswer(qaID string) (GenerateAnswerResponse, error)
	GetQuestionAugment(baseQuestion string, numAugments int) (AugmentQuestionResponse, error)
	OrderAnswer(question string) (GenerateAnswerResponse, error)
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
		Get("/generate-question")
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

func (s *SyntheticApi) GetAnswer(qaID string) (GenerateAnswerResponse, error) {
	var out GenerateAnswerResponse
	resp, err := s.client.R().
		SetQueryParam("qa_id", qaID).
		SetResult(&out).
		Post("/generate-answer")
	if err != nil {
		log.Error().Err(err).Msg("generate-answer request failed")
		return GenerateAnswerResponse{}, fmt.Errorf("generate answer: %w", err)
	}
	if resp.IsError() {
		log.Error().Int("status", resp.StatusCode()).Str("body", resp.String()).Msg("generate-answer non-2xx")
		return GenerateAnswerResponse{}, fmt.Errorf("generate-answer status %d: %s", resp.StatusCode(), resp.String())
	}
	if !out.Success {
		return GenerateAnswerResponse{}, fmt.Errorf("generate-answer api returned success=false")
	}
	return out, nil
}

func (s *SyntheticApi) GetQuestionAugment(baseQuestion string, numAugments int) (AugmentQuestionResponse, error) {
	var out AugmentQuestionResponse
	resp, err := s.client.R().
		SetQueryParams(map[string]string{
			"base_question": baseQuestion,
			"num_augments":  strconv.Itoa(numAugments),
		}).
		SetResult(&out).
		Post("/get-question-augment")
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

func (s *SyntheticApi) OrderAnswer(question string) (GenerateAnswerResponse, error) {
	var out GenerateAnswerResponse
	resp, err := s.client.R().
		SetQueryParam("question", question).
		SetResult(&out).
		Post("/order-answer")
	if err != nil {
		log.Error().Err(err).Msg("order-answer request failed")
		return GenerateAnswerResponse{}, fmt.Errorf("order answer: %w", err)
	}
	if resp.IsError() {
		log.Error().Int("status", resp.StatusCode()).Str("body", resp.String()).Msg("order-answer non-2xx")
		return GenerateAnswerResponse{}, fmt.Errorf("order-answer status %d: %s", resp.StatusCode(), resp.String())
	}
	if !out.Success {
		return GenerateAnswerResponse{}, fmt.Errorf("order-answer api returned success=false")
	}
	return out, nil
}
