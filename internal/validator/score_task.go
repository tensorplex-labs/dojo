package validator

import (
	"encoding/json"
	"fmt"
	"maps"
	"os"
	"strings"
	"time"

	"github.com/bytedance/sonic"
	"github.com/rs/zerolog/log"

	"github.com/tensorplex-labs/dojo/internal/scoring"
	"github.com/tensorplex-labs/dojo/internal/taskapi"
)

const scoreFileName = "all_task_scores.json"

// CompletionMaps maps hotkeys to their completion id
type CompletionMaps struct {
	validator          map[string]string
	generators         map[string]string
	positiveGenerators map[string]string
	negativeGenerators map[string]string
}

func (v *Validator) processTasksToScore(latestScoresData ScoresFileData) {
	if latestScoresData.Step >= v.IntervalConfig.WeightSettingStep {
		log.Info().Msg("Initializing scores")
		initializeScores(scoresFileName)

		scoresFile, err := os.ReadFile(scoresFileName)
		if err != nil {
			log.Error().Err(err).Msg("failed to read scores file")
			return
		}
		var latestScoresFileData ScoresFileData
		if err := sonic.Unmarshal(scoresFile, &latestScoresFileData); err != nil {
			log.Error().Err(err).Msg("failed to unmarshal scores from file")
			return
		}
		latestScoresData = latestScoresFileData
	}
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

	if !strings.EqualFold(v.ValidatorConfig.Environment, "prod") {
		if err = v.saveTaskScoresToFile(allTaskScores, scoreFileName); err != nil {
			log.Error().Err(err).Msg("failed to save task scores")
			return
		}
	}

	// TODO: Convert below into a proper testing setup
	// allTaskScores := make(map[string]map[string]float64)
	// allTaskScoresData, err := os.ReadFile("all_task_scores.json")
	// if err != nil {
	// 	log.Error().Err(err).Msg("failed to read all_task_scores.json")
	// 	return
	// }

	// if err := sonic.Unmarshal(allTaskScoresData, &allTaskScores); err != nil {
	// 	log.Error().Err(err).Msg("failed to unmarshal all_task_scores.json")
	// 	return
	// }
	// log.Info().Msg("Successfully loaded scores from all_task_scores.json")

	updatedScoresData := v.updateScores(allTaskScores, latestScoresData)

	updatedScoresJSON, err := sonic.Marshal(updatedScoresData)
	if err != nil {
		log.Error().Err(err).Msg("failed to marshal updated scores")
		return
	}

	if err := os.WriteFile(scoresFileName, updatedScoresJSON, 0o600); err != nil {
		log.Error().Err(err).Msg("failed to write scores.json")
		return
	}
	log.Info().Msg("Successfully saved updated scores to scores.json")

	v.LatestScoresData = updatedScoresData
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

	for i := range tasks {
		task := &tasks[i]
		taskScores := v.calculateSingleTaskScore(task)
		if len(taskScores) > 0 {
			allTaskScores[task.ID] = taskScores
			headers, err := v.setupAuthHeaders()
			if err != nil {
				log.Error().Err(err).Msg("failed to setup authentication")
				return nil
			}

			if _, err := v.TaskAPI.UpdateTaskStatus(headers, task.ID, "scored"); err != nil {
				log.Error().Err(err).Msgf("failed to update task status to scored for task %s", task.ID)
			}
		}
	}

	return allTaskScores
}

func (v *Validator) calculateSingleTaskScore(task *taskapi.VoteTaskData) map[string]float64 {
	isTrap, negativeGeneratorHotkey := v.checkIfTrapTask(task.ID)

	completionMaps := v.categorizeCompletions(task.Completions, isTrap, negativeGeneratorHotkey, task.ValidatorHotkey)

	discriminators := v.buildDiscriminatorsMap(task.Votes)
	if len(discriminators) == 0 {
		log.Info().Msgf("No discriminators found for task %s, skipping", task.ID)
		return nil
	}

	return v.calculateScoresByType(task.ID, isTrap, discriminators, completionMaps)
}

func (v *Validator) checkIfTrapTask(taskID string) (trapBool bool, hotkey string) {
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

func (v *Validator) categorizeCompletions(
	completions []taskapi.VoteCompletion,
	isTrap bool,
	negativeGeneratorHotkey,
	validatorHotkey string,
) CompletionMaps {
	completionMaps := CompletionMaps{
		validator:          make(map[string]string),
		generators:         make(map[string]string),
		positiveGenerators: make(map[string]string),
		negativeGenerators: make(map[string]string),
	}

	for _, completion := range completions {
		if isTrap {
			if completion.ParticipantHotkey == negativeGeneratorHotkey {
				completionMaps.negativeGenerators[completion.ParticipantHotkey] = completion.ID
			} else {
				completionMaps.positiveGenerators[completion.ParticipantHotkey] = completion.ID
			}
		} else {
			if completion.ParticipantHotkey == validatorHotkey {
				completionMaps.validator[completion.ParticipantHotkey] = completion.ID
			} else {
				completionMaps.generators[completion.ParticipantHotkey] = completion.ID
			}
		}
	}

	return completionMaps
}

func (v *Validator) buildDiscriminatorsMap(votes []taskapi.VoteData) map[string]string {
	discriminators := make(map[string]string)

	for _, vote := range votes {
		discriminators[vote.VoterHotkey] = vote.ChosenCompletionID
	}

	return discriminators
}

func (v *Validator) calculateScoresByType(
	taskID string,
	isTrap bool,
	discriminators map[string]string,
	completionMaps CompletionMaps,
) map[string]float64 {
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
	existingData, err := os.ReadFile(filename) // #nosec G304
	if err == nil {
		if parseErr := json.Unmarshal(existingData, &existingScores); parseErr != nil {
			log.Warn().Err(parseErr).Msg("Failed to parse existing scores file, will overwrite")
			existingScores = make(map[string]map[string]float64)
		} else {
			backupName := fmt.Sprintf("%s.backup", filename)
			if backupErr := os.WriteFile(backupName, existingData, 0o600); backupErr != nil {
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

	if err := os.WriteFile(filename, jsonData, 0o600); err != nil {
		return fmt.Errorf("failed to write scores to file: %w", err)
	}

	log.Info().Msgf("Successfully saved scores for %d tasks to %s", len(allTaskScores), filename)
	return nil
}

func (v *Validator) updateScores(allTaskScores map[string]map[string]float64, latestScoresData ScoresFileData) (updatedScoresData ScoresFileData) {
	currentHotkeyToUID := make(map[string]int)
	for uid, hotkey := range v.MetagraphData.Metagraph.Hotkeys {
		currentHotkeyToUID[hotkey] = uid
	}

	updatedScoresData = latestScoresData

	maxLen := max(len(v.MetagraphData.Metagraph.Hotkeys), len(latestScoresData.Hotkeys))

	for i := range maxLen {
		if i < len(v.MetagraphData.Metagraph.Hotkeys) {
			currentHotkey := v.MetagraphData.Metagraph.Hotkeys[i]

			if i < len(latestScoresData.Hotkeys) {
				if latestScoresData.Hotkeys[i] != currentHotkey {
					log.Debug().Msgf("UID %d: hotkey changed from %s to %s, resetting score %.2f to 0",
						i, latestScoresData.Hotkeys[i], currentHotkey, updatedScoresData.Scores[i])
					updatedScoresData.Hotkeys[i] = currentHotkey
					updatedScoresData.Scores[i] = 0
				}
			} else {
				log.Info().Msgf("New UID %d with hotkey %s", i, currentHotkey)
				updatedScoresData.Hotkeys = append(updatedScoresData.Hotkeys, currentHotkey)
				updatedScoresData.Scores = append(updatedScoresData.Scores, 0)
			}
		} else {
			updatedScoresData.Hotkeys[i] = ""
			updatedScoresData.Scores[i] = 0
		}
	}

	for taskID, taskScores := range allTaskScores {
		for hotkey, score := range taskScores {
			if uid, exists := currentHotkeyToUID[hotkey]; exists {
				updatedScoresData.Scores[uid] += score
			} else {
				log.Warn().Str("hotkey", hotkey).Str("taskID", taskID).Msg("hotkey not found in metagraph")
			}
		}
	}

	updatedScoresData.Step += 1

	return updatedScoresData
}
