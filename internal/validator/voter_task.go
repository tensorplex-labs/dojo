package validator

import (
	"fmt"
	"sync"
	"time"

	"github.com/bytedance/sonic"
	"github.com/rs/zerolog/log"
)

func (v *Validator) processVotingTasks() {
	// get tasks that are in voting period
	log.Info().Msg("Fetching voting tasks from Task API...")

	headers, err := v.setupAuthHeaders()
	if err != nil {
		log.Error().Err(err).Msg("failed to setup authentication")
		return
	}

	tasks, err := v.TaskAPI.GetVotingTasks(headers)
	if err != nil {
		log.Error().Err(err).Msg("failed to fetch voting tasks")
		return
	}

	voterList, err := v.buildVoterList()
	if err != nil {
		log.Error().Err(err).Msg("failed to build voter list")
		return
	}
	var wg sync.WaitGroup
	for _, task := range tasks.Data {
		id := task.ID
		createdAt, err := time.Parse(time.RFC3339, task.CreatedAt)
		if err != nil {
			log.Error().Err(err).Msgf("failed to parse created at time for task %s", id)
			continue
		}
		expireAt, err := time.Parse(time.RFC3339, task.ExpireAt)
		if err != nil {
			log.Error().Err(err).Msgf("failed to parse expire at time for task %s", id)
			continue
		}

		wg.Add(1)
		go func(taskID string, voters []byte, createdAt, expireAt time.Time) {
			err := v.cacheVoters(taskID, voters, createdAt, expireAt)
			if err != nil {
				log.Error().Err(err).Msgf("failed to cache voters for task %s", taskID)
			} else {
				log.Debug().Msgf("Successfully cached voters for task %s", taskID)
			}
		}(id, voterList, createdAt, expireAt)
	}

	wg.Wait()
	log.Info().Msg("Finished caching voting tasks")
}

func (v *Validator) cacheVoters(taskID string, voters []byte, createdAt, expireAt time.Time) error {
	// skip tasks that are expiring in less than an hour
	if expireAt.Sub(createdAt) < 1*time.Hour {
		log.Debug().Msgf("Task %s is expiring in less than an hour, skipping caching voters", taskID)
		return nil
	}

	voterKey := fmt.Sprintf("voters:%s", taskID)
	exists, err := v.Redis.Get(v.Ctx, voterKey)
	if err != nil {
		log.Error().Err(err).Msgf("failed to check if task %s has been voted on", taskID)
		return err
	}
	if exists != "" {
		log.Debug().Msgf("Voters already cached for task %s", taskID)
		return nil
	}

	err = v.Redis.Set(v.Ctx, voterKey, string(voters), 2*v.IntervalConfig.ScoreResetInterval)
	if err != nil {
		log.Error().Err(err).Msgf("failed to cache voters for task %s", taskID)
		return err
	}
	return nil
}

func (v *Validator) buildVoterList() ([]byte, error) {
	var voters []string
	for _, uid := range v.MetagraphData.CurrentActiveMinerUids {
		hotkey := v.MetagraphData.Metagraph.Hotkeys[uid]
		voters = append(voters, hotkey)
	}

	jsonData, err := sonic.Marshal(voters)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal voter list: %w", err)
	}
	return jsonData, nil
}
