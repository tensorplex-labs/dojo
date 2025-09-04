package validator

import (
	"context"
	"fmt"
	"sync"

	"github.com/rs/zerolog/log"

	chainutils "github.com/tensorplex-labs/dojo/internal/utils/chain_utils"
)

func (v *Validator) syncMetagraph() {
	v.mu.Lock()

	log.Info().Msg(fmt.Sprintf("syncing metagraph data for subnet: %d", v.ValidatorConfig.Netuid))
	newMetagraph, err := v.Kami.GetMetagraph(v.ValidatorConfig.Netuid)
	if err != nil {
		log.Error().Err(err).Msg("failed to get metagraph")
		return
	}

	var currentActiveMiners []int64
	for uid, axon := range newMetagraph.Data.Axons {
		hotkey := newMetagraph.Data.Hotkeys[uid]
		rootStake := newMetagraph.Data.TaoStake[uid]
		alphaStake := newMetagraph.Data.AlphaStake[uid]

		miner, err := chainutils.CheckIfMiner(alphaStake, rootStake)
		log.Debug().Msgf("Miner check for UID %d of %s returned: %t", uid, hotkey, miner)
		if err != nil {
			log.Error().Err(err).Msg("failed to check miner status")
			continue
		}
		if miner {
			currentActiveMiners = append(currentActiveMiners, int64(uid))
			log.Debug().Msgf("Found active miner UID %d at %s:%d", uid, axon.IP, axon.Port)
		}
	}

	log.Info().Msgf("Metagraph synced. Found %d active miners", len(currentActiveMiners))

	v.MetagraphData.Metagraph = newMetagraph.Data
	v.MetagraphData.CurrentActiveMinerUids = currentActiveMiners

	v.mu.Unlock()
}

func (v *Validator) syncBlock() {
	v.mu.Lock()

	log.Info().Msg(fmt.Sprintf("syncing latest block. current block : %d", v.LatestBlock))
	newBlockResp, err := v.Kami.GetLatestBlock()
	if err != nil {
		log.Error().Err(err).Msg("failed to get latest block")
		return
	}

	v.LatestBlock = int64(newBlockResp.Data.BlockNumber)
	v.mu.Unlock()
}

func (v *Validator) sendTaskRound() {
	if !v.taskRoundRunning.CompareAndSwap(false, true) {
		return
	}
	defer v.taskRoundRunning.Store(false)
	ctx := v.Ctx
	if !v.canStartTaskRound(ctx) {
		return
	}

	currentRound, err := v.incrementTaskRound()
	if err != nil {
		log.Error().Err(err).Msg("failed to increment task round")
		return
	}
	log.Info().Msg(fmt.Sprintf("starting task round %d", currentRound))

	active := len(v.MetagraphData.CurrentActiveMinerUids)
	log.Info().Msg(fmt.Sprintf("sending task round with %d tasks", active))

	var wg sync.WaitGroup
	for i := range v.MetagraphData.CurrentActiveMinerUids {
		uid := v.MetagraphData.CurrentActiveMinerUids[i]
		wg.Add(1)
		go func(i int, uid int64) {
			defer wg.Done()
			v.processCodegenTask(currentRound, i, uid)
		}(i, uid)
	}

	wg.Wait()
	log.Info().Msgf("task round %d completed", currentRound)
}

func (v *Validator) canStartTaskRound(ctx context.Context) bool {
	if v.Redis == nil {
		log.Error().Msg("redis client is not initialized")
		return false
	}
	taskCount, err := v.Redis.LLen(ctx, "synthetic:questions")
	if err != nil {
		log.Error().Err(err).Msg("failed to get task count from redis")
		return false
	}
	active := len(v.MetagraphData.CurrentActiveMinerUids)
	if active == 0 {
		log.Info().Msg("no active miners, skipping task round")
		return false
	}
	if taskCount < int64(active) {
		log.Info().Msg("not enough tasks in redis, skipping task round")
		return false
	}
	return true
}
