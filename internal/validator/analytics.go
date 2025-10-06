package validator

import (
	"slices"
	"time"

	"github.com/bytedance/sonic"
	"github.com/rs/zerolog/log"

	"github.com/tensorplex-labs/dojo/internal/scoring"
	"github.com/tensorplex-labs/dojo/internal/taskapi"
	chainutils "github.com/tensorplex-labs/dojo/internal/utils/chain_utils"
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

	// TODO: push to task api

	log.Info().RawJSON("analytics", analyticsJSON).Msg("Task Analytics")
}

func (v *Validator) pushTaskAnalyticsToTaskAPI(analytics *ScoredTaskAnalyticsRecord) error {
	headers, err := v.setupAuthHeaders()
	if err != nil {
		log.Error().Err(err).Msg("Failed to sign message")
		return err
	}
	_, err = v.TaskAPI.PostTaskScoresAnalytics(headers, analytics)
	if err != nil {
		log.Error().Err(err).Msg("Failed to push task analytics to task API")
		return err
	}
	return nil
}
