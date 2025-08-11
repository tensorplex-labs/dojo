package synapse

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"strings"
	"time"

	"github.com/bytedance/sonic"
	"github.com/go-resty/resty/v2"
	"github.com/klauspost/compress/zstd"
	"github.com/rs/zerolog/log"
	"github.com/tensorplex-labs/dojo/internal/kami"
)

type Client struct {
	httpClient *resty.Client
	kami       *kami.Kami
}

func NewClient(kami *kami.Kami) *Client {
	cli := resty.New()

	cli.SetRetryCount(5)
	cli.SetTimeout(60 * time.Second)
	cli.SetRetryWaitTime(500 * time.Millisecond)
	cli.SetRetryMaxWaitTime(2 * time.Second)
	return &Client{httpClient: cli, kami: kami}
}

// SetKami attaches a Kami client to enable request signing
// heartbeat Synapse
func (c *Client) SendHeartbeat(ctx context.Context, url string, hb HeartbeatRequest) (HeartbeatResponse, error) {
	var resp HeartbeatResponse
	b, err := sonic.Marshal(hb)
	if err != nil {
		return resp, fmt.Errorf("marshal heartbeat: %w", err)
	}

	req := c.httpClient.R().SetContext(ctx).
		SetHeader("Content-Type", "application/json").
		SetBody(b)

	// attach auth headers if kami available
	if c.kami != nil {
		headers, err := createAuthHeaders(c.kami, b)
		if err != nil {
			log.Error().Err(err).Msg("failed to create auth headers")
			return resp, fmt.Errorf("create auth headers: %w", err)
		}
		for k, v := range headers {
			req.SetHeader(k, v)
		}
	}

	restyResp, err := req.Post(url)
	if err != nil {
		log.Error().Err(err).Str("url", url).Msg("send heartbeat failed")
		return resp, err
	}

	if restyResp.StatusCode() >= 400 {
		return resp, fmt.Errorf("bad status %d: %s", restyResp.StatusCode(), string(restyResp.Body()))
	}

	data := restyResp.Body()
	if strings.Contains(strings.ToLower(restyResp.Header().Get("Content-Encoding")), "zstd") {
		r, err := zstd.NewReader(bytes.NewReader(data))
		if err != nil {
			return resp, fmt.Errorf("zstd: failed to create reader: %w", err)
		}
		defer r.Close()

		out, err := io.ReadAll(r)
		if err != nil {
			return resp, fmt.Errorf("zstd: failed to decompress response: %w", err)
		}
		data = out
	}

	if err := sonic.Unmarshal(data, &resp); err != nil {
		return resp, fmt.Errorf("unmarshal response: %w", err)
	}
	return resp, nil
}

func createAuthHeaders(k *kami.Kami, body []byte) (map[string]string, error) {
	if k == nil {
		return nil, fmt.Errorf("kami client is nil")
	}

	res, err := k.SignMessage(kami.SignMessageParams{Message: string(body)})
	if err != nil {
		log.Error().Err(err).Msg("kami: sign message failed")
		return nil, fmt.Errorf("sign message: %w", err)
	}

	sig := res.Data.Signature
	if sig == "" {
		return nil, fmt.Errorf("empty signature returned from kami")
	}

	headers := map[string]string{
		"x-signature": sig,
		"x-hotkey":    k.WalletHotkey,
	}

	return headers, nil
}
