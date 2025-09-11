package validator

import (
	"fmt"
	"math/rand"
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
	if len(processedMiners.uids) >= len(activeMinerUIDs) {
		log.Info().Msg("All miners have been processed")
		return
	}

	shouldDuelValidator := v.rollProbability(validatorDuelProbablity)
	count := 2
	if shouldDuelValidator {
		count = 1
	}
	selectedMinerUIDs := v.pickRandomMiners(activeMinerUIDs, count, processedMiners)

	synAPIQuestion, err := v.SyntheticAPI.GetQuestion()
	if err != nil {
		log.Error().Err(err).Msg("failed to get question from synthetic API")
		return
	}
	log.Debug().Msgf("Received question: %s of id: %s", synAPIQuestion.Prompt, synAPIQuestion.QaID)
	log.Debug().Msgf("Processing question with ID %s for duel %+v", synAPIQuestion.QaID, selectedMinerUIDs)

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
	payload := taskapi.CreateTasksRequest[taskapi.CodegenTaskMetadata]{
		TaskType: taskType,
		ExpireAt: time.Now().Add(expireAt).Format(time.RFC3339),
		Metadata: taskapi.CodegenTaskMetadata{Prompt: completion.Answer.Prompt},
	}

	taskAugmented, selectedAugmentedMiner, augmentedPrompt, validatorContent := v.maybeAugment(shouldDuelValidator, synAPIQuestion, selectedMinerUIDs, validatorContent)

	payload.Assignees = v.buildAssignees(synAPIQuestion.Prompt, selectedMinerUIDs, shouldDuelValidator, taskAugmented, selectedAugmentedMiner, augmentedPrompt)

	headers, err := v.setupAuthHeaders()
	if err != nil {
		log.Error().Err(err).Msg("failed to sign message")
		return
	}

	content := ""
	if shouldDuelValidator {
		content = validatorContent
	}

	taskCreationResponse, err := v.TaskAPI.CreateCodegenTask(headers, payload, content)
	if err != nil {
		log.Error().Err(err).Msgf("failed to create task for question with ID %s for %+v ", synAPIQuestion.QaID, selectedMinerUIDs)
		return
	}

	if taskAugmented {
		trapValue := v.ValidatorHotkey
		if !shouldDuelValidator {
			trapValue = v.MetagraphData.Metagraph.Hotkeys[selectedAugmentedMiner]
		}

		if err = v.Redis.Set(v.Ctx, fmt.Sprintf("trap:%s", taskCreationResponse.Data.TaskID), trapValue, 0); err != nil {
			log.Error().Err(err).Msgf("failed to set trap for task ID %s", taskCreationResponse.Data.TaskID)
		} else {
			log.Debug().Msgf("Set trap for task ID %s", taskCreationResponse.Data.TaskID)
		}
	}

	if shouldDuelValidator {
		log.Debug().Msgf("Created task for %d and validator\n", selectedMinerUIDs[0])
	} else {
		log.Debug().Msgf("Created task for %+v\n", selectedMinerUIDs)
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
	shouldDuelValidator bool,
	syn syntheticapi.GenerateQuestionResponse,
	selectedMinerUIDs []int64,
	initialContent string,
) (bool, int64, string, string) {
	taskAugmented := false
	var selectedAugmentedMiner int64
	augmentedPrompt := ""
	validatorContent := initialContent

	if !v.shouldAugment(augmentedProbability) {
		log.Debug().Msgf("Not using augmented answer for question ID %s", syn.QaID)
		return taskAugmented, selectedAugmentedMiner, augmentedPrompt, validatorContent
	}

	augmentedCompletion, err := v.SyntheticAPI.GetCodegenAnswer(syn.AnsAugID)
	if err != nil {
		log.Error().Err(err).Msgf("failed to get augmented answer for question ID %s", syn.QaID)
	}

	if shouldDuelValidator {
		if len(augmentedCompletion.Answer.Responses) > 0 || len(augmentedCompletion.Answer.Responses[0].Completion.Files) > 0 {
			log.Debug().Msgf("Using augmented answer for question ID %s", syn.QaID)
			validatorContent = augmentedCompletion.Answer.Responses[0].Completion.Files[0].Content
		}
		taskAugmented = true
	} else {
		selectedAugmentedMiner = selectedMinerUIDs[rand.Intn(len(selectedMinerUIDs))]
		augmentedPrompt = augmentedCompletion.Answer.Prompt
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
	for _, uid := range selectedMinerUIDs {
		prompt := basePrompt
		if !validatorDuel && taskAugmented && uid == selectedAugmentedMiner && len(augmentedPrompt) > 0 {
			prompt = augmentedPrompt
		}
		assignees = append(assignees, taskapi.AssigneeData{
			Hotkey: v.MetagraphData.Metagraph.Hotkeys[uid],
			Prompt: prompt,
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
	for range count {
		index := rand.Intn(len(availableMiners))
		selectedMiners = append(selectedMiners, availableMiners[index])
		processedMiners.uids = append(processedMiners.uids, availableMiners[index])
		availableMiners = slices.Delete(availableMiners, int(index), int(index)+1)
		if len(availableMiners) == 0 {
			break
		}
	}

	return selectedMiners
}
