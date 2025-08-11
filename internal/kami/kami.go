package kami

import (
	"fmt"
	"strings"

	"github.com/bytedance/sonic"
	"github.com/go-resty/resty/v2"
	"github.com/rs/zerolog/log"

	"github.com/tensorplex-labs/dojo/internal/config"
)

// KamiChainRepo is a repository for interacting with the bittensor chain
type KamiChainRepo struct {
	httpClient *resty.Client
	baseURL    string
}

// KamiClient defines the methods implemented by the Kami service client
// Use this interface in callers to allow easy mocking and testing
type KamiClient interface {
	ServeAxon(ServeAxonParams) (ExtrinsicHashResponse, error)
	GetMetagraph() (SubnetMetagraphResponse, error)
	GetAxon() (LatestBlockResponse, error)
	SetWeights(SetWeightsParams) (ExtrinsicHashResponse, error)
}

type Kami struct {
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

	return &Kami{
		Host:          cfg.KamiHost,
		Port:          cfg.KamiPort,
		WalletHotkey:  cfg.WalletHotkey,
		WalletColdkey: cfg.WalltetColdkey,
		BaseURL:       url,
	}, nil
}

func (k *Kami) ServeAxon(payload ServeAxonParams) (ExtrinsicHashResponse, error) {
	apiPath := fmt.Sprintf("%s/chain/serve-axon", k.BaseURL)

	resp, err := sendRequest(apiPath, "POST", payload)
	if err != nil {
		log.Error().Err(err).Msg("failed to serve axon")
		return ExtrinsicHashResponse{}, fmt.Errorf("serve axon: %w", err)
	}

	var result ExtrinsicHashResponse
	if err := sonic.Unmarshal(resp, &result); err != nil {
		log.Error().Err(err).Msg("failed to unmarshal axon response")
		return ExtrinsicHashResponse{}, fmt.Errorf("unmarshal axon response: %w", err)
	}

	if result.Error != nil {
		log.Error().Str("error", fmt.Sprintf("%+v", result.Error)).Msg("axon response contains error")
		return ExtrinsicHashResponse{}, fmt.Errorf("axon response error: %s", result.Error)
	}

	return result, nil
}

func (k *Kami) GetMetagraph(netuid int) (SubnetMetagraphResponse, error) {
	apiPath := fmt.Sprintf("%s/chain/metagraph/%d", k.BaseURL, netuid)

	resp, err := sendRequest(apiPath, "GET", nil)
	if err != nil {
		log.Error().Err(err).Msg("failed to get metagraph")
		return SubnetMetagraphResponse{}, fmt.Errorf("get metagraph: %w", err)
	}

	var result SubnetMetagraphResponse
	if err := sonic.Unmarshal(resp, &result); err != nil {
		log.Error().Err(err).Msg("failed to unmarshal metagraph response")
		return SubnetMetagraphResponse{}, fmt.Errorf("unmarshal metagraph response: %w", err)
	}

	if result.Error != nil {
		log.Error().Str("error", fmt.Sprintf("%+v", result.Error)).Msg("metagraph response contains error")
		return SubnetMetagraphResponse{}, fmt.Errorf("metagraph response error: %s", result.Error)
	}

	return result, nil
}

func (k *Kami) GetLatestBlock() (LatestBlockResponse, error) {
	apiPath := fmt.Sprintf("%s/chain/latest-block", k.BaseURL)

	resp, err := sendRequest(apiPath, "GET", nil)
	if err != nil {
		log.Error().Err(err).Msg("failed to get axon")
		return LatestBlockResponse{}, fmt.Errorf("get axon: %w", err)
	}

	var result LatestBlockResponse
	if err := sonic.Unmarshal(resp, &result); err != nil {
		log.Error().Err(err).Msg("failed to unmarshal axon response")
		return LatestBlockResponse{}, fmt.Errorf("unmarshal axon response: %w", err)
	}

	if result.Error != nil {
		log.Error().Str("error", fmt.Sprintf("%+v", result.Error)).Msg("axon response contains error")
		return LatestBlockResponse{}, fmt.Errorf("axon response error: %s", result.Error)
	}

	return result, nil
}

func (k *Kami) SetWeights(params SetWeightsParams) (ExtrinsicHashResponse, error) {
	apiPath := fmt.Sprintf("%s/chain/set-weights", k.BaseURL)

	resp, err := sendRequest(apiPath, "POST", params)
	if err != nil {
		log.Error().Err(err).Msg("failed to set weights")
		return ExtrinsicHashResponse{}, fmt.Errorf("set weights: %w", err)
	}

	var result ExtrinsicHashResponse
	if err := sonic.Unmarshal(resp, &result); err != nil {
		log.Error().Err(err).Msg("failed to unmarshal set weights response")
		return ExtrinsicHashResponse{}, fmt.Errorf("unmarshal set weights response: %w", err)
	}

	if result.Error != nil {
		log.Error().Str("error", fmt.Sprintf("%+v", result.Error)).Msg("set weights response contains error")
		return ExtrinsicHashResponse{}, fmt.Errorf("set weights response error: %s", result.Error)
	}

	return result, nil
}

func (k *Kami) SignMessage(params SignMessageParams) (SignMessageResponse, error) {
	apiPath := fmt.Sprintf("%s/substrate/sign-message/sign", k.BaseURL)

	resp, err := sendRequest(apiPath, "POST", params)
	if err != nil {
		log.Error().Err(err).Msg("failed to sign message")
		return SignMessageResponse{}, fmt.Errorf("sign message: %w", err)
	}

	var result SignMessageResponse
	if err := sonic.Unmarshal(resp, &result); err != nil {
		log.Error().Err(err).Msg("failed to unmarshal sign message response")
		return SignMessageResponse{}, fmt.Errorf("unmarshal sign message response: %w", err)
	}

	if result.Error != nil {
		log.Error().Str("error", fmt.Sprintf("%+v", result.Error)).Msg("sign message response contains error")
		return SignMessageResponse{}, fmt.Errorf("sign message response error: %s", result.Error)
	}

	return result, nil
}

func (k *Kami) VerifyMessage(params VerifyMessageParams) (VerifyMessageResponse, error) {
	apiPath := fmt.Sprintf("%s/substrate/sign-message/verify", k.BaseURL)

	resp, err := sendRequest(apiPath, "POST", params)
	if err != nil {
		log.Error().Err(err).Msg("failed to verify message")
		return VerifyMessageResponse{}, fmt.Errorf("verify message: %w", err)
	}

	var result VerifyMessageResponse
	if err := sonic.Unmarshal(resp, &result); err != nil {
		log.Error().Err(err).Msg("failed to unmarshal verify message response")
		return VerifyMessageResponse{}, fmt.Errorf("unmarshal verify message response: %w", err)
	}

	if result.Error != nil {
		log.Error().Str("error", fmt.Sprintf("%+v", result.Error)).Msg("verify message response contains error")
		return VerifyMessageResponse{}, fmt.Errorf("verify message response error: %s", result.Error)
	}

	return result, nil
}

func (k *Kami) GetKeyringPair() (KeyringPairInfoResponse, error) {
	apiPath := fmt.Sprintf("%s/substrate/keyring-pair", k.BaseURL)

	resp, err := sendRequest(apiPath, "GET", nil)
	if err != nil {
		log.Error().Err(err).Msg("failed to get keyring pair")
		return KeyringPairInfoResponse{}, fmt.Errorf("get keyring pair: %w", err)
	}

	var result KeyringPairInfoResponse
	if err := sonic.Unmarshal(resp, &result); err != nil {
		log.Error().Err(err).Msg("failed to unmarshal keyring pair response")
		return KeyringPairInfoResponse{}, fmt.Errorf("unmarshal keyring pair response: %w", err)
	}

	if result.Error != nil {
		log.Error().Str("error", fmt.Sprintf("%+v", result.Error)).Msg("keyring pair response contains error")
		return KeyringPairInfoResponse{}, fmt.Errorf("keyring pair response error: %s", result.Error)
	}

	return result, nil
}

func sendRequest(url string, method string, body interface{}) ([]byte, error) {
	client := resty.New()
	method = strings.ToUpper(method)

	req := client.R().SetHeader("Accept", "application/json")

	// attach body for methods that support payloads
	if body != nil && (method == "POST" || method == "PUT" || method == "PATCH") {
		b, err := sonic.Marshal(body)
		if err != nil {
			log.Error().Err(err).Msg("failed to marshal request body")
			return nil, fmt.Errorf("marshal body: %w", err)
		}
		req.SetHeader("Content-Type", "application/json").SetBody(b)
	}

	var resp *resty.Response
	var err error
	switch method {
	case "GET":
		resp, err = req.Get(url)
	case "POST":
		resp, err = req.Post(url)
	case "PUT":
		resp, err = req.Put(url)
	case "DELETE":
		resp, err = req.Delete(url)
	case "PATCH":
		resp, err = req.Patch(url)
	default:
		return nil, fmt.Errorf("unsupported method %s", method)
	}

	if err != nil {
		log.Error().Err(err).Str("url", url).Str("method", method).Msg("request failed")
		return nil, fmt.Errorf("request failed: %w", err)
	}

	if resp.IsError() {
		log.Error().Int("status", resp.StatusCode()).Str("body", string(resp.Body())).Msg("received error status from kami")
		return nil, fmt.Errorf("request returned status %d: %s", resp.StatusCode(), string(resp.Body()))
	}

	if len(resp.Body()) == 0 {
		return nil, nil
	}

	return resp.Body(), nil
}
