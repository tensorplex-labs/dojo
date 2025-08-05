package chain

import (
	"bytes"
	"context"
	"encoding/binary"
	"fmt"
	"io"
	"net"
	"net/http"
	"time"

	"github.com/bytedance/sonic"
	"github.com/hashicorp/go-retryablehttp"
	"github.com/rs/zerolog/log"
	"github.com/sethvargo/go-envconfig"
	"github.com/tensorplex-labs/dojo/pkg/config"
)

func NewKamiChainRepo() (*KamiChainRepo, error) {
	log.Debug().Msg("creating new kami client")

	ctx := context.Background()

	// TODO: use config.KamiConfig or something, centralize env vars
	var envCfg config.KamiEnvConfig
	if err := envconfig.Process(ctx, &envCfg); err != nil {
		log.Fatal().Err(err).Msg("Failed to process environment variables for Kami")
	}

	kamiHost := envCfg.KamiHost
	if kamiHost == "" {
		kamiHost = "localhost"
		log.Debug().Str("chain_host", kamiHost).Msg("using default host")
	} else {
		log.Debug().Str("kami_host", kamiHost).Msg("using configured host")
	}

	kamiPort := envCfg.KamiPort
	if kamiPort == "" {
		kamiPort = "3000"
		log.Debug().Str("kami_port", kamiPort).Msg("using default port")
	} else {
		log.Debug().Str("kami_port", kamiPort).Msg("using configured port")
	}

	baseURL := fmt.Sprintf("http://%s:%s", kamiHost, kamiPort)
	log.Debug().Str("base_url", baseURL).Msg("constructed base URL")

	client := retryablehttp.NewClient()
	client.RetryMax = 5
	client.HTTPClient.Timeout = 30 * time.Second
	client.RetryWaitMin = 500 * time.Millisecond
	client.RetryWaitMax = 20 * time.Second

	// Configure retryablehttp to use our logger wrapper
	client.Logger = nil

	log.Info().
		Str("base_url", baseURL).
		Int("retry_max", client.RetryMax).
		Str("timeout", client.HTTPClient.Timeout.String()).
		Str("retry_wait_min", client.RetryWaitMin.String()).
		Str("retry_wait_max", client.RetryWaitMax.String()).
		Msg("kami client initialized successfully")

	return &KamiChainRepo{
		httpClient: client,
		baseURL:    baseURL,
	}, nil
}

func (k *KamiChainRepo) doRequest(method, endpoint string, body interface{}) ([]byte, error) {
	log.Debug().
		Str("method", method).
		Str("endpoint", endpoint).
		Msg("entering doRequest")

	url := k.baseURL + endpoint

	var bodyReader io.Reader
	var bodySize int
	if body != nil {
		log.Debug().Msg("marshaling request body")
		jsonBody, err := sonic.Marshal(body)
		if err != nil {
			log.Error().
				Err(err).
				Str("method", method).
				Str("endpoint", endpoint).
				Msg("failed to marshal request body")
			return nil, fmt.Errorf("failed to marshal request body: %w", err)
		}
		bodySize = len(jsonBody)
		bodyReader = bytes.NewBuffer(jsonBody)
		log.Debug().Int("body_size", bodySize).Msg("request body marshaled")
	}

	req, err := retryablehttp.NewRequest(method, url, bodyReader)
	if err != nil {
		log.Error().
			Err(err).
			Str("method", method).
			Str("url", url).
			Msg("failed to create HTTP request")
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json")

	log.Debug().
		Str("method", method).
		Str("url", url).
		Int("body_size", bodySize).
		Msg("making HTTP request")

	resp, err := k.httpClient.Do(req)
	if err != nil {
		log.Error().
			Err(err).
			Str("method", method).
			Str("url", url).
			Msg("HTTP request failed")
		return nil, fmt.Errorf("HTTP request failed: %w", err)
	}
	defer resp.Body.Close()

	log.Debug().
		Str("method", method).
		Str("url", url).
		Int("status_code", resp.StatusCode).
		Msg("reading response body")

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		log.Error().
			Err(err).
			Str("method", method).
			Str("url", url).
			Int("status_code", resp.StatusCode).
			Msg("failed to read response body")
		return nil, fmt.Errorf("failed to read response body: %w", err)
	}

	log.Debug().
		Str("method", method).
		Str("url", url).
		Int("status_code", resp.StatusCode).
		Int("response_body_length", len(respBody)).
		Msg("HTTP request completed successfully")

	return respBody, nil
}

func (k *KamiChainRepo) GetSubnetMetagraph(netuid int) func(*ChainState) (*ChainState, error) {
	return func(state *ChainState) (*ChainState, error) {
		log.Info().
			Int("netuid", netuid).
			Msg("starting subnet metagraph fetch")

		endpoint := fmt.Sprintf("/chain/subnet-metagraph/%d", netuid)
		log.Debug().
			Int("netuid", netuid).
			Str("endpoint", endpoint).
			Msg("constructed endpoint for subnet metagraph")

		respBody, err := k.doRequest("GET", endpoint, nil)
		if err != nil {
			log.Error().
				Err(err).
				Int("netuid", netuid).
				Str("endpoint", endpoint).
				Msg("failed to get subnet metagraph")
			return state, fmt.Errorf("failed to get subnet metagraph: %w", err)
		}

		log.Debug().
			Int("netuid", netuid).
			Int("response_size", len(respBody)).
			Msg("parsing subnet metagraph response")

		var result SubnetMetagraphResponse
		if err := sonic.Unmarshal(respBody, &result); err != nil {
			log.Error().
				Err(err).
				Int("netuid", netuid).
				Int("response_size", len(respBody)).
				Msg("failed to parse subnet metagraph response")
			return state, fmt.Errorf("failed to parse response: %w", err)
		}

		log.Info().
			Int("netuid", netuid).
			Int("status_code", result.StatusCode).
			Bool("success", result.Success).
			Int("num_uids", result.Data.NumUids).
			Int("max_uids", result.Data.MaxUids).
			Int("block", result.Data.Block).
			Msg("subnet metagraph fetched successfully")

		return state.UpdateMetagraph(result.Data), nil
	}
}

func (k *KamiChainRepo) GetKeyringPairInfo() func(*ChainState) (*ChainState, error) {
	return func(state *ChainState) (*ChainState, error) {
		log.Info().Msg("starting keyring pair info fetch")

		endpoint := "/substrate/keyring-pair-info"
		log.Debug().
			Str("endpoint", endpoint).
			Msg("constructed endpoint for keyring pair info")

		respBody, err := k.doRequest("GET", endpoint, nil)
		if err != nil {
			log.Error().
				Err(err).
				Str("endpoint", endpoint).
				Msg("failed to get keyring pair info")
			return state, fmt.Errorf("failed to get keyring pair info: %w", err)
		}

		log.Debug().
			Int("response_size", len(respBody)).
			Msg("parsing keyring pair info response")

		var result KeyringPairInfoResponse
		if err := sonic.Unmarshal(respBody, &result); err != nil {
			log.Error().
				Err(err).
				Int("response_size", len(respBody)).
				Msg("failed to parse keyring pair info response")
			return state, fmt.Errorf("failed to parse response: %w", err)
		}

		log.Info().
			Int("status_code", result.StatusCode).
			Bool("success", result.Success).
			Str("hotkey_address", result.Data.KeyringPair.Address).
			Str("coldkey_address", result.Data.WalletColdkey).
			Str("key_type", result.Data.KeyringPair.Type).
			Bool("is_locked", result.Data.KeyringPair.IsLocked).
			Msg("keyring pair info fetched successfully")

		return state, nil
	}
}

func (k *KamiChainRepo) GetLatestBlock() func(*ChainState) (*ChainState, error) {
	return func(state *ChainState) (*ChainState, error) {
		endpoint := "/chain/latest-block"
		log.Debug().
			Str("endpoint", endpoint).
			Msg("constructed endpoint for latest block")

		respBody, err := k.doRequest("GET", endpoint, nil)
		if err != nil {
			log.Error().
				Err(err).
				Str("endpoint", endpoint).
				Msg("failed to get latest block")
			return state, fmt.Errorf("failed to get latest block: %w", err)
		}

		log.Debug().
			Int("response_size", len(respBody)).
			Msg("parsing latest block response")

		var result LatestBlockResponse
		if err := sonic.Unmarshal(respBody, &result); err != nil {
			log.Error().
				Err(err).
				Int("response_size", len(respBody)).
				Msg("failed to parse latest block response")
			return state, fmt.Errorf("failed to parse response: %w", err)
		}

		if !result.Success || result.StatusCode != http.StatusOK || result.Error != nil {
			log.Error().
				Int("status_code", result.StatusCode).
				Bool("success", result.Success).
				Interface("error", result.Error).
				Msg("failed to fetch latest block")
			return state, fmt.Errorf("failed to fetch latest block: %s", result.Error)
		}

		return state.UpdateBlock(result.Data.BlockNumber), nil
	}
}

func (k *KamiChainRepo) SetIP(ip string, port int) error {
	ipAsInt := ip2int(net.ParseIP(ip))
	params := ServeAxonParams{
		IP:           int(ipAsInt),
		Port:         port,
		Version:      1,
		IPType:       4, // 4 for IPv4
		Protocol:     4, // Should match ipType
		Placeholder1: 0,
		Placeholder2: 0,
	}

	endpoint := "chain/serve-axon"
	respBody, err := k.doRequest("POST", endpoint, params)
	if err != nil {
		log.Error().
			Err(err).
			Str("endpoint", endpoint).
			Msg("failed to set IP for axon")
		return fmt.Errorf("failed to set IP for axon: %w", err)
	}

	var result ServeAxonResponse
	if err := sonic.Unmarshal(respBody, &result); err != nil {
		log.Error().
			Err(err).
			Str("endpoint", endpoint).
			Int("response_size", len(respBody)).
			Msg("failed to parse serve axon response")
		return fmt.Errorf("failed to parse response: %w", err)
	}

	if !result.Success || result.StatusCode != http.StatusOK || result.Error != nil {
		log.Error().
			Int("status_code", result.StatusCode).
			Bool("success", result.Success).
			Interface("error", result.Error).
			Msg("failed to set IP for axon")
		return fmt.Errorf("failed to set IP for axon: %s", result.Error)
	}

	return nil
}

func ip2int(ip net.IP) uint32 {
	if len(ip) == 16 {
		return binary.BigEndian.Uint32(ip[12:16])
	}
	return binary.BigEndian.Uint32(ip)
}

func int2ip(nn uint32) net.IP {
	ip := make(net.IP, 4)
	binary.BigEndian.PutUint32(ip, nn)
	return ip
}
