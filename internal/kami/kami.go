// Package kami provides a client for interacting with the Kami service.
package kami

import (
	"fmt"

	"github.com/bytedance/sonic"
	"github.com/go-resty/resty/v2"
	"github.com/rs/zerolog/log"

	"github.com/tensorplex-labs/dojo/internal/config"
)

// KamiInterface defines the methods implemented by the Kami service client
// Use this interface in callers to allow easy mocking and testing
//

type KamiInterface interface {
	ServeAxon(ServeAxonParams) (ExtrinsicHashResponse, error)
	GetMetagraph(netuid int) (SubnetMetagraphResponse, error)
	SetWeights(SetWeightsParams) (ExtrinsicHashResponse, error)
	SignMessage(SignMessageParams) (SignMessageResponse, error)
	VerifyMessage(VerifyMessageParams) (VerifyMessageResponse, error)
	GetKeyringPair() (KeyringPairInfoResponse, error)
	GetLatestBlock() (LatestBlockResponse, error)
}

// Kami is a client wrapper for the Kami HTTP API.
// Kami is a client wrapper for the Kami HTTP API.
type Kami struct {
	client        *resty.Client
	Host          string
	Port          string
	WalletHotkey  string
	WalletColdkey string
	BaseURL       string
}

// NewKami creates a new Kami client using the provided environment configuration.
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

func postJSON[T any](client *resty.Client, path string, body any) (KamiResponse[T], error) {
	var result KamiResponse[T]
	resp, err := client.R().
		SetBody(body).
		SetResult(&result).
		Post(path)
	if err != nil {
		log.Error().Err(err).Str("path", path).Msg("post request failed")
		return KamiResponse[T]{}, fmt.Errorf("post %s: %w", path, err)
	}
	if resp.IsError() {
		log.Error().Int("status", resp.StatusCode()).Str("body", resp.String()).Str("path", path).Msg("post non-2xx")
		return KamiResponse[T]{}, fmt.Errorf("request returned status %d: %s", resp.StatusCode(), resp.String())
	}
	if result.Error != nil {
		log.Error().Interface("error", result.Error).Str("path", path).Msg("response contains error")
		return KamiResponse[T]{}, fmt.Errorf("response error: %v", result.Error)
	}
	return result, nil
}

func getJSON[T any](client *resty.Client, path string) (KamiResponse[T], error) {
	var result KamiResponse[T]
	resp, err := client.R().
		SetResult(&result).
		Get(path)
	if err != nil {
		log.Error().Err(err).Str("path", path).Msg("get request failed")
		return KamiResponse[T]{}, fmt.Errorf("get %s: %w", path, err)
	}
	if resp.IsError() {
		log.Error().Int("status", resp.StatusCode()).Str("body", resp.String()).Str("path", path).Msg("get non-2xx")
		return KamiResponse[T]{}, fmt.Errorf("request returned status %d: %s", resp.StatusCode(), resp.String())
	}
	if result.Error != nil {
		log.Error().Interface("error", result.Error).Str("path", path).Msg("response contains error")
		return KamiResponse[T]{}, fmt.Errorf("response error: %v", result.Error)
	}
	return result, nil
}

// ServeAxon registers an axon on-chain and returns the extrinsic hash response.
func (k *Kami) ServeAxon(payload ServeAxonParams) (ExtrinsicHashResponse, error) {
	return postJSON[string](k.client, "/chain/serve-axon", payload)
}

// GetMetagraph fetches the subnet metagraph for the given netuid.
func (k *Kami) GetMetagraph(netuid int) (SubnetMetagraphResponse, error) {
	path := fmt.Sprintf("/chain/subnet-metagraph/%d", netuid)
	return getJSON[SubnetMetagraph](k.client, path)
}

// GetLatestBlock retrieves the latest block details from the chain.
func (k *Kami) GetLatestBlock() (LatestBlockResponse, error) {
	return getJSON[LatestBlock](k.client, "/chain/latest-block")
}

// SetWeights sets the subnet weights and returns the extrinsic hash response.
func (k *Kami) SetWeights(params SetWeightsParams) (ExtrinsicHashResponse, error) {
	return postJSON[string](k.client, "/chain/set-weights", params)
}

// SignMessage signs an arbitrary message with the node's keypair.
func (k *Kami) SignMessage(params SignMessageParams) (SignMessageResponse, error) {
	return postJSON[SignMessage](k.client, "/substrate/sign-message/sign", params)
}

// VerifyMessage verifies a signed message against a signee address.
func (k *Kami) VerifyMessage(params VerifyMessageParams) (VerifyMessageResponse, error) {
	return postJSON[VerifyMessage](k.client, "/substrate/sign-message/verify", params)
}

// GetKeyringPair returns information about the node's keyring pair.
func (k *Kami) GetKeyringPair() (KeyringPairInfoResponse, error) {
	return getJSON[KeyringPairInfo](k.client, "/substrate/keyring-pair-info")
}
