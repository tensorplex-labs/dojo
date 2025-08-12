package miner

import (
	"context"
	"net"
	"time"

	"github.com/rs/zerolog/log"

	"github.com/tensorplex-labs/dojo/internal/kami"
	"github.com/tensorplex-labs/dojo/internal/synapse"
	chainutils "github.com/tensorplex-labs/dojo/internal/utils/chain_utils"
)

type Miner struct {
	cfg  *synapse.Config
	srv  *synapse.Server
	kami *kami.Kami
	axon kami.ServeAxonParams

	ctx    context.Context
	cancel context.CancelFunc
}

func NewMiner(cfg *synapse.Config, k *kami.Kami) *Miner {
	ipAddress := cfg.MinerEnvConfig.Address

	// Convert provided address (or discovered external IP) to integer
	var ipInt int
	if ipAddress != "" {
		// try direct parse
		p := net.ParseIP(ipAddress)
		if p == nil {
			// try DNS lookup
			addrs, err := net.LookupIP(ipAddress)
			if err == nil && len(addrs) > 0 {
				p = addrs[0]
			}
		}

		if p != nil {
			v, err := chainutils.IPv4ToInt(p)
			if err != nil {
				log.Error().Err(err).Str("address", ipAddress).Msg("invalid ipv4 address, falling back to external IP")
				if ext, extErr := chainutils.GetExternalIPInt(); extErr == nil {
					ipInt = int(ext)
				} else {
					log.Error().Err(extErr).Msg("failed to determine external IP")
					ipInt = 0
				}
			} else {
				ipInt = int(v)
			}
		} else {
			// couldn't parse or resolve, try external
			if ext, err := chainutils.GetExternalIPInt(); err == nil {
				ipInt = int(ext)
			} else {
				log.Error().Err(err).Msg("failed to determine external IP")
				ipInt = 0
			}
		}
	} else {
		// address empty, try external
		if ext, err := chainutils.GetExternalIPInt(); err == nil {
			ipInt = int(ext)
		} else {
			log.Error().Err(err).Msg("failed to determine external IP")
			ipInt = 0
		}
	}

	serveAxonParams := kami.ServeAxonParams{
		Version:      1,
		IP:           ipInt,
		Port:         int(cfg.Port),
		IPType:       0, // 0 for IPv4
		Netuid:       0, // default netuid
		Protocol:     0, // default protocol
		Placeholder1: 0,
		Placeholder2: 0,
	}

	ctx, cancel := context.WithCancel(context.Background())

	s := synapse.NewServer(*cfg, nil)
	return &Miner{cfg: cfg, srv: s, kami: k, axon: serveAxonParams, ctx: ctx, cancel: cancel}
}

func (m *Miner) Run() {
	m.ctx, m.cancel = context.WithCancel(context.Background())
	go func() {
		if err := m.srv.Start(m.ctx); err != nil {
			log.Error().Err(err).Msg("failed to start miner server")
		}
	}()
	log.Info().Str("address", m.cfg.Address).Msg("miner server started")
}

func (m *Miner) Stop() {
	if m.cancel != nil {
		m.cancel()
		// give some time for shutdown
		time.Sleep(100 * time.Millisecond)
	}
	log.Info().Msg("miner stopped")
}
