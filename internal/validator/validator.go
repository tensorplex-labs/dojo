// Package validator implements the validator runtime: metagraph sync, task
// orchestration, and communication with external services.
package validator

import (
	"context"
	"sync"
	"sync/atomic"
	"time"

	"github.com/rs/zerolog/log"

	"github.com/tensorplex-labs/dojo/internal/config"
	"github.com/tensorplex-labs/dojo/internal/kami"
	"github.com/tensorplex-labs/dojo/internal/syntheticapi"
	"github.com/tensorplex-labs/dojo/internal/taskapi"
	"github.com/tensorplex-labs/dojo/internal/utils/redis"
)

// Validator coordinates task rounds and on-chain state for a subnet.
type Validator struct {
	Kami         kami.KamiInterface
	TaskAPI      taskapi.TaskAPIInterface // TaskAPIInterface is used to interact with the task API
	Redis        redis.RedisInterface
	SyntheticAPI syntheticapi.SyntheticAPIInterface

	// Chain global state
	LatestBlock     int64
	MetagraphData   MetagraphData
	ValidatorHotkey string

	IntervalConfig  *IntervalConfig            // used for heartbeat and task round intervals
	ValidatorConfig *config.ValidatorEnvConfig // configuration for the validator

	Ctx    context.Context
	Cancel context.CancelFunc
	Wg     sync.WaitGroup

	mu               sync.Mutex  // mutex to protect shared data
	taskRoundRunning atomic.Bool // atomic flag to indicate if a task round is currently running
}

// NewValidator constructs a Validator with intervals based on environment.
func NewValidator(
	cfg *config.ValidatorEnvConfig,
	k kami.KamiInterface,
	taskAPI taskapi.TaskAPIInterface,
	r redis.RedisInterface,
	s syntheticapi.SyntheticAPIInterface,
) *Validator {
	var intervalConfig *IntervalConfig
	if cfg.Environment == "dev" || cfg.Environment == "DEV" {
		log.Warn().Msg("Validator is running in dev/test mode, this is not recommended for production!")
		intervalConfig = &IntervalConfig{
			MetagraphInterval: 5 * time.Second,
			TaskRoundInterval: 10 * time.Second,
			BlockInterval:     2 * time.Second,
		}
	} else {
		intervalConfig = &IntervalConfig{
			MetagraphInterval: 30 * time.Second,
			TaskRoundInterval: 15 * time.Minute,
			BlockInterval:     12 * time.Second,
		}
	}

	ctx, cancel := context.WithCancel(context.Background())

	return &Validator{
		Kami:         k,
		TaskAPI:      taskAPI,
		Redis:        r,
		SyntheticAPI: s,

		LatestBlock:     0,
		MetagraphData:   MetagraphData{},
		ValidatorHotkey: "",

		IntervalConfig:  intervalConfig,
		ValidatorConfig: cfg,

		Ctx:    ctx,
		Cancel: cancel,
		Wg:     sync.WaitGroup{},

		mu: sync.Mutex{},
	}
}

// runTicker runs a function periodically until the provided context is canceled.
// fn is executed in its own goroutine to ensure the ticker loop can exit quickly
// when the context is canceled.
func (v *Validator) runTicker(ctx context.Context, d time.Duration, fn func()) {
	defer v.Wg.Done()
	t := time.NewTicker(d)
	defer t.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-t.C:
			go fn()
		}
	}
}

// Start initializes validator hotkey and kicks off periodic routines.
func (v *Validator) Start() {
	keyringData, err := v.Kami.GetKeyringPair()
	if err != nil {
		log.Error().Err(err).Msg("failed to get validator hotkey")
		return
	}

	log.Info().Msgf("Validator hotkey %s loaded!", keyringData.Data.KeyringPair.Address)

	v.ValidatorHotkey = keyringData.Data.KeyringPair.Address

	v.Wg.Add(3)
	go v.runTicker(v.Ctx, v.IntervalConfig.TaskRoundInterval, func() {
		v.sendTaskRound()
	})

	go v.runTicker(v.Ctx, v.IntervalConfig.MetagraphInterval, func() {
		v.syncMetagraph()
	})

	go v.runTicker(v.Ctx, v.IntervalConfig.BlockInterval, func() {
		v.syncBlock()
	})
}

// Stop cancels background routines and waits for them to finish.
func (v *Validator) Stop() {
	if v.Cancel != nil {
		v.Cancel()
	}
	v.Wg.Wait()
}
