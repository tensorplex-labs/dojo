package validator

import (
	"encoding/json"
	"fmt"
	"maps"
	"os"
	"time"

	"github.com/rs/zerolog/log"
	"github.com/tensorplex-labs/dojo/internal/scoring"
	"github.com/tensorplex-labs/dojo/internal/taskapi"
)

const scoreFileName = "all_task_scores.json"

// maps hotkeys to their completion id
type CompletionMaps struct {
	validator          map[string]string
	generators         map[string]string
	positiveGenerators map[string]string
	negativeGenerators map[string]string
}

func (v *Validator) processTasksToScore() {
	startTime := time.Now()

	headers, err := v.setupAuthHeaders()
	if err != nil {
		log.Error().Err(err).Msg("failed to setup authentication")
		return
	}

	tasks, err := v.fetchTasksToScore(headers)
	if err != nil {
		log.Error().Err(err).Msg("failed to fetch tasks")
		return
	}

	if len(tasks) == 0 {
		log.Info().Msg("No tasks to score")
		return
	}

	allTaskScores := v.calculateAllTaskScores(tasks)

	// TODO: revisit later, just a quick way to backup and save the scores to a local file
	if err := v.saveTaskScoresToFile(allTaskScores, scoreFileName); err != nil {
		log.Error().Err(err).Msg("failed to save task scores")
		return
	}

	// TODO: update task status to scored
	log.Info().Msgf("Processed %d tasks in %v", len(allTaskScores), time.Since(startTime))

}

func (v *Validator) fetchTasksToScore(headers taskapi.AuthHeaders) ([]taskapi.VoteTaskData, error) {
	tasksToScore, err := v.TaskAPI.GetExpiredTasks(headers)
	if err != nil {
		return nil, fmt.Errorf("failed to get expired tasks: %w", err)
	}

	log.Info().Msgf("Found %d task(s) to score", tasksToScore.Data.Total)
	return tasksToScore.Data.Tasks, nil
}

func (v *Validator) calculateAllTaskScores(tasks []taskapi.VoteTaskData) map[string]map[string]float64 {
	allTaskScores := make(map[string]map[string]float64)

	for _, task := range tasks {
		taskScores := v.calculateSingleTaskScore(task)
		if len(taskScores) > 0 {
			allTaskScores[task.ID] = taskScores
		}
	}

	return allTaskScores
}

func (v *Validator) calculateSingleTaskScore(task taskapi.VoteTaskData) map[string]float64 {
	isTrap, negativeGeneratorHotkey := v.checkIfTrapTask(task.ID)

	completionMaps := v.categorizeCompletions(task.Completions, isTrap, negativeGeneratorHotkey, task.ValidatorHotkey)

	discriminators := v.buildDiscriminatorsMap(task.Votes)
	if len(discriminators) == 0 {
		log.Info().Msgf("No discriminators found for task %s, skipping", task.ID)
		return nil
	}
	// TODO: should we validate the votes?
	return v.calculateScoresByType(task.ID, isTrap, discriminators, completionMaps)
}

func (v *Validator) checkIfTrapTask(taskID string) (bool, string) {
	trapRedisKey := fmt.Sprintf("trap:%s", taskID)

	negativeGeneratorHotkey, err := v.Redis.Get(v.Ctx, trapRedisKey)
	if err != nil {
		// TODO: how to handle this redis get key error better
		log.Error().Err(err).Msgf("failed to get trap for task %s", taskID)
		return false, ""
	}

	if negativeGeneratorHotkey != "" {
		log.Debug().Msgf("Task %s is a trap task (negative generator: %s)", taskID, negativeGeneratorHotkey)
		if delErr := v.Redis.Del(v.Ctx, trapRedisKey); delErr != nil {
			// TODO: how to handle this redis delete key error better
			log.Error().Err(delErr).Msgf("Failed to delete trap key %s", trapRedisKey)
		}
		return true, negativeGeneratorHotkey
	}

	return false, ""
}

func (v *Validator) categorizeCompletions(completions []taskapi.VoteCompletion, isTrap bool, negativeGeneratorHotkey, validatorHotkey string) CompletionMaps {
	maps := CompletionMaps{
		validator:          make(map[string]string),
		generators:         make(map[string]string),
		positiveGenerators: make(map[string]string),
		negativeGenerators: make(map[string]string),
	}

	for _, completion := range completions {
		if isTrap {
			if completion.ParticipantHotkey == negativeGeneratorHotkey {
				maps.negativeGenerators[completion.ParticipantHotkey] = completion.ID
			} else {
				maps.positiveGenerators[completion.ParticipantHotkey] = completion.ID
			}
		} else {
			if completion.ParticipantHotkey == validatorHotkey {
				maps.validator[completion.ParticipantHotkey] = completion.ID
			} else {
				maps.generators[completion.ParticipantHotkey] = completion.ID
			}
		}
	}

	return maps
}

func (v *Validator) buildDiscriminatorsMap(votes []taskapi.VoteData) map[string]string {
	discriminators := make(map[string]string)

	for _, vote := range votes {
		discriminators[vote.VoterHotkey] = vote.ChosenCompletionID
	}

	return discriminators
}

func (v *Validator) calculateScoresByType(taskID string, isTrap bool, discriminators map[string]string, completionMaps CompletionMaps) map[string]float64 {
	if isTrap {
		log.Debug().Msgf("Calculating trap score for task %s", taskID)
		return scoring.CalcTrapScores(discriminators, completionMaps.positiveGenerators, completionMaps.negativeGenerators)
	} else if len(completionMaps.validator) == 0 {
		log.Debug().Msgf("Calculating PvP score for task %s", taskID)
		return scoring.CalcPvPScores(discriminators, completionMaps.generators)
	} else {
		log.Debug().Msgf("Calculating PvV score for task %s", taskID)
		return scoring.CalcPvVScores(discriminators, completionMaps.generators, completionMaps.validator)
	}
}

func (v *Validator) saveTaskScoresToFile(allTaskScores map[string]map[string]float64, filename string) error {
	var existingScores map[string]map[string]float64
	existingData, err := os.ReadFile(filename)

	if err == nil {
		if parseErr := json.Unmarshal(existingData, &existingScores); parseErr != nil {
			log.Warn().Err(parseErr).Msg("Failed to parse existing scores file, will overwrite")
			existingScores = make(map[string]map[string]float64)
		} else {
			backupName := fmt.Sprintf("%s.backup", filename)
			if backupErr := os.WriteFile(backupName, existingData, 0644); backupErr != nil {
				log.Warn().Err(backupErr).Msg("Failed to create backup of existing scores file")
			} else {
				log.Info().Msgf("Created backup: %s", backupName)
			}
		}
	} else {
		existingScores = make(map[string]map[string]float64)
	}

	maps.Copy(existingScores, allTaskScores)

	jsonData, err := json.MarshalIndent(existingScores, "", "  ")
	if err != nil {
		return fmt.Errorf("failed to marshal task scores: %w", err)
	}

	if err := os.WriteFile(filename, jsonData, 0644); err != nil {
		return fmt.Errorf("failed to write scores to file: %w", err)
	}

	log.Info().Msgf("Successfully saved scores for %d tasks to %s", len(allTaskScores), filename)
	return nil
}
