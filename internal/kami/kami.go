// Package kami provides a Bittensor subtensor client which relies on Kami as the RPC endpoint.
package kami

import (
	"fmt"
	"time"

	"github.com/bytedance/sonic"
	"github.com/go-resty/resty/v2"
	"github.com/rs/zerolog/log"

	"github.com/tensorplex-labs/dojo/internal/config"
	"github.com/tensorplex-labs/dojo/internal/validator"
)

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
		SetJSONUnmarshaler(sonic.Unmarshal).
		SetTimeout(15 * time.Second)

	return &Kami{
		client:        client,
		Host:          cfg.KamiHost,
		Port:          cfg.KamiPort,
		WalletHotkey:  cfg.WalletHotkey,
		WalletColdkey: cfg.WalltetColdkey,
		BaseURL:       url,
	}, nil
}

func postJSON[T any](client *resty.Client, path string, body any) (validator.SubtensorResponse[T], error) {
	var result validator.SubtensorResponse[T]
	resp, err := client.R().
		SetBody(body).
		SetResult(&result).
		Post(path)
	if err != nil {
		log.Error().Err(err).Str("path", path).Msg("post request failed")
		return validator.SubtensorResponse[T]{}, fmt.Errorf("post %s: %w", path, err)
	}
	if resp.IsError() {
		log.Error().Int("status", resp.StatusCode()).Str("body", resp.String()).Str("path", path).Msg("post non-2xx")
		return validator.SubtensorResponse[T]{}, fmt.Errorf("request returned status %d: %s", resp.StatusCode(), resp.String())
	}
	if result.Error != nil {
		log.Error().Interface("error", result.Error).Str("path", path).Msg("response contains error")
		return validator.SubtensorResponse[T]{}, fmt.Errorf("response error: %v", result.Error)
	}
	return result, nil
}

func getJSON[T any](client *resty.Client, path string) (validator.SubtensorResponse[T], error) {
	var result validator.SubtensorResponse[T]
	resp, err := client.R().
		SetResult(&result).
		Get(path)
	if err != nil {
		log.Error().Err(err).Str("path", path).Msg("get request failed")
		return validator.SubtensorResponse[T]{}, fmt.Errorf("get %s: %w", path, err)
	}
	if resp.IsError() {
		log.Error().Int("status", resp.StatusCode()).Str("body", resp.String()).Str("path", path).Msg("get non-2xx")
		return validator.SubtensorResponse[T]{}, fmt.Errorf("request returned status %d: %s", resp.StatusCode(), resp.String())
	}
	if result.Error != nil {
		log.Error().Interface("error", result.Error).Str("path", path).Msg("response contains error")
		return validator.SubtensorResponse[T]{}, fmt.Errorf("response error: %v", result.Error)
	}
	return result, nil
}

// GetMetagraph fetches the subnet metagraph for the given netuid.
func (k *Kami) GetMetagraph(netuid int) (validator.SubnetMetagraphResponse, error) {
	path := fmt.Sprintf("/chain/subnet-metagraph/%d", netuid)
	return getJSON[validator.SubnetMetagraph](k.client, path)
}

// GetSubnetHyperparams fetches the subnet hyperparams for the given netuid.
func (k *Kami) GetSubnetHyperparams(netuid int) (validator.SubnetHyperparamsResponse, error) {
	path := fmt.Sprintf("/chain/subnet-hyperparameters/%d", netuid)
	return getJSON[validator.SubnetHyperparams](k.client, path)
}

// GetLatestBlock retrieves the latest block details from the chain.
func (k *Kami) GetLatestBlock() (validator.LatestBlockResponse, error) {
	return getJSON[validator.LatestBlock](k.client, "/chain/latest-block")
}

// SetWeights sets the subnet weights and returns the extrinsic hash response.
func (k *Kami) SetWeights(params validator.SetWeightsParams) (validator.ExtrinsicHashResponse, error) {
	return postJSON[string](k.client, "/chain/set-weights", params)
}

// SetTimelockedWeights sets the subnet timelocked weights and returns the extrinsic hash response.
func (k *Kami) SetTimelockedWeights(params validator.SetTimelockedWeightsParams) (validator.ExtrinsicHashResponse, error) {
	return postJSON[string](k.client, "/chain/set-timelocked-weights", params)
}

// SignMessage signs an arbitrary message with the node's keypair.
func (k *Kami) SignMessage(params validator.SignMessageParams) (validator.SignMessageResponse, error) {
	return postJSON[validator.SignMessage](k.client, "/substrate/sign-message/sign", params)
}

// VerifyMessage verifies a signed message against a signee address.
func (k *Kami) VerifyMessage(params validator.VerifyMessageParams) (validator.VerifyMessageResponse, error) {
	return postJSON[validator.VerifyMessage](k.client, "/substrate/sign-message/verify", params)
}

// GetKeyringPair returns information about the node's keyring pair.
func (k *Kami) GetKeyringPair() (validator.KeyringPairInfoResponse, error) {
	return getJSON[validator.KeyringPairInfo](k.client, "/substrate/keyring-pair-info")
}
