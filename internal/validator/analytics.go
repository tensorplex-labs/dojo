package validator

import (
	"fmt"
	"slices"
	"time"

	"github.com/bytedance/sonic"
	"github.com/rs/zerolog/log"

	"github.com/tensorplex-labs/dojo/internal/scoring"
	"github.com/tensorplex-labs/dojo/internal/taskapi"
	chainutils "github.com/tensorplex-labs/dojo/internal/utils/chain_utils"
)

const (
	scoreAnalyticsUploadCacheKey string        = "score_analytics_upload"
	scoreAnalyticsUploadCacheTTL time.Duration = 24 * time.Hour

	scoreAnalyticsUploadCacheStatusCreated   string = "created"
	scoreAnalyticsUploadCacheStatusDuplicate string = "duplicate"
	scoreAnalyticsUploadCacheStatusError     string = "error"
)

type ScoresRecord = taskapi.ScoresRecord

type VotesRecord = taskapi.VotesRecord

type ScoredTaskAnalyticsRecord = taskapi.ScoredTaskAnalyticsRecord

func (v *Validator) buildTaskAnalytics(
	task *taskapi.VoteTaskData,
	taskScores map[string]float64,
	isTrap bool,
	negativeGeneratorHotkey string,
	voters []string,
) ScoredTaskAnalyticsRecord {
	completionMaps := scoring.CategorizeCompletions(
		task.Completions, isTrap, negativeGeneratorHotkey, task.ValidatorHotkey,
	)
	taskType := scoring.DetermineTaskType(completionMaps, isTrap)

	scoresRecord := v.buildScoresRecord(task, taskScores, completionMaps, voters)

	votesRecord := v.buildVotesRecord(task, completionMaps, voters)

	return ScoredTaskAnalyticsRecord{
		TaskID:    task.ID,
		TaskType:  taskType,
		CreatedAt: time.Now(),
		AnalyticsMetadata: map[string]any{
			"created_at": time.Now(),
		},
		ValidatorHotkey: task.ValidatorHotkey,
		ScoresRecord:    scoresRecord,
		VotesRecord:     votesRecord,
	}
}

func (v *Validator) buildScoresRecord(
	task *taskapi.VoteTaskData,
	taskScores map[string]float64,
	completionMaps scoring.CompletionMaps,
	voters []string,
) []ScoresRecord {
	records := make([]ScoresRecord, 0, len(taskScores))

	for hotkey, score := range taskScores {
		role := v.determineRole(hotkey, task.ValidatorHotkey, completionMaps, voters, task)
		coldkey := chainutils.GetColdkeyForHotkey(&v.MetagraphData.Metagraph, hotkey)

		records = append(records, ScoresRecord{
			Hotkey:  hotkey,
			Coldkey: coldkey,
			Score:   score,
			Role:    role,
		})
	}

	return records
}

func (v *Validator) buildVotesRecord(
	task *taskapi.VoteTaskData,
	completionMaps scoring.CompletionMaps,
	voters []string,
) []VotesRecord {
	records := make([]VotesRecord, 0, len(task.Votes))

	completionToParticipant := make(map[string]string)
	for _, completion := range task.Completions {
		completionToParticipant[completion.ID] = completion.ParticipantHotkey
	}

	for _, vote := range task.Votes {
		voteeHotkey := completionToParticipant[vote.ChosenCompletionID]
		voteeRole := v.determineRole(voteeHotkey, task.ValidatorHotkey, completionMaps, voters, task)

		records = append(records, VotesRecord{
			VoterHotkey:        vote.VoterHotkey,
			VoterColdkey:       chainutils.GetColdkeyForHotkey(&v.MetagraphData.Metagraph, vote.VoterHotkey),
			ChosenCompletionID: vote.ChosenCompletionID,
			VoteWeight:         vote.Weight,
			VoteeHotkey:        voteeHotkey,
			VoteeColdkey:       chainutils.GetColdkeyForHotkey(&v.MetagraphData.Metagraph, voteeHotkey),
			VoteeRole:          voteeRole,
		})
	}

	return records
}

func (v *Validator) determineRole(
	hotkey string,
	taskValidatorHotkey string,
	completionMaps scoring.CompletionMaps,
	voters []string,
	task *taskapi.VoteTaskData,
) string {
	if _, exists := completionMaps.Generators[hotkey]; exists {
		return "Generator"
	}
	if _, exists := completionMaps.Validator[hotkey]; exists {
		return "Validator"
	}
	if _, exists := completionMaps.PositiveGenerators[hotkey]; exists {
		if hotkey == taskValidatorHotkey {
			return "PositiveValidator"
		}
		return "PositiveGenerator"
	}
	if _, exists := completionMaps.NegativeGenerators[hotkey]; exists {
		if hotkey == taskValidatorHotkey {
			return "NegativeValidator"
		}
		return "NegativeGenerator"
	}

	if slices.Contains(voters, hotkey) {
		for _, vote := range task.Votes {
			if vote.VoterHotkey == hotkey {
				return "Discriminator"
			}
		}
		return "DiscriminatorNoVote"
	}
	return "Discriminator"
}

func (v *Validator) pushLogAnalytics(analytics *ScoredTaskAnalyticsRecord) {
	analyticsJSON, err := sonic.Marshal(analytics)
	if err != nil {
		log.Warn().Err(err).Str("taskID", analytics.TaskID).Msg("failed to marshal task analytics")
		return
	}

	log.Debug().RawJSON("analytics", analyticsJSON).Msg("Task Analytics")
}

func (v *Validator) pushTaskAnalyticsToTaskAPIBatch(analyticsBatch []*ScoredTaskAnalyticsRecord) error {
	headers, setupAuthHeadersErr := v.setupAuthHeaders()
	if setupAuthHeadersErr != nil {
		log.Error().Err(setupAuthHeadersErr).Msg("Failed to sign message")
		return setupAuthHeadersErr
	}

	analyticsUploadBatch := make([]*taskapi.ScoredTaskAnalyticsRecord, 0, len(analyticsBatch))
	for _, analytics := range analyticsBatch {
		exists, err := v.Redis.Get(v.Ctx, fmt.Sprintf("%s:%s", scoreAnalyticsUploadCacheKey, analytics.TaskID))
		if err != nil {
			log.Warn().Err(err).Str("taskID", analytics.TaskID).Msg("Failed to check cache, including in upload")
		}
		if exists != "" {
			log.Info().Str("taskID", analytics.TaskID).Msg("Task analytics already uploaded")
			continue
		}
		analyticsUploadBatch = append(analyticsUploadBatch, analytics)
	}

	if len(analyticsUploadBatch) == 0 {
		log.Info().Msg("No task analytics to upload")
		return nil
	}

	postTaskScoresAnalyticsUploadResponse, err := v.TaskAPI.PostTaskScoresAnalyticsBatch(headers, taskapi.ScoredTaskAnalyticsBatchRequest{
		Analytics: analyticsUploadBatch,
	})
	if err != nil {
		log.Error().Err(err).Msg("Failed to push task analytics to task API batch")
		return err
	}

	var successfulUploads int
	var failedUploads []string

	if postTaskScoresAnalyticsUploadResponse.Success {
		for _, result := range postTaskScoresAnalyticsUploadResponse.Data.Results {
			switch result.Status {
			case scoreAnalyticsUploadCacheStatusCreated:
				if err := v.Redis.Set(v.Ctx, fmt.Sprintf("%s:%s", scoreAnalyticsUploadCacheKey, result.TaskID), result.Status, scoreAnalyticsUploadCacheTTL); err != nil {
					log.Error().Err(err).Msg("Failed to set score analytics upload cache")
					return err
				}
				successfulUploads++
				log.Info().Msgf("Successful upload, caching for task ID %s", result.TaskID)
			case scoreAnalyticsUploadCacheStatusDuplicate:
				log.Info().Str("taskID", result.TaskID).Str("status", result.Status).Str("message", result.Message)
			case scoreAnalyticsUploadCacheStatusError:
				failedUploads = append(failedUploads, result.TaskID)
				log.Error().Str("taskID", result.TaskID).Str("status", result.Status).Str("message", result.Message).Msg("Failed to push task analytics to task API")
			}
		}
		log.Info().Msgf("Successfully pushed %d task analytics to task API", successfulUploads)
		log.Warn().Strs("taskIDs", failedUploads).Msg("Failed to push task analytics to task API")
	}

	return nil
}
