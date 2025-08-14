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
	"github.com/tensorplex-labs/dojo/internal/utils/logger"
	"github.com/tensorplex-labs/dojo/internal/utils/redis"
	"github.com/tensorplex-labs/dojo/internal/validator"
)

func main() {
	logger.Init()
	log.Info().Msg("Starting validator...")

	_ = godotenv.Load() // best-effort

	cfg, err := config.LoadValidatorEnv()
	if err != nil {
		log.Fatal().Err(err).Msg("failed to load validator env")
	}

	kamiCfg, err := config.LoadKamiEnv()
	if err != nil {
		log.Fatal().Err(err).Msg("failed to load kami env")
	}
	k, err := kami.NewKami(kamiCfg)
	if err != nil {
		log.Fatal().Err(err).Msg("failed to init kami client")
	}

	redisCfg, err := config.LoadRedisEnv()
	var r *redis.Redis
	if err != nil {
		log.Error().Err(err).Msg("failed to load redis env, continuing without redis")
	} else {
		r, err = redis.NewRedis(redisCfg)
		if err != nil {
			log.Error().Err(err).Msg("failed to init redis client, continuing without redis")
			r = nil
		}
	}

	syntheticApiCfg, err := config.LoadSyntheticApiEnv()
	if err != nil {
		log.Fatal().Err(err).Msg("failed to load synthetic api env")
	}

	s, err := syntheticapi.NewSyntheticApi(syntheticApiCfg)
	if err != nil {
		log.Fatal().Err(err).Msg("failed to init synthetic api client")
	}

	v := validator.NewValidator(cfg, k, nil, r, s)
	v.Start()

	// graceful shutdown
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)
	<-sigChan
	log.Info().Msg("shutdown signal received, stopping validator")
	v.Stop()
}
