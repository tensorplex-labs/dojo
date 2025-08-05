package miner

import (
	"context"

	"github.com/gofiber/fiber/v2"
	"github.com/rs/zerolog/log"
	"github.com/sethvargo/go-envconfig"
	"github.com/tensorplex-labs/dojo/internal/core"
	"github.com/tensorplex-labs/dojo/pkg/chain"
	"github.com/tensorplex-labs/dojo/pkg/config"
	"github.com/tensorplex-labs/dojo/pkg/schnitz"
)

func NewMiner(chainRepo chain.ChainProvider) *Miner {
	ctx := context.Background()

	var envCfg config.MinerEnvConfig
	if err := envconfig.Process(ctx, &envCfg); err != nil {
		log.Fatal().Err(err).Msg("Failed to process environment variables for Miner")
	}
	// Create server with custom config
	serverConfig := &schnitz.ServerConfig{
		Host: "0.0.0.0",
		Port: envCfg.ServerPort,
	}

	server := schnitz.NewServer(serverConfig)
	return &Miner{
		Node:   core.NewNode(chainRepo),
		server: server,
		config: &envCfg,
	}
}

func (m *Miner) ServeIP() {
	ipAddr, err := m.server.GetExternalIP()
	if err != nil {
		log.Error().Err(err).Msg("Failed to get external IP address")
		return
	}

	getMetagraphFn := m.ChainRepo.GetSubnetMetagraph(m.config.Netuid)
	latestState, err := getMetagraphFn(m.ChainState)
	if err != nil {
		log.Error().Err(err).Msg("Failed to get latest metagraph")
		return
	}
	m.ChainState = latestState

	axon := chain.FindAxonByHotkey(latestState.GetMetagraph(), m.config.WalletHotkey)
	if axon != nil {
		if axon.IP == ipAddr && axon.Port == m.config.ServerPort {
			log.Info().Msg("Miner IP and Port already in metagraph, skipping serve axon.")
			return
		}
	}

	err = m.ChainRepo.SetIP(ipAddr, m.config.ServerPort)
	if err != nil {
		log.Error().Err(err).Msg("Failed to set IP in metagraph")
		return
	}
}

func (m *Miner) Run() {
	ctx := context.Background()
	if err := m.Node.Start(ctx); err != nil {
		log.Fatal().Err(err).Msg("Failed to start node")
	}

	m.RegisterMetagraphSync()
	m.StartBlockUpdater()
	m.ServeIP()

	schnitz.ServeRoute(m.server, func(c *fiber.Ctx, req core.Heartbeat) (core.Heartbeat, error) {
		log.Info().Any("request", req).Msg("Heartbeat handler called")
		req.Ack = true
		return req, nil
	})

	m.server.Start()
	// TODO: task serving logic
}
