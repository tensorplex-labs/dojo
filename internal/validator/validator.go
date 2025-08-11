package validator

import (
	"context"
	"sync"
	"time"

	"github.com/rs/zerolog/log"
	"github.com/tensorplex-labs/dojo/internal/config"
	"github.com/tensorplex-labs/dojo/internal/kami"
	"github.com/tensorplex-labs/dojo/internal/synapse"
	chainutils "github.com/tensorplex-labs/dojo/internal/utils/chain_utils"
)

type Validator struct {
	Kami            *kami.Kami
	MetagraphData   MetagraphData
	ValidatorHotkey string
	TaskPool        any // placeholder for task pool if needed
	Client          *synapse.Client
	IntervalConfig  *IntervalConfig            // used for heartbeat and task round intervals
	ValidatorConfig *config.ValidatorEnvConfig // configuration for the validator

	Ctx    context.Context
	Cancel context.CancelFunc
	Wg     sync.WaitGroup
}

func NewValidator(cfg *config.ValidatorEnvConfig, kami *kami.Kami, taskPool any) *Validator {
	intervalConfig := &IntervalConfig{
		HeartbeatInterval: 60 * time.Second,
		MetagraphInterval: 30 * time.Second,
		TaskRoundInterval: 15 * time.Minute,
		BlockInterval:     12 * time.Second,
	}

	ctx, cancel := context.WithCancel(context.Background())

	return &Validator{
		Kami:            kami,
		TaskPool:        taskPool,
		Client:          synapse.NewClient(kami),
		MetagraphData:   MetagraphData{},
		IntervalConfig:  intervalConfig,
		ValidatorConfig: cfg,

		Ctx:    ctx,
		Cancel: cancel,
		Wg:     sync.WaitGroup{},
	}
}

// runTicker runs a function periodically until the provided context is canceled.
func (v *Validator) runTicker(ctx context.Context, d time.Duration, fn func()) {
	defer v.Wg.Done()
	t := time.NewTicker(d)
	defer t.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-t.C:
			fn()
		}
	}
}

func (v *Validator) Start() {
	_, err := chainutils.GetHotkey(v.Kami)
	if err != nil {
		log.Error().Err(err).Msg("failed to get validator hotkey")
		return
	}

	v.Wg.Add(2)
	go v.runTicker(v.Ctx, v.IntervalConfig.HeartbeatInterval, func() {
		v.heartBeat(v.Ctx, v.Client, v.ValidatorHotkey)
	})

	go v.runTicker(v.Ctx, v.IntervalConfig.TaskRoundInterval, func() {
		v.sendTaskRound(v.Ctx, v.Client, v.ValidatorHotkey)
	})
}

func (v *Validator) Stop() {
	if v.Cancel != nil {
		v.Cancel()
	}
	v.Wg.Wait()
}
