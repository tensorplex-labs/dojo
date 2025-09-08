package validator

import "github.com/rs/zerolog/log"

func (v *Validator) processTasksToScore() {
	// retrieve tasks that are expired but not scored yet
	tasksToScore, err := v.TaskAPI.GetExpiredTasks(v.ValidatorHotkey)
	if err != nil {
		log.Error().Err(err).Msg("failed to get expired tasks")
		return
	}
	log.Info().Msgf("Found %d tasks to score", len(tasksToScore.Data.Votes))

	// check if task is trap round

	// calculate score for each task

	// store score in redis or file??
}
