package validator

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"sync"

	"github.com/rs/zerolog/log"

	chainutils "github.com/tensorplex-labs/dojo/internal/utils/chain_utils"
)

func (v *Validator) syncMetagraph() {
	v.mu.Lock()
	defer v.mu.Unlock()

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

	log.Info().Msgf("Metagraph synced. Found %d active miners with uid: %v", len(currentActiveMiners), currentActiveMiners)

	v.MetagraphData.Metagraph = newMetagraph.Data
	v.MetagraphData.CurrentActiveMinerUids = currentActiveMiners

	// v.mu.Unlock()
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

	active := len(v.MetagraphData.CurrentActiveMinerUids)
	log.Info().Msg(fmt.Sprintf("Starting task round with %d tasks", active))

	var wg sync.WaitGroup
	// for _, v := range v.MetagraphData.CurrentActiveMinerUids {
	for i := range []int{0, 1, 3, 4, 5} { // TODO: remove testing range to loop 5 tasks.
		// uid := v.MetagraphData.Hotkeys[v]
		uid := int64(158) // TODO: remove testing uid
		wg.Add(1)
		go func(i int, uid int64) {
			defer wg.Done()
			v.processCodegenTask(i, uid)
		}(i, uid)
	}

	wg.Wait()
	log.Info().Msgf("Tasks generation completed")
	os.Exit(1) // TODO: remove
}

func (v *Validator) canStartTaskRound(ctx context.Context) bool {
	if v.Redis == nil {
		log.Error().Msg("redis client is not initialized")
		return false
	}
	taskCount, generatedCount, err := v.taskTrackerPure(ctx)
	if err != nil {
		log.Error().Err(err).Msg("failed to get task tracker")
		return false
	}

	active := len(v.MetagraphData.CurrentActiveMinerUids)
	if active == 0 {
		log.Info().Msg("no active miners, skipping task round")
		return false
	}

	if int64(generatedCount) < int64(active) {
		log.Info().Msg(fmt.Sprintf("Tasks in pool %d, generated tasks %d and active miners %d. Not starting new task round", taskCount, generatedCount, active))
		return false
	}
	return true
}

// calling via redis so it doesn't pop the tasks out of the list
func (v *Validator) taskTrackerPure(ctx context.Context) (numOfTasks, numCompletionsGenerated int, err error) {
	vals, err := v.Redis.LRange(ctx, "synthetic:questions", 0, -1)
	if err != nil {
		return 0, 0, fmt.Errorf("lrange: %w", err)
	}
	complete := 0
	for _, t := range vals {
		if t == "" {
			continue
		}
		var taskData CachedTasks
		if err := json.Unmarshal([]byte(t), &taskData); err != nil {
			return len(vals), complete, fmt.Errorf("unmarshal: %w", err)
		}
		if v.isTaskReady(taskData) {
			complete++
		}
	}
	return len(vals), complete, nil
}

func (v *Validator) isTaskReady(taskData CachedTasks) bool {
	return taskData.AnsAugID != "" &&
		taskData.QaID != "" &&
		v.checkCompletionExists(taskData.QaID) &&
		v.checkCompletionExists(taskData.AnsAugID)
}

func (v *Validator) checkCompletionExists(qaID string) bool {
	exists, err := v.Redis.Get(v.Ctx, fmt.Sprintf("synthetic:answers:%s", qaID))
	if err != nil {
		log.Error().Err(err).Msg("failed to check if completion exists in redis")
		return false
	}
	return exists != ""
}
