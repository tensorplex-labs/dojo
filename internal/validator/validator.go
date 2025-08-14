package validator

import (
	"context"
	"sync"
	"time"

	"github.com/rs/zerolog/log"
	"github.com/tensorplex-labs/dojo/internal/config"
	"github.com/tensorplex-labs/dojo/internal/kami"
	"github.com/tensorplex-labs/dojo/internal/synapse"
	"github.com/tensorplex-labs/dojo/internal/syntheticapi"
	"github.com/tensorplex-labs/dojo/internal/utils/redis"
)

type Validator struct {
	Kami         kami.KamiInterface
	TaskPool     any // placeholder for task pool if needed
	Client       *synapse.Client
	Redis        redis.RedisInterface
	SyntheticApi syntheticapi.SyntheticApiInterface

	// Chain global state
	LatestBlock     int64
	MetagraphData   MetagraphData
	ValidatorHotkey string

	IntervalConfig  *IntervalConfig            // used for heartbeat and task round intervals
	ValidatorConfig *config.ValidatorEnvConfig // configuration for the validator

	Ctx    context.Context
	Cancel context.CancelFunc
	Wg     sync.WaitGroup

	mu sync.Mutex // mutex to protect shared data
}

func NewValidator(cfg *config.ValidatorEnvConfig, kami kami.KamiInterface, taskPool any, redis redis.RedisInterface, syntheticApi syntheticapi.SyntheticApiInterface) *Validator {
	intervalConfig := &IntervalConfig{
		MetagraphInterval: 30 * time.Second,
		TaskRoundInterval: 15 * time.Minute,
		BlockInterval:     12 * time.Second,
	}

	ctx, cancel := context.WithCancel(context.Background())

	return &Validator{
		Kami:         kami,
		TaskPool:     taskPool,
		Redis:        redis,
		SyntheticApi: syntheticApi,

		LatestBlock:     0,               // will be updated during block processing
		MetagraphData:   MetagraphData{}, // initialize with empty data
		ValidatorHotkey: "",              // will be set after fetching from Kami

		IntervalConfig:  intervalConfig,
		ValidatorConfig: cfg,

		Ctx:    ctx,
		Cancel: cancel,
		Wg:     sync.WaitGroup{},

		mu: sync.Mutex{}, // initialize mutex
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

func (v *Validator) Start() {
	_, err := v.Kami.GetKeyringPair()
	if err != nil {
		log.Error().Err(err).Msg("failed to get validator hotkey")
		return
	}

	v.Wg.Add(3)
	go v.runTicker(v.Ctx, v.IntervalConfig.TaskRoundInterval, func() {
		v.sendTaskRound(v.Ctx, v.Client, v.ValidatorHotkey)
	})

	go v.runTicker(v.Ctx, v.IntervalConfig.MetagraphInterval, func() {
		v.syncMetagraph()
	})

	go v.runTicker(v.Ctx, v.IntervalConfig.BlockInterval, func() {
		v.syncBlock()
	})
}

func (v *Validator) Stop() {
	if v.Cancel != nil {
		v.Cancel()
	}
	v.Wg.Wait()
}
