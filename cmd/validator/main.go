package main

import (
	"context"
	"os"
	"os/signal"
	"syscall"

	"github.com/joho/godotenv"
	"github.com/rs/zerolog/log"
	"github.com/tensorplex-labs/dojo/internal/validator"
	"github.com/tensorplex-labs/dojo/pkg/chain"
	"github.com/tensorplex-labs/dojo/pkg/utils/logger"
)

func main() {
	logger.Init()
	log.Info().Msg("Starting validator...")

	err := godotenv.Load()
	if err != nil {
		log.Fatal().Msg("Error loading .env file")
	}

	log.Info().Msg("Validator service is starting...")

	chainRepo, err := chain.NewKamiChainRepo()
	if err != nil {
		log.Fatal().Err(err).Msg("Error initializing Kami")
	}

	_, cancel := context.WithCancel(context.Background())
	defer cancel()

	v := validator.NewValidator(chainRepo)
	v.Run()

	// Setup signal handling for graceful shutdown
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)

	log.Info().Msg("Validator is running. Press Ctrl+C to shutdown...")

	// Wait for shutdown signal
	<-sigChan
	log.Info().Msg("Shutdown signal received, gracefully shutting down...")

	// Cancel context to signal all goroutines to stop
	cancel()

	// Shutdown the validator's worker pool
	v.Stop()

	log.Info().Msg("Validator shutdown complete")
}
