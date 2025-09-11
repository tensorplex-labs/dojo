package validator

import (
	"fmt"
	"slices"
	"time"

	"github.com/rs/zerolog/log"
	"github.com/tensorplex-labs/dojo/internal/syntheticapi"
	"github.com/tensorplex-labs/dojo/internal/taskapi"
)

const (
	taskType                = "codeGen"
	augmentedProbability    = int64(25)
	validatorDuelProbablity = int64(60)
	expireAt                = 6 * time.Hour
)

func (v *Validator) processCodegenTask(activeMinerUIDs []int64, processedMiners *ProcessedMiners) {
	for len(processedMiners.uids) < len(activeMinerUIDs) {
		validatorDuel := v.shouldDuelValidator(validatorDuelProbablity)
		var selectedMinerUIDs []int64
		if validatorDuel {
			selectedMinerUIDs = v.pickRandomMiners(activeMinerUIDs, 1, processedMiners)
		} else {
			selectedMinerUIDs = v.pickRandomMiners(activeMinerUIDs, 2, processedMiners)
		}

		synAPIQuestion, err := v.SyntheticAPI.GetQuestion()
		if err != nil {
			log.Error().Err(err).Msg("failed to get question from synthetic API")
			return
		}
		log.Debug().Msgf("Received question: %s of id: %s", synAPIQuestion.Prompt, synAPIQuestion.QaID)
		log.Info().Msgf("Processing question with ID %s for duel %+v", synAPIQuestion.QaID, selectedMinerUIDs)

		completion, err := v.SyntheticAPI.GetCodegenAnswer(synAPIQuestion.QaID)
		if err != nil {
			log.Error().Err(err).Msgf("failed to get answer for question ID %s", synAPIQuestion.QaID)
			return
		}
		if !hasValidatorContent(completion) {
			log.Error().Msgf("empty completion for question ID %s", synAPIQuestion.QaID)
			return
		}

		validatorContent := completion.Answer.Responses[0].Completion.Files[0].Content

		var payload taskapi.CreateTasksRequest[taskapi.CodegenTaskMetadata]
		payload.TaskType = taskType
		payload.ExpireAt = time.Now().Add(expireAt).Format(time.RFC3339)
		payload.Metadata = taskapi.CodegenTaskMetadata{Prompt: completion.Answer.Prompt}

		taskAugmented, selectedAugmentedMiner, augmentedPrompt, validatorContent := v.maybeAugment(validatorDuel, synAPIQuestion, selectedMinerUIDs, validatorContent)

		assignees := v.buildAssignees(synAPIQuestion.Prompt, selectedMinerUIDs, validatorDuel, taskAugmented, selectedAugmentedMiner, augmentedPrompt)
		payload.Assignees = assignees

		headers, err := v.setupAuthHeaders()
		if err != nil {
			log.Error().Err(err).Msg("failed to sign message")
			return
		}

		var taskCreationResponse taskapi.Response[taskapi.CreateTaskResponse]
		if validatorDuel {
			taskCreationResponse, err = v.TaskAPI.CreateCodegenTask(headers, payload, validatorContent)
			if err != nil {
				log.Error().Err(err).Msgf("failed to create task for question with ID %s for %+v ", synAPIQuestion.QaID, selectedMinerUIDs)
				return
			}
		} else {
			taskCreationResponse, err = v.TaskAPI.CreateCodegenTask(headers, payload, "")
			if err != nil {
				log.Error().Err(err).Msgf("failed to create task for question with ID %s for %+v ", synAPIQuestion.QaID, selectedMinerUIDs)
				return
			}
		}

		if taskAugmented && validatorDuel {
			if err = v.Redis.Set(v.Ctx, fmt.Sprintf("trap:%s", taskCreationResponse.Data.TaskID), v.ValidatorHotkey, 0); err != nil {
				log.Error().Err(err).Msgf("failed to set trap for task ID %s", taskCreationResponse.Data.TaskID)
			} else {
				log.Debug().Msgf("Set trap for task ID %s", taskCreationResponse.Data.TaskID)
			}
		} else {
			if err = v.Redis.Set(v.Ctx, fmt.Sprintf("trap:%s", taskCreationResponse.Data.TaskID), v.MetagraphData.Metagraph.Hotkeys[selectedAugmentedMiner], 0); err != nil {
				log.Error().Err(err).Msgf("failed to set trap for task ID %s", taskCreationResponse.Data.TaskID)
			} else {
				log.Debug().Msgf("Set trap for task ID %s", taskCreationResponse.Data.TaskID)
			}
		}

		if validatorDuel {
			log.Info().Msgf("Created task for %d and validator\n", selectedMinerUIDs[0])
		} else {
			log.Info().Msgf("Created task for %+v\n", selectedMinerUIDs)
		}
	}
}

func hasValidatorContent(completion syntheticapi.GenerateAnswerResponse[syntheticapi.CodegenAnswer]) bool {
	if len(completion.Answer.Responses) == 0 {
		return false
	}
	if len(completion.Answer.Responses[0].Completion.Files) == 0 {
		return false
	}
	return completion.Answer.Responses[0].Completion.Files[0].Content != ""
}

func (v *Validator) maybeAugment(
	validatorDuel bool,
	syn syntheticapi.GenerateQuestionResponse,
	selectedMinerUIDs []int64,
	initialContent string,
) (bool, int64, string, string) {
	taskAugmented := false
	var selectedAugmentedMiner int64
	augmentedPrompt := ""
	validatorContent := initialContent

	if v.shouldAugment(augmentedProbability) && validatorDuel {
		augmentedCompletion, err := v.SyntheticAPI.GetCodegenAnswer(syn.AnsAugID)
		if err != nil {
			log.Error().Err(err).Msgf("failed to get augmented answer for question ID %s", syn.QaID)
		} else {
			if len(augmentedCompletion.Answer.Responses) > 0 || len(augmentedCompletion.Answer.Responses[0].Completion.Files) > 0 {
				log.Info().Msgf("Using augmented answer for question ID %s", syn.QaID)
				validatorContent = augmentedCompletion.Answer.Responses[0].Completion.Files[0].Content
			}
			taskAugmented = true
		}
	} else if !validatorDuel && v.shouldAugment(augmentedProbability) {
		selectedAugmentedMiner = selectedMinerUIDs[time.Now().UnixNano()%int64(len(selectedMinerUIDs))]
		augmentedCompletion, err := v.SyntheticAPI.GetCodegenAnswer(syn.AnsAugID)
		if err != nil {
			log.Error().Err(err).Msgf("failed to get augmented question for question ID %s", syn.QaID)
		} else {
			augmentedPrompt = augmentedCompletion.Answer.Prompt
		}
	} else {
		log.Info().Msgf("Not using augmented answer for question ID %s", syn.QaID)
	}

	return taskAugmented, selectedAugmentedMiner, augmentedPrompt, validatorContent
}

func (v *Validator) buildAssignees(
	basePrompt string,
	selectedMinerUIDs []int64,
	validatorDuel bool,
	taskAugmented bool,
	selectedAugmentedMiner int64,
	augmentedPrompt string,
) []taskapi.AssigneeData {
	var assignees []taskapi.AssigneeData
	if validatorDuel {
		for _, uid := range selectedMinerUIDs {
			assignees = append(assignees, taskapi.AssigneeData{
				Hotkey: v.MetagraphData.Metagraph.Hotkeys[uid],
				Prompt: basePrompt,
			})
		}
		return assignees
	}
	for _, uid := range selectedMinerUIDs {
		p := basePrompt
		if taskAugmented && uid == selectedAugmentedMiner && len(augmentedPrompt) > 0 {
			p = augmentedPrompt
		}
		assignees = append(assignees, taskapi.AssigneeData{
			Hotkey: v.MetagraphData.Metagraph.Hotkeys[uid],
			Prompt: p,
		})
	}
	return assignees
}

func (v *Validator) pickRandomMiners(activeMinerUIDs []int64, count int, processedMiners *ProcessedMiners) []int64 {
	processedMiners.Lock()
	defer processedMiners.Unlock()

	var availableMiners []int64
	for _, uid := range activeMinerUIDs {
		if !slices.Contains(processedMiners.uids, uid) {
			availableMiners = append(availableMiners, uid)
		}
	}

	if len(availableMiners) == 0 {
		log.Warn().Msg("No available miners to pick from")
		return nil
	}

	if len(availableMiners) < count {
		count = len(availableMiners)
	}

	selectedMiners := make([]int64, 0, count)
	for i := 0; i < count; i++ {
		index := time.Now().UnixNano() % int64(len(availableMiners))
		selectedMiners = append(selectedMiners, availableMiners[index])
		processedMiners.uids = append(processedMiners.uids, availableMiners[index])
		availableMiners = append(availableMiners[:index], availableMiners[index+1:]...)
		if len(availableMiners) == 0 {
			break
		}
	}

	return selectedMiners
}
