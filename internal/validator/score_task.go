package validator

import (
	"github.com/rs/zerolog/log"
	"github.com/tensorplex-labs/dojo/internal/taskapi"
)

func (v *Validator) processTasksToScore() {
	// retrieve tasks that are expired but not scored yet
	messageToSign, err := v.randomStringToSign()
	if err != nil {
		log.Error().Err(err).Msg("failed to sign message")
		return
	}
	signature, err := v.signMessage(messageToSign)
	if err != nil {
		log.Error().Err(err).Msg("failed to sign message")
		return
	}
	headers := taskapi.AuthHeaders{Hotkey: v.ValidatorHotkey, Signature: signature, Message: messageToSign}
	tasksToScore, err := v.TaskAPI.GetExpiredTasks(headers)
	if err != nil {
		log.Error().Err(err).Msg("failed to get expired tasks")
		return
	}
	log.Info().Msgf("Found %d tasks to score", len(tasksToScore.Data.Votes))

	// check redis if task is trap round

	// process into the format to call scoring functions

	// calculate score for each task

	// store score in redis or file??

	// pop redis if task is trap round
}
