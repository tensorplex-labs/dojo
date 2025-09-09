package validator

import (
	"github.com/rs/zerolog/log"
	"github.com/tensorplex-labs/dojo/internal/scoring"
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
	log.Info().Msgf("Found %d task(s) to score", tasksToScore.Data.Total)

	//TESTING
	// tasks := scoring.TestPvVResponse.Data.Tasks
	tasks := tasksToScore.Data.Tasks
	for _, task := range tasks {
		completions := task.Completions
		validator := make(map[string]string)
		generators := make(map[string]string)
		// TODO: Trap Scoring
		// check redis if task is trap round

		// pop redis if task is trap round

		// PvP/PvV Scoring
		for _, completion := range completions {
			log.Info().Msgf("Completion: %+v", completion)
			log.Info().Msgf("Validator hotkey: %s", task.ValidatorHotkey)
			if completion.ParticipantHotkey == task.ValidatorHotkey {
				validator[completion.ParticipantHotkey] = completion.ID
			} else {
				generators[completion.ParticipantHotkey] = completion.ID
			}
		}
		log.Info().Msgf("Generators: %+v", generators)
		discriminators := make(map[string]string)
		for _, vote := range task.Votes {
			discriminators[vote.VoterHotkey] = vote.ChosenCompletionID
		}
		var scores map[string]float64
		if len(validator) == 0 {
			log.Info().Msgf("Calculating PvP score for task %s", task.ID)
			scores = scoring.CalcPvPScores(discriminators, generators)
		} else {
			log.Info().Msgf("Calculating PvV score for task %s", task.ID)
			scores = scoring.CalcPvVScores(discriminators, generators, validator)
		}
		for addr, score := range scores {
			if score > 0.1 {
				log.Info().Msgf("Address: %s, Score: %f", addr, score)
			}
		}

	}

	// TODO: store score in redis or file??

	// TODO: update task status to scored

}
