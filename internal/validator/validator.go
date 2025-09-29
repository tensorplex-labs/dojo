// Package validator implements the validator runtime: metagraph sync, task
// orchestration, and communication with external services.
package validator

import (
	"context"
	"os"
	"sync"
	"sync/atomic"
	"time"

	"github.com/bytedance/sonic"
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
	LatestBlock      int64
	MetagraphData    MetagraphData
	ValidatorHotkey  string
	LatestScoresData ScoresData

	IntervalConfig  *config.IntervalConfig     // used for heartbeat and task round intervals
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
	intervalConfig := config.NewIntervalConfig(cfg.Environment)

	keyringData, err := k.GetKeyringPair()
	if err != nil {
		log.Error().Err(err).Msg("failed to get validator hotkey")
		return nil
	}

	scoresFile, err := os.ReadFile(scoresFileName)
	if err != nil {
		if os.IsNotExist(err) {
			log.Info().Msg("scores file not found, initializing with default scores")
			initializeScores(scoresFileName)
			scoresFile, err = os.ReadFile(scoresFileName)
			if err != nil {
				log.Error().Err(err).Msg("failed to read newly created scores file")
				return nil
			}
		} else {
			log.Error().Err(err).Msg("failed to load scores from file")
			return nil
		}
	}

	var latestScoresData ScoresData
	if err := sonic.Unmarshal(scoresFile, &latestScoresData); err != nil {
		log.Error().Err(err).Msg("failed to unmarshal scores from file")
		return nil
	}

	log.Info().Msgf("Loaded latest scores from file: step %d, scores %+v", latestScoresData.Step, latestScoresData.Scores)

	ctx, cancel := context.WithCancel(context.Background())

	log.Info().Msgf("Validator hotkey %s loaded!", keyringData.Data.KeyringPair.Address)

	return &Validator{
		Kami:         k,
		TaskAPI:      taskAPI,
		Redis:        r,
		SyntheticAPI: s,

		LatestBlock:      0,
		MetagraphData:    MetagraphData{},
		ValidatorHotkey:  keyringData.Data.KeyringPair.Address,
		LatestScoresData: latestScoresData,

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
	v.Wg.Add(1)
	go v.runTicker(v.Ctx, v.IntervalConfig.TaskRoundInterval, func() {
		v.sendTaskRound()
	})

	v.Wg.Add(1)
	go v.runTicker(v.Ctx, v.IntervalConfig.MetagraphInterval, func() {
		v.syncMetagraph()
	})

	v.Wg.Add(1)
	go v.runTicker(v.Ctx, v.IntervalConfig.BlockInterval, func() {
		v.syncBlock()
	})

	v.Wg.Add(1)
	go v.runTicker(v.Ctx, v.IntervalConfig.ScoringInterval, func() {
		v.startScoring()
		v.setWeights(v.LatestScoresData)
	})
}

// Stop cancels background routines and waits for them to finish.
func (v *Validator) Stop() {
	if v.Cancel != nil {
		v.Cancel()
	}
	v.Wg.Wait()
}
