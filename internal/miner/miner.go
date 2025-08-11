package miner

import (
	"context"
	"time"

	"github.com/rs/zerolog/log"

	"github.com/tensorplex-labs/dojo/internal/synapse"
)

type Config struct {
	Address string
}

type Miner struct {
	cfg    Config
	srv    *synapse.Server
	ctx    context.Context
	cancel context.CancelFunc
}

func NewMiner(cfg *synapse.Config) *Miner {
	c := Config{Address: ":8080"}
	if cfg != nil {
		c.Address = cfg.Address
	}

	s := synapse.NewServer(synapse.Config{Address: c.Address})
	return &Miner{cfg: c, srv: s}
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
