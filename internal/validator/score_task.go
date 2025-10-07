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

func (v *Validator) processTasksToScore(latestScoresData ScoresData) {
	startTime := time.Now()

	tasks, err := v.fetchTasksToScoreRollingWindow()
	if err != nil {
		log.Error().Err(err).Msg("failed to fetch tasks for scoring")
		return
	}

	if len(tasks) == 0 {
		log.Warn().Msg("No tasks to score")
		return
	}

	allTaskScores := make(map[string]map[string]float64)

	analyticsBatch := make([]*ScoredTaskAnalyticsRecord, 0, len(tasks))

	for i := range tasks {
		task := &tasks[i]
		isTrap, negativeGeneratorHotkey, checkTrapErr := v.checkIfTrapTask(task.ID)
		if checkTrapErr != nil {
			log.Warn().Err(checkTrapErr).Str("taskID", task.ID).Msg("failed to check if task is a trap, skipping")
			continue
		}
		voters, votersRetrievalErr := v.retrieveVoters(task.ID)
		if votersRetrievalErr != nil {
			log.Warn().Err(votersRetrievalErr).Str("taskID", task.ID).Msg("failed to retrieve voters for task, skipping")
			continue
		}

		taskScores := scoring.CalculateTaskScores(
			&scoring.TaskScoringInput{
				TaskID:                     task.ID,
				Completions:                task.Completions,
				Votes:                      task.Votes,
				IsTrap:                     isTrap,
				NegativeGeneratorHotkey:    negativeGeneratorHotkey,
				ValidatorHotkey:            task.ValidatorHotkey,
				Voters:                     voters,
				CurrentActiveMinersHotkeys: v.MetagraphData.Metagraph.Hotkeys,
			},
		)

		if len(taskScores) > 0 {
			allTaskScores[task.ID] = taskScores
			analytics := v.buildTaskAnalytics(task, taskScores, isTrap, negativeGeneratorHotkey, voters)
			v.pushLogAnalytics(&analytics)
			analyticsBatch = append(analyticsBatch, &analytics)
		}
	}

	if len(analyticsBatch) > 0 {
		if pushTaskAnalyticsErr := v.pushTaskAnalyticsToTaskAPIBatch(analyticsBatch); pushTaskAnalyticsErr != nil {
			log.Error().Err(pushTaskAnalyticsErr).Msgf("Failed to push %d task analytics to task API", len(analyticsBatch))
		}
	}

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

	scores := scoring.AggregateTaskScoresByUID(allTaskScores, v.MetagraphData.Metagraph.Hotkeys)

	updatedScoresData := ScoresData{
		Scores:  scores,
		Step:    latestScoresData.Step + 1,
		Hotkeys: v.MetagraphData.Metagraph.Hotkeys,
	}

	for uid, score := range updatedScoresData.Scores {
		log.Info().Int("uid", uid).Float64("score", score).Str("hotkey", updatedScoresData.Hotkeys[uid]).Msgf("uid %d with hotkey %s | coldkey %s scored %f", uid, updatedScoresData.Hotkeys[uid], v.MetagraphData.Metagraph.Coldkeys[uid], score)
	}

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

func (v *Validator) fetchTasksToScoreRollingWindow() ([]taskapi.VoteTaskData, error) {
	headers, err := v.setupAuthHeaders()
	if err != nil {
		return nil, fmt.Errorf("failed to setup authentication: %w", err)
	}

	hours := int(v.IntervalConfig.ScoreResetInterval / time.Hour)

	tasksToScore, err := v.TaskAPI.GetExpiredTasksRollingWindow(headers, hours)
	if err != nil {
		return nil, fmt.Errorf("failed to get expired tasks for a rolling window of %d hours: %w", hours, err)
	}

	log.Info().Msgf("Found %d task(s) in a rolling window of %d hours to score", tasksToScore.Data.Total, hours)
	return tasksToScore.Data.Tasks, nil
}

func (v *Validator) checkIfTrapTask(taskID string) (trapBool bool, hotkey string, err error) {
	negativeGeneratorHotkey, err := v.Redis.Get(v.Ctx, fmt.Sprintf("%s:%s", redisTrapKey, taskID))
	if err != nil {
		return false, "", fmt.Errorf("failed to get trap for task %s: %w", taskID, err)
	}

	if negativeGeneratorHotkey != "" {
		log.Debug().Msgf("Task %s is a trap task (negative generator: %s)", taskID, negativeGeneratorHotkey)
		return true, negativeGeneratorHotkey, nil
	}

	return false, "", nil
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

func (v *Validator) retrieveVoters(taskID string) (voters []string, err error) {
	votersJSONString, err := v.Redis.Get(v.Ctx, fmt.Sprintf("%s:%s", redisVotersKey, taskID))
	if err != nil {
		return nil, fmt.Errorf("failed to get voters for task %s: %w", taskID, err)
	}

	if votersJSONString == "" {
		log.Warn().Str("taskID", taskID).Msg("voters key for task exists but has empty value")
		return []string{}, nil
	}

	if err := sonic.Unmarshal([]byte(votersJSONString), &voters); err != nil {
		return nil, fmt.Errorf("failed to unmarshal voters for task %s: %w", taskID, err)
	}

	return voters, nil
}
