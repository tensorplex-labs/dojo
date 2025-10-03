package validator

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/rs/zerolog/log"

	chainutils "github.com/tensorplex-labs/dojo/internal/utils/chain_utils"
)

func (v *Validator) syncMetagraph() {
	log.Info().Msg(fmt.Sprintf("syncing metagraph data for subnet: %d", v.ValidatorConfig.Netuid))
	var currentActiveMiners []int64

	newMetagraph, err := v.Kami.GetMetagraph(v.ValidatorConfig.Netuid)
	if err != nil {
		log.Error().Err(err).Msg("failed to get metagraph")
		return
	}

	if v.ValidatorConfig.Environment == "dev" {
		currentActiveMiners = []int64{202, 93, 201}
	} else {
		for uid := range newMetagraph.Data.Hotkeys {
			rootStake := newMetagraph.Data.TaoStake[uid]
			alphaStake := newMetagraph.Data.AlphaStake[uid]

			miner, err := chainutils.CheckIfMiner(alphaStake, rootStake)
			if err != nil {
				log.Error().Err(err).Msg("failed to check miner status")
				continue
			}

			if miner {
				currentActiveMiners = append(currentActiveMiners, int64(uid))
			}
		}
	}

	log.Info().Msgf("Metagraph synced. Found %d active miners with uid: %v", len(currentActiveMiners), currentActiveMiners)
	v.mu.Lock()
	defer v.mu.Unlock()

	v.MetagraphData.Metagraph = newMetagraph.Data
	v.MetagraphData.CurrentActiveMinerUids = currentActiveMiners
}

func (v *Validator) syncBlock() {
	log.Info().Msg(fmt.Sprintf("syncing latest block. current block : %d", v.LatestBlock))
	newBlockResp, err := v.Kami.GetLatestBlock()
	if err != nil {
		log.Error().Err(err).Msg("failed to get latest block")
		return
	}
	v.mu.Lock()
	defer v.mu.Unlock()

	v.LatestBlock = int64(newBlockResp.Data.BlockNumber)
}

func (v *Validator) startScoring() {
	if v.MetagraphData.Metagraph.Hotkeys == nil {
		log.Info().Msg("metagraph hotkeys is nil, skipping scoring for this step")
		return
	}
	v.processTasksToScore(v.LatestScoresData)
}

func (v *Validator) startVotersCache() {
	if v.MetagraphData.Metagraph.Hotkeys == nil {
		log.Info().Msg("metagraph hotkeys is nil, skipping voters cache for this step")
		return
	}

	if v.MetagraphData.CurrentActiveMinerUids == nil {
		log.Info().Msg("no active miners, skipping voters cache for this step")
		return
	}

	v.processVotingTasks()
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
	log.Info().Msg(fmt.Sprintf("Starting task round: miners active %d", active))

	var processedMiners ProcessedMiners
	v.processCodegenTask(v.MetagraphData.CurrentActiveMinerUids, &processedMiners)

	log.Info().Msgf("Tasks generation completed")
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
func (v *Validator) taskTrackerPure(ctx context.Context) (total, completed int, err error) {
	vals, err := v.Redis.LRange(ctx, redisSyntheticQAKey, 0, -1)
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
	exists, err := v.Redis.Get(v.Ctx, fmt.Sprintf("%s:%s", redisSyntheticAnswersKey, qaID))
	if err != nil {
		log.Error().Err(err).Msg("failed to check if completion exists in redis")
		return false
	}
	return exists != ""
}

func (v *Validator) setWeights(latestScoresData ScoresData) {
	weightSettingSteps := int(v.IntervalConfig.WeightSettingInterval / v.IntervalConfig.ScoringInterval)

	if latestScoresData.Step == 0 || latestScoresData.Step%weightSettingSteps != 0 {
		nextWeightSettingStep := ((latestScoresData.Step / weightSettingSteps) + 1) * weightSettingSteps
		remainingSteps := nextWeightSettingStep - latestScoresData.Step
		remainingMinutes := time.Duration(remainingSteps) * v.IntervalConfig.ScoringInterval

		log.Info().Msgf("Current score step is %d. Next weight setting in %.0f minutes",
			latestScoresData.Step, remainingMinutes.Minutes())
		return
	}

	uids := make([]int64, len(latestScoresData.Scores))
	for i := range uids {
		uids[i] = int64(i)
	}

	weights := chainutils.ClampNegativeWeights(latestScoresData.Scores)

	if err := v.setWeightsOnChain(uids, weights); err != nil {
		log.Error().Err(err).Msg("failed to set weights")
	}
}
