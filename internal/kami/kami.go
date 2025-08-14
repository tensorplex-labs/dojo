package kami

import (
	"fmt"
	"strconv"

	"github.com/bytedance/sonic"
	"github.com/go-resty/resty/v2"
	"github.com/rs/zerolog/log"

	"github.com/tensorplex-labs/dojo/internal/config"
)

// KamiClient defines the methods implemented by the Kami service client
// Use this interface in callers to allow easy mocking and testing
type KamiInterface interface {
	ServeAxon(ServeAxonParams) (ExtrinsicHashResponse, error)
	GetMetagraph(netuid int) (SubnetMetagraphResponse, error)
	SetWeights(SetWeightsParams) (ExtrinsicHashResponse, error)
	SignMessage(SignMessageParams) (SignMessageResponse, error)
	VerifyMessage(VerifyMessageParams) (VerifyMessageResponse, error)
	GetKeyringPair() (KeyringPairInfoResponse, error)
	GetLatestBlock() (LatestBlockResponse, error)
}

type Kami struct {
	client        *resty.Client
	Host          string
	Port          string
	WalletHotkey  string
	WalletColdkey string
	BaseURL       string
}

func NewKami(cfg *config.KamiEnvConfig) (*Kami, error) {
	if cfg == nil {
		return nil, fmt.Errorf("configuration cannot be nil")
	}

	url := fmt.Sprintf("http://%s:%s", cfg.KamiHost, cfg.KamiPort)

	client := resty.New().
		SetBaseURL(url).
		SetJSONMarshaler(sonic.Marshal).
		SetJSONUnmarshaler(sonic.Unmarshal)

	return &Kami{
		client:        client,
		Host:          cfg.KamiHost,
		Port:          cfg.KamiPort,
		WalletHotkey:  cfg.WalletHotkey,
		WalletColdkey: cfg.WalltetColdkey,
		BaseURL:       url,
	}, nil
}

func (k *Kami) ServeAxon(payload ServeAxonParams) (ExtrinsicHashResponse, error) {
	var result ExtrinsicHashResponse

	resp, err := k.client.R().
		SetBody(payload).
		SetResult(&result).
		Post("/chain/serve-axon")
	if err != nil {
		log.Error().Err(err).Msg("failed to serve axon")
		return ExtrinsicHashResponse{}, fmt.Errorf("serve axon: %w", err)
	}
	if resp.IsError() {
		log.Error().Int("status", resp.StatusCode()).Str("body", resp.String()).Msg("serve-axon error")
		return ExtrinsicHashResponse{}, fmt.Errorf("request returned status %d: %s", resp.StatusCode(), resp.String())
	}
	if result.Error != nil {
		log.Error().Interface("error", result.Error).Msg("axon response contains error")
		return ExtrinsicHashResponse{}, fmt.Errorf("axon response error: %v", result.Error)
	}
	return result, nil
}

func (k *Kami) GetMetagraph(netuid int) (SubnetMetagraphResponse, error) {
	var result SubnetMetagraphResponse

	resp, err := k.client.R().
		SetPathParams(map[string]string{"netuid": strconv.Itoa(netuid)}).
		SetResult(&result).
		Get("/chain/subnet-metagraph/{netuid}")
	if err != nil {
		log.Error().Err(err).Msg("failed to get metagraph")
		return SubnetMetagraphResponse{}, fmt.Errorf("get metagraph: %w", err)
	}
	if resp.IsError() {
		log.Error().Int("status", resp.StatusCode()).Str("body", resp.String()).Msg("metagraph error")
		return SubnetMetagraphResponse{}, fmt.Errorf("request returned status %d: %s", resp.StatusCode(), resp.String())
	}
	if result.Error != nil {
		log.Error().Interface("error", result.Error).Msg("metagraph response contains error")
		return SubnetMetagraphResponse{}, fmt.Errorf("metagraph response error: %v", result.Error)
	}
	return result, nil
}

func (k *Kami) GetLatestBlock() (LatestBlockResponse, error) {
	var result LatestBlockResponse

	resp, err := k.client.R().
		SetResult(&result).
		Get("/chain/latest-block")
	if err != nil {
		log.Error().Err(err).Msg("failed to get latest block")
		return LatestBlockResponse{}, fmt.Errorf("get latest block: %w", err)
	}
	if resp.IsError() {
		log.Error().Int("status", resp.StatusCode()).Str("body", resp.String()).Msg("latest-block error")
		return LatestBlockResponse{}, fmt.Errorf("request returned status %d: %s", resp.StatusCode(), resp.String())
	}
	if result.Error != nil {
		log.Error().Interface("error", result.Error).Msg("latest-block response contains error")
		return LatestBlockResponse{}, fmt.Errorf("latest-block response error: %v", result.Error)
	}
	return result, nil
}

func (k *Kami) SetWeights(params SetWeightsParams) (ExtrinsicHashResponse, error) {
	var result ExtrinsicHashResponse

	resp, err := k.client.R().
		SetBody(params).
		SetResult(&result).
		Post("/chain/set-weights")
	if err != nil {
		log.Error().Err(err).Msg("failed to set weights")
		return ExtrinsicHashResponse{}, fmt.Errorf("set weights: %w", err)
	}
	if resp.IsError() {
		log.Error().Int("status", resp.StatusCode()).Str("body", resp.String()).Msg("set-weights error")
		return ExtrinsicHashResponse{}, fmt.Errorf("request returned status %d: %s", resp.StatusCode(), resp.String())
	}
	if result.Error != nil {
		log.Error().Interface("error", result.Error).Msg("set-weights response contains error")
		return ExtrinsicHashResponse{}, fmt.Errorf("set weights response error: %v", result.Error)
	}
	return result, nil
}

func (k *Kami) SignMessage(params SignMessageParams) (SignMessageResponse, error) {
	var result SignMessageResponse

	resp, err := k.client.R().
		SetBody(params).
		SetResult(&result).
		Post("/substrate/sign-message/sign")
	if err != nil {
		log.Error().Err(err).Msg("failed to sign message")
		return SignMessageResponse{}, fmt.Errorf("sign message: %w", err)
	}
	if resp.IsError() {
		log.Error().Int("status", resp.StatusCode()).Str("body", resp.String()).Msg("sign-message error")
		return SignMessageResponse{}, fmt.Errorf("request returned status %d: %s", resp.StatusCode(), resp.String())
	}
	if result.Error != nil {
		log.Error().Interface("error", result.Error).Msg("sign-message response contains error")
		return SignMessageResponse{}, fmt.Errorf("sign message response error: %v", result.Error)
	}
	return result, nil
}

func (k *Kami) VerifyMessage(params VerifyMessageParams) (VerifyMessageResponse, error) {
	var result VerifyMessageResponse

	resp, err := k.client.R().
		SetBody(params).
		SetResult(&result).
		Post("/substrate/sign-message/verify")
	if err != nil {
		log.Error().Err(err).Msg("failed to verify message")
		return VerifyMessageResponse{}, fmt.Errorf("verify message: %w", err)
	}
	if resp.IsError() {
		log.Error().Int("status", resp.StatusCode()).Str("body", resp.String()).Msg("verify-message error")
		return VerifyMessageResponse{}, fmt.Errorf("request returned status %d: %s", resp.StatusCode(), resp.String())
	}
	if result.Error != nil {
		log.Error().Interface("error", result.Error).Msg("verify-message response contains error")
		return VerifyMessageResponse{}, fmt.Errorf("verify message response error: %v", result.Error)
	}
	return result, nil
}

func (k *Kami) GetKeyringPair() (KeyringPairInfoResponse, error) {
	var result KeyringPairInfoResponse

	resp, err := k.client.R().
		SetResult(&result).
		Get("/substrate/keyring-pair-info")
	if err != nil {
		log.Error().Err(err).Msg("failed to get keyring pair")
		return KeyringPairInfoResponse{}, fmt.Errorf("get keyring pair: %w", err)
	}
	if resp.IsError() {
		log.Error().Int("status", resp.StatusCode()).Str("body", resp.String()).Msg("keyring-pair-info error")
		return KeyringPairInfoResponse{}, fmt.Errorf("request returned status %d: %s", resp.StatusCode(), resp.String())
	}
	if result.Error != nil {
		log.Error().Interface("error", result.Error).Msg("keyring pair response contains error")
		return KeyringPairInfoResponse{}, fmt.Errorf("keyring pair response error: %v", result.Error)
	}
	return result, nil
}
