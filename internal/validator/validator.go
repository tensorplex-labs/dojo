package validator

import (
	"context"
	"fmt"
	"os"
	"strconv"
	"sync"
	"time"

	"github.com/rs/zerolog/log"

	"github.com/tensorplex-labs/dojo/internal/kami"
	"github.com/tensorplex-labs/dojo/internal/synapse"
)

type Config struct {
	MinerAxons  map[string]string
	Interval    time.Duration
	ValidatorID string
}

type Validator struct {
	kami   *kami.Kami
	cfg    Config
	client *synapse.Client

	ctx    context.Context
	cancel context.CancelFunc
	wg     sync.WaitGroup
}

func NewValidator(k *kami.Kami) *Validator {
	hb := os.Getenv("SYNAPSE_HEARTBEAT_URL")

	id := os.Getenv("VALIDATOR_ID")
	if id == "" && k != nil {
		id = k.WalletHotkey
	}

	interval := 10 * time.Second

	minerAxons := []string{}
	if k != nil {
		netuid := 1
		if v := os.Getenv("NETUID"); v != "" {
			if n, err := strconv.Atoi(v); err == nil {
				netuid = n
			}
		}

		res, err := k.GetMetagraph(netuid)
		if err != nil {
			log.Error().Err(err).Int("netuid", netuid).Msg("failed to fetch metagraph from kami")
		} else {
			for uid, ax := range res.Data.Axons {
				if ax.IP == "" || ax.Port == 0 {
					continue
				}

				hotkey := res.Data.Hotkeys[uid]
				rootStake := res.Data.TaoStake[uid]
				alphaStake := res.Data.AlphaStake[uid]

				validator := 


				u := fmt.Sprintf("http://%s:%d/heartbeat", ax.IP, ax.Port)
				urls = append(urls, u)
			}
		}
	}

	if len(urls) == 0 {
		if hb != "" {
			urls = append(urls, hb)
		} else {
			urls = append(urls, "http://127.0.0.1:8080/heartbeat")
		}
	}

	clientCfg := synapse.Config{
		Address:       urls[0],
		ClientTimeout: 5 * time.Second,
		RetryMax:      1,
		RetryWait:     500 * time.Millisecond,
	}

	v := &Validator{
		kami:   k,
		cfg:    Config{HeartbeatURLs: urls, Interval: interval, ValidatorID: id},
		client: synapse.NewClient(clientCfg),
	}

	log.Info().Int("targets", len(urls)).Strs("urls", urls).Msg("validator will send heartbeats to")

	return v
}

func (v *Validator) Run() {
	v.ctx, v.cancel = context.WithCancel(context.Background())
	v.wg.Add(1)
	go v.loop()
	log.Info().Msg("validator client started")
}

func (v *Validator) loop() {
	defer v.wg.Done()
	t := time.NewTicker(v.cfg.Interval)
	defer t.Stop()

	for {
		select {
		case <-v.ctx.Done():
			log.Info().Msg("validator loop stopping")
			return
		case <-t.C:
			v.sendHeartbeats()
		}
	}
}

func (v *Validator) sendHeartbeats() {
	if v.client == nil {
		log.Error().Msg("no synapse client available")
		return
	}

	for _, url := range v.cfg.HeartbeatURLs {
		hb := synapse.HeartbeatRequest{
			ValidatorID: v.cfg.ValidatorID,
			Timestamp:   time.Now().UnixNano(),
		}

		ctx, cancel := context.WithTimeout(v.ctx, 5*time.Second)
		resp, err := v.client.SendHeartbeat(ctx, url, hb)
		cancel()
		if err != nil {
			log.Error().Err(err).Str("url", url).Msg("failed to send heartbeat")
			continue
		}
		log.Info().Str("url", url).Str("status", resp.Status).Int64("received_at", resp.ReceivedAt).Msg("heartbeat response")
	}
}

func (v *Validator) Stop() {
	if v.cancel != nil {
		v.cancel()
	}
	v.wg.Wait()
	log.Info().Msg("validator stopped")
}
