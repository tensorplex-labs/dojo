package synapse

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"strings"

	"github.com/bytedance/sonic"
	"github.com/go-resty/resty/v2"
	"github.com/klauspost/compress/zstd"
	"github.com/rs/zerolog/log"
)

type Client struct {
	httpClient *resty.Client
	cfg        Config
}

func NewClient(cfg Config) *Client {
	cli := resty.New()

	cli.SetRetryCount(cfg.RetryMax)
	cli.SetTimeout(cfg.ClientTimeout)
	cli.SetRetryWaitTime(cfg.RetryWait)
	cli.SetRetryMaxWaitTime(cfg.RetryWait * 2)
	return &Client{httpClient: cli, cfg: cfg}
}

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
