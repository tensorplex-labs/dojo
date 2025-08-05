package main

import (
	"context"
	"os"
	"os/signal"
	"syscall"

	"github.com/joho/godotenv"
	"github.com/rs/zerolog/log"
	"github.com/tensorplex-labs/dojo/internal/miner"
	"github.com/tensorplex-labs/dojo/pkg/chain"
	"github.com/tensorplex-labs/dojo/pkg/utils/logger"
)

func main() {
	logger.Init()
	log.Info().Msg("Starting miner...")

	err := godotenv.Load()
	if err != nil {
		log.Fatal().Msg("Error loading .env file")
	}

	log.Info().Msg("Miner service is starting...")

	chainRepo, err := chain.NewKamiChainRepo()
	if err != nil {
		log.Fatal().Err(err).Msg("Error initializing Kami")
	}

	_, cancel := context.WithCancel(context.Background())
	defer cancel()

	m := miner.NewMiner(chainRepo)
	m.Run()

	// Setup signal handling for graceful shutdown
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)

	log.Info().Msg("Miner is running. Press Ctrl+C to shutdown...")

	// Wait for shutdown signal
	<-sigChan
	log.Info().Msg("Shutdown signal received, gracefully shutting down...")

	// Cancel context to signal all goroutines to stop
	cancel()

	// Shutdown the miner's worker pool
	m.Stop()

	log.Info().Msg("Miner shutdown complete")
}
