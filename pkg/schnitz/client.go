package schnitz

import (
	"bytes"
	"fmt"
	"os"
	"reflect"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/bytedance/sonic"
	"github.com/go-resty/resty/v2"
	"github.com/klauspost/compress/zstd"
	"github.com/rs/zerolog/log"
	"github.com/tensorplex-labs/dojo/pkg/signature"
)

// Client configuration
type ClientConfig struct {
	Timeout         time.Duration
	ZstdCompression bool
	hotkeyName      string
	coldkeyName     string
}

type Client struct {
	config            *ClientConfig
	restyClient       *resty.Client
	encoder           *zstd.Encoder
	decoder           *zstd.Decoder
	signatureProvider *signature.Provider
	hotkey            string
}

// NewClient creates a new schnitz client
func NewClient(config *ClientConfig) (*Client, error) {
	if config == nil {
		config = &ClientConfig{}
	}

	// TODO: use envconfigs from config pkg, need to explore if it clashes
	// since already parsed using MinerEnvConfig / ValidatorEnvConfig
	if timeoutStr := os.Getenv("CLIENT_TIMEOUT"); timeoutStr != "" {
		if timeout, err := strconv.Atoi(timeoutStr); err == nil {
			config.Timeout = time.Duration(timeout) * time.Second
			log.Debug().
				Int("timeout_seconds", timeout).
				Msg("Loaded client timeout from environment")
		} else {
			log.Warn().
				Str("CLIENT_TIMEOUT", timeoutStr).
				Err(err).
				Msg("Invalid CLIENT_TIMEOUT environment variable, using default")
		}
	}

	if config.Timeout == 0 {
		config.Timeout = DefaultClientTimeout * time.Second
	}

	if config.hotkeyName == "" {
		if walletHotkey := os.Getenv("WALLET_HOTKEY"); walletHotkey != "" {
			config.hotkeyName = walletHotkey
			log.Debug().
				Str("hotkey_path", walletHotkey).
				Msg("Loaded client hotkey path from environment")
		}
	}

	if config.coldkeyName == "" {
		if walletColdkey := os.Getenv("WALLET_COLDKEY"); walletColdkey != "" {
			config.coldkeyName = walletColdkey
			log.Debug().
				Str("coldkey_path", walletColdkey).
				Msg("Loaded client coldkey path from environment")
		}
	}

	// Always enable compression
	config.ZstdCompression = true

	// Create resty client with configuration
	restyClient := resty.New().
		SetTimeout(config.Timeout).
		SetJSONMarshaler(sonic.Marshal).
		SetJSONUnmarshaler(sonic.Unmarshal)

	// Enable automatic decompression for all compression types
	if config.ZstdCompression {
		restyClient.SetHeader("Accept-Encoding", "zstd")
	}

	client := &Client{
		config:      config,
		restyClient: restyClient,
	}

	// Initialize signature provider if keypair path is provided
	if config.hotkeyName != "" {
		keypair, err := signature.LoadKeypairFromHotkey(
			config.coldkeyName,
			config.hotkeyName,
		)
		if err != nil {
			return nil, fmt.Errorf("failed to load keypair: %w", err)
		}

		signProvider, err := signature.NewProvider(keypair)
		if err != nil {
			return nil, fmt.Errorf("failed to create signature provider: %w", err)
		}

		client.signatureProvider = signProvider
		client.hotkey = signature.ToSs58Address(keypair)
	}

	// Initialize reusable encoder and decoder if compression is enabled
	if config.ZstdCompression {
		var buf bytes.Buffer
		encoder, err := zstd.NewWriter(&buf)
		if err != nil {
			return nil, fmt.Errorf("failed to create zstd encoder: %w", err)
		}
		client.encoder = encoder

		decoder, err := zstd.NewReader(nil)
		if err != nil {
			return nil, fmt.Errorf("failed to create zstd decoder: %w", err)
		}
		client.decoder = decoder
	}
	return client, nil
}

// Close cleans up client resources
func (c *Client) Close() {
	if c.encoder != nil {
		c.encoder.Close()
	}
	if c.decoder != nil {
		c.decoder.Close()
	}
}

// CreateAuthParams creates AuthParams by signing the provided message
func (c *Client) CreateAuthParams() (AuthParams, error) {
	if c.signatureProvider == nil {
		return AuthParams{}, fmt.Errorf(
			"signature provider not initialized - keypair path required in ClientConfig",
		)
	}

	message := "I swear that I am the owner of hotkey:" + c.hotkey
	signature, err := c.signatureProvider.Sign(message)
	if err != nil {
		return AuthParams{}, fmt.Errorf("failed to sign message: %w", err)
	}

	return AuthParams{
		Hotkey:    c.hotkey,
		Message:   message,
		Signature: signature,
	}, nil
}

func (c *Client) buildHeaders(auth AuthParams) map[string]string {
	headers := map[string]string{
		"Content-Type": "application/json",
		"x-signature":  auth.Signature,
		"x-message":    auth.Message,
		"x-hotkey":     auth.Hotkey,
	}
	if c.config.ZstdCompression {
		headers["Accept-Encoding"] = "zstd"
		headers["Content-Encoding"] = "zstd"
	}
	return headers
}

// makeRequest performs an authenticated HTTP request with optional compression
func (c *Client) makeRequest(
	baseURL string,
	request interface{},
	response interface{},
	auth AuthParams,
) error {
	// Build endpoint from request type
	requestType := reflect.TypeOf(request)
	if requestType.Kind() == reflect.Ptr {
		requestType = requestType.Elem()
	}
	endpoint := strings.TrimSuffix(baseURL, "/") + "/" + requestType.Name()
	headers := c.buildHeaders(auth)
	// TODO: add retry hooks
	req := c.restyClient.R().
		SetHeaders(headers)

	if response == nil || reflect.ValueOf(response).Kind() != reflect.Ptr ||
		reflect.ValueOf(response).IsNil() {
		return fmt.Errorf("invalid response: must be a non-nil pointer")
	}

	log.Trace().
		Interface("headers", headers).
		Str("endpoint", endpoint).
		Interface("request", request).
		Msg("Request headers")

	// Handle compression if enabled
	if c.config.ZstdCompression && c.encoder != nil {
		// Compress the request body
		jsonData, err := sonic.Marshal(request)
		if err != nil {
			return fmt.Errorf("failed to marshal request: %w", err)
		}

		// Reuse encoder by resetting to a new buffer
		var buf bytes.Buffer
		c.encoder.Reset(&buf)

		_, err = c.encoder.Write(jsonData)
		if err != nil {
			return fmt.Errorf("failed to compress request: %w", err)
		}

		err = c.encoder.Close()
		if err != nil {
			return fmt.Errorf("failed to finalize compression: %w", err)
		}

		req = req.SetBody(buf.Bytes())
	} else {
		req = req.SetBody(request)
	}

	// Make the request
	resp, err := req.Post(endpoint)
	if err != nil {
		return fmt.Errorf("failed to make request: %w", err)
	}

	// Handle response decompression if needed (before error checking)
	responseBody := resp.Body()
	if c.config.ZstdCompression && c.decoder != nil {
		contentEncoding := resp.Header().Get("Content-Encoding")
		if contentEncoding == "zstd" {
			decompressed, err := c.decoder.DecodeAll(responseBody, nil)
			if err != nil {
				return fmt.Errorf("failed to decompress response: %w", err)
			}
			responseBody = decompressed
		}
	}

	// Check for errors (resty handles HTTP status codes automatically)
	if resp.IsError() {
		return fmt.Errorf("HTTP error %d: %s", resp.StatusCode(), string(responseBody))
	}

	// Parse the StdResponse wrapper manually
	responseType := reflect.TypeOf(response).Elem()
	stdResponseType := reflect.StructOf([]reflect.StructField{
		{Name: "Body", Type: responseType, Tag: `json:"body"`},
		{Name: "Error", Type: reflect.TypeOf((*string)(nil)), Tag: `json:"error,omitempty"`},
	})

	stdResponseValue := reflect.New(stdResponseType)
	err = sonic.Unmarshal(responseBody, stdResponseValue.Interface())
	if err != nil {
		return fmt.Errorf("failed to unmarshal StdResponse: %w", err)
	}

	// Check for application-level errors
	errorField := stdResponseValue.Elem().FieldByName("Error")
	if !errorField.IsNil() {
		errorMsg := errorField.Elem().String()
		return fmt.Errorf("server error: %s", errorMsg)
	}

	// Extract the body and set it to the response
	bodyField := stdResponseValue.Elem().FieldByName("Body")
	reflect.ValueOf(response).Elem().Set(bodyField)

	return nil
}

// Send performs an authenticated HTTP request with optional compression
func (c *Client) Send(
	baseURL string,
	request interface{},
	response interface{},
	auth AuthParams,
) error {
	return c.makeRequest(baseURL, request, response, auth)
}

func SendMany[T any](
	c *Client,
	baseUrls []string,
	requests []T,
	responses []*T,
	auth AuthParams,
) []error {
	if len(baseUrls) != len(requests) || len(baseUrls) != len(responses) {
		log.Error().Msg("baseUrls, requests, and responses must have the same length")
		return []error{fmt.Errorf("baseUrls, request, and response must have the same length")}
	}

	errors := make([]error, len(baseUrls))
	var wg sync.WaitGroup
	wg.Add(len(baseUrls))

	for i, url := range baseUrls {
		go func(index int, url string, request T, response *T) {
			defer wg.Done()
			err := c.makeRequest(url, request, response, auth)
			log.Info().Interface(fmt.Sprintf("Request%d", index), request)
			if err != nil {
				errors[index] = fmt.Errorf("error in request %d: %w", index, err)
			}
		}(i, url, requests[i], responses[i])
	}

	wg.Wait()
	return errors
}
