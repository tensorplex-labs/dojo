package validator

import (
	"crypto/rand"
	"fmt"
	"math/big"
	"slices"
	"time"

	"github.com/bytedance/sonic"
	"github.com/rs/zerolog/log"

	"github.com/tensorplex-labs/dojo/internal/syntheticapi"
	"github.com/tensorplex-labs/dojo/internal/taskapi"
)

const (
	taskType                = "codeGen"
	augmentedProbability    = int64(25) // 25% chance for traps!
	validatorDuelProbablity = int64(20) // 60% chance to duel validator
)

func (v *Validator) processCodegenTask(activeMinerUIDs []int64, processedMiners *ProcessedMiners) {
	for len(processedMiners.uids) < len(activeMinerUIDs) {
		shouldDuelValidator := v.rollProbability(validatorDuelProbablity)
		count := 2
		if shouldDuelValidator {
			count = 1
		}
		selectedMinerUIDs := v.pickRandomMiners(activeMinerUIDs, count, processedMiners)

		log.Debug().Msgf("Selected miners for codegen task: %+v", selectedMinerUIDs)

		synAPIQuestion, err := v.SyntheticAPI.GetQuestion()
		if err != nil {
			log.Error().Err(err).Msg("failed to get question from synthetic API")
			return
		}

		log.Debug().Msgf("Received question: %s of id: %s", synAPIQuestion.Prompt, synAPIQuestion.QaID)
		log.Debug().Msgf("Processing question with ID %s for duel %+v", synAPIQuestion.QaID, selectedMinerUIDs)

		completionRaw, err := v.Redis.Get(v.Ctx, fmt.Sprintf("synthetic:answers:%s", synAPIQuestion.QaID))
		if err != nil {
			log.Error().Err(err).Msgf("failed to get answer content from redis for question ID %s", synAPIQuestion.QaID)
			return
		}

		var completion syntheticapi.CodegenAnswer
		if err = sonic.Unmarshal([]byte(completionRaw), &completion); err != nil {
			log.Error().Err(err).Msgf("failed to unmarshal answer content from redis for %s", synAPIQuestion.QaID)
		}
		validatorContent := completion.Responses[0].Completion.Files[0].Content

		taskAugmented,
			selectedAugmentedMiner,
			augmentedPrompt,
			validatorContent,
			trapValue := v.maybeAugment(shouldDuelValidator, synAPIQuestion, selectedMinerUIDs, validatorContent)

		payload := taskapi.CreateTasksRequest[taskapi.CodegenTaskMetadata]{
			TaskType:  taskType,
			ExpireAt:  time.Now().Add(v.IntervalConfig.TaskExpiryDuration).Format(time.RFC3339),
			Assignees: v.buildAssignees(synAPIQuestion.Prompt, selectedMinerUIDs, shouldDuelValidator, taskAugmented, selectedAugmentedMiner, augmentedPrompt),
			Metadata: taskapi.CodegenTaskMetadata{
				Prompt:                  synAPIQuestion.Prompt,
				ValidatorDuel:           shouldDuelValidator,
				NegativeGeneratorHotkey: trapValue,
			},
		}

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

		if trapValue != "" {
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

		ok, err := v.SyntheticAPI.PopQA(synAPIQuestion.QaID)
		if err != nil {
			log.Error().Err(err).Msgf("failed to pop question with ID %s", synAPIQuestion.QaID)
		}

		if !ok {
			log.Error().Msgf("failed to pop question with ID %s", synAPIQuestion.QaID)
		}

		log.Info().Msgf("Processed miners so far: %d/%d\n", len(processedMiners.uids), len(activeMinerUIDs))
	}
}

func cryptoIntn(n int) int {
	if n <= 0 {
		return 0
	}
	maxBig := big.NewInt(int64(n))
	r, err := rand.Int(rand.Reader, maxBig)
	if err != nil {
		log.Error().Err(err).Msg("failed to generate crypto random int, defaulting to 0")
		return 0
	}
	return int(r.Int64())
}

func (v *Validator) maybeAugment(
	shouldDuelValidator bool,
	syn syntheticapi.GenerateQuestionResponse,
	selectedMinerUIDs []int64,
	initialContent string,
) (
	taskAugmented bool,
	selectedAugmentedMiner int64,
	augmentedPrompt string,
	validatorContent string,
	trapValue string,
) {
	taskAugmented = false
	augmentedPrompt = ""
	validatorContent = initialContent
	trapValue = ""

	if !v.shouldAugment(augmentedProbability) {
		log.Debug().Msgf("Not using augmented answer for question ID %s", syn.QaID)
		return taskAugmented, selectedAugmentedMiner, augmentedPrompt, validatorContent, trapValue
	}

	augmentedCompletionRaw, err := v.Redis.Get(v.Ctx, fmt.Sprintf("synthetic:answers:%s", syn.AnsAugID))
	if err != nil {
		log.Error().Err(err).Msgf("failed to get augmented answer for question ID %s", syn.QaID)
	}

	var augmentedCompletion syntheticapi.CodegenAnswer
	if err = sonic.Unmarshal([]byte(augmentedCompletionRaw), &augmentedCompletion); err != nil {
		log.Error().Err(err).Msgf("failed to unmarshal augmented answer for question ID %s", syn.QaID)
		return taskAugmented, selectedAugmentedMiner, augmentedPrompt, validatorContent, trapValue
	}

	if shouldDuelValidator {
		if len(augmentedCompletion.Responses) > 0 || len(augmentedCompletion.Responses[0].Completion.Files) > 0 {
			log.Debug().Msgf("Using augmented answer for question ID %s", syn.QaID)
			validatorContent = augmentedCompletion.Responses[0].Completion.Files[0].Content
			trapValue = v.ValidatorHotkey
		}
	} else {
		selectedAugmentedMiner = selectedMinerUIDs[cryptoIntn(len(selectedMinerUIDs))]
		augmentedPrompt = augmentedCompletion.Prompt
		trapValue = v.MetagraphData.Metagraph.Hotkeys[selectedAugmentedMiner]
	}

	taskAugmented = true
	return taskAugmented, selectedAugmentedMiner, augmentedPrompt, validatorContent, trapValue
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
		if !validatorDuel && taskAugmented && uid == selectedAugmentedMiner && augmentedPrompt != "" {
			prompt = augmentedPrompt
		}

		assignees = append(assignees, taskapi.AssigneeData{
			Hotkey: v.MetagraphData.Metagraph.Hotkeys[uid],
			Prompt: prompt,
			Role:   "miner",
		})
	}

	if validatorDuel {
		assignees = append(assignees, taskapi.AssigneeData{
			Hotkey: v.ValidatorHotkey,
			Prompt: basePrompt,
			Role:   "validator",
		})
	}

	return assignees
}

func (v *Validator) pickRandomMiners(activeMinerUIDs []int64, count int, processedMiners *ProcessedMiners) []int64 {
	processedMiners.m.Lock()
	defer processedMiners.m.Unlock()

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
		index := cryptoIntn(len(availableMiners))
		selectedMiners = append(selectedMiners, availableMiners[index])
		processedMiners.uids = append(processedMiners.uids, availableMiners[index])
		availableMiners = slices.Delete(availableMiners, index, index+1)
		if len(availableMiners) == 0 {
			break
		}
	}

	return selectedMiners
}
