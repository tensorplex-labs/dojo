package main

import (
	"os"
	"os/signal"
	"syscall"

	"github.com/joho/godotenv"
	"github.com/rs/zerolog/log"

	"github.com/tensorplex-labs/dojo/internal/config"
	"github.com/tensorplex-labs/dojo/internal/kami"
	"github.com/tensorplex-labs/dojo/internal/syntheticapi"
	"github.com/tensorplex-labs/dojo/internal/taskapi"
	"github.com/tensorplex-labs/dojo/internal/utils/logger"
	"github.com/tensorplex-labs/dojo/internal/utils/redis"
	"github.com/tensorplex-labs/dojo/internal/validator"
)

func main() {
	logger.Init()
	log.Info().Msg("Starting validator...")

	if err := godotenv.Load(); err != nil {
		log.Debug().Msg(".env not loaded; continuing with existing environment")
	}

	cfg, err := config.LoadConfig()
	if err != nil {
		log.Fatal().Err(err).Msg("failed to load environment configuration")
	}

	k, err := kami.NewKami(&cfg.KamiEnvConfig)
	if err != nil {
		log.Fatal().Err(err).Msg("failed to init kami client")
	}

	r, err := redis.NewRedis(&cfg.RedisEnvConfig)
	if err != nil {
		log.Error().Err(err).Msg("failed to init redis client, continuing without redis")
		r = nil
	}

	s, err := syntheticapi.NewSyntheticAPI(&cfg.SyntheticAPIEnvConfig)
	if err != nil {
		log.Fatal().Err(err).Msg("failed to load synthetic api env")
	}

	taskAPI, err := taskapi.NewTaskAPI(&cfg.TaskAPIEnvConfig)
	if err != nil {
		log.Fatal().Err(err).Msg("failed to init task api client")
	}

	v := validator.NewValidator(&cfg.ValidatorEnvConfig, k, taskAPI, r, s)

	// setup signal handling for graceful shutdown before starting validator
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)

	// listen for shutdown signal in a separate goroutine so we can start the validator
	go func() {
		<-sigChan
		log.Info().Msg("shutdown signal received, stopping validator")
		v.Stop()
	}()

	v.Start()

	// wait until validator context is cancelled (v.Stop will call Cancel())
	<-v.Ctx.Done()
	log.Info().Msg("validator stopped")
}
