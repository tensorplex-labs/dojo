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
	taskType                 = "codeGen"
	augmentedProbability     = int64(25) // 25% chance for traps
	validatorDuelProbability = int64(20) // 20% chance to duel validator
)

func (v *Validator) processCodegenTask(activeMinerUIDs []int64, processedMiners *ProcessedMiners) {
	for len(processedMiners.uids) < len(activeMinerUIDs) {
		var (
			shouldDuelValidator bool
			shouldAugment       bool
			selectedMinerUIDs   []int64
			validatorCompletion string
		)

		shouldDuelValidator = v.rollProbability(validatorDuelProbability)
		shouldAugment = v.rollProbability(augmentedProbability)
		selectedMinerUIDs = v.pickRandomMiners(activeMinerUIDs, shouldDuelValidator, processedMiners)

		log.Debug().Msgf("Selected miners for codegen task: %+v", selectedMinerUIDs)
		log.Debug().Msgf("Should duel validator: %t", shouldDuelValidator)
		log.Debug().Msgf("Should augment: %t", shouldAugment)

		synAPIQuestion, err := v.SyntheticAPI.GetQuestion()
		if err != nil {
			log.Error().Err(err).Msg("Failed to get question from synthetic API")
			continue
		}
		log.Debug().Msgf("Received question: %s of id: %s", synAPIQuestion.Prompt, synAPIQuestion.QaID)

		completionRaw, err := v.Redis.Get(v.Ctx, fmt.Sprintf("%s:%s", redisSyntheticAnswersKey, synAPIQuestion.QaID))
		if err != nil {
			log.Error().Err(err).Msgf("Failed to get answer content from redis for question ID %s", synAPIQuestion.QaID)
			continue
		}

		var completion syntheticapi.CodegenAnswer
		if err = sonic.Unmarshal([]byte(completionRaw), &completion); err != nil {
			log.Error().Err(err).Msgf("Failed to unmarshal answer content from redis for %s", synAPIQuestion.QaID)
			continue
		}
		validatorCompletion = completion.Responses[0].Completion.Files[0].Content

		augmentArgs := augmentTaskArgs{
			shouldDuelValidator: shouldDuelValidator,
			shouldAugment:       shouldAugment,
			syn:                 synAPIQuestion,
			selectedMinerUIDs:   selectedMinerUIDs,
			initialContent:      validatorCompletion,
		}
		augmentedPrompt, validatorCompletion, trapHotkey := v.augmentTask(&augmentArgs)

		payload := taskapi.CreateTasksRequest[taskapi.CodegenTaskMetadata]{
			TaskType:  taskType,
			ExpireAt:  time.Now().Add(v.IntervalConfig.TaskExpiryDuration).Format(time.RFC3339),
			Assignees: v.buildAssignees(synAPIQuestion.Prompt, selectedMinerUIDs, shouldDuelValidator, augmentedPrompt, trapHotkey),
			Metadata: taskapi.CodegenTaskMetadata{
				Prompt:                  synAPIQuestion.Prompt,
				ValidatorDuel:           shouldDuelValidator,
				NegativeGeneratorHotkey: trapHotkey,
			},
		}

		headers, err := v.setupAuthHeaders()
		if err != nil {
			log.Error().Err(err).Msg("Failed to sign message")
			continue
		}

		content := ""
		if shouldDuelValidator {
			content = validatorCompletion
		}

		taskCreationResponse, err := v.TaskAPI.CreateCodegenTask(headers, payload, content)
		if err != nil {
			log.Error().Err(err).Msgf("Failed to create task for question with ID %s for %+v ", synAPIQuestion.QaID, selectedMinerUIDs)
			continue
		}

		// If dueling validator, only one miner
		log.Debug().Msgf("Created codegen task with ID %s for %+v", taskCreationResponse.Data.TaskID, selectedMinerUIDs)

		if trapHotkey != "" {
			if err = v.Redis.Set(v.Ctx, fmt.Sprintf("%s:%s", redisTrapKey, taskCreationResponse.Data.TaskID), trapHotkey, 2*v.IntervalConfig.ScoreResetInterval); err != nil {
				log.Error().Err(err).Msgf("Failed to set trap for task ID %s", taskCreationResponse.Data.TaskID)
				continue
			} else {
				if shouldDuelValidator {
					log.Debug().Msgf("Set trap for task ID %s for %+v and validator", taskCreationResponse.Data.TaskID, selectedMinerUIDs)
				} else {
					log.Debug().Msgf("Set trap for task ID %s for %+v", taskCreationResponse.Data.TaskID, selectedMinerUIDs)
				}
			}
		}

		ok, err := v.SyntheticAPI.PopQA(synAPIQuestion.QaID)
		if err != nil {
			log.Error().Err(err).Msgf("Failed to pop question with ID %s", synAPIQuestion.QaID)
			continue
		}
		if !ok {
			log.Error().Msgf("Failed to pop question with ID %s", synAPIQuestion.QaID)
			continue
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
		log.Error().Err(err).Msg("Failed to generate crypto random int, defaulting to 0")
		return 0
	}
	return int(r.Int64())
}

type augmentTaskArgs struct {
	shouldDuelValidator bool
	shouldAugment       bool
	syn                 syntheticapi.GenerateQuestionResponse
	selectedMinerUIDs   []int64
	initialContent      string
}

func (v *Validator) augmentTask(
	args *augmentTaskArgs,
) (
	augmentedPrompt string,
	validatorContent string,
	trapHotkey string,
) {
	augmentedPrompt = ""
	validatorContent = args.initialContent
	trapHotkey = ""

	if !args.shouldAugment {
		log.Debug().Msgf("Not using augmented answer for question ID %s", args.syn.QaID)
		return augmentedPrompt, validatorContent, trapHotkey
	}

	augmentedCompletionRaw, err := v.Redis.Get(v.Ctx, fmt.Sprintf("%s:%s", redisSyntheticAnswersKey, args.syn.AnsAugID))
	if err != nil {
		log.Error().Err(err).Msgf("Failed to get augmented answer for question ID %s", args.syn.QaID)
	}

	var augmentedCompletion syntheticapi.CodegenAnswer
	if err = sonic.Unmarshal([]byte(augmentedCompletionRaw), &augmentedCompletion); err != nil {
		log.Error().Err(err).Msgf("Failed to unmarshal augmented answer for question ID %s", args.syn.QaID)
		return augmentedPrompt, validatorContent, trapHotkey
	}

	if args.shouldDuelValidator {
		if len(augmentedCompletion.Responses) > 0 || len(augmentedCompletion.Responses[0].Completion.Files) > 0 {
			augmentedPrompt = augmentedCompletion.Prompt
			validatorContent = augmentedCompletion.Responses[0].Completion.Files[0].Content
			trapHotkey = v.ValidatorHotkey

			log.Debug().Msgf("Using augmented answer for question ID %s with trap hotkey %s", args.syn.QaID, trapHotkey)
		}
	} else {
		selectedAugmentedMiner := args.selectedMinerUIDs[cryptoIntn(len(args.selectedMinerUIDs))]
		augmentedPrompt = augmentedCompletion.Prompt
		trapHotkey = v.MetagraphData.Metagraph.Hotkeys[selectedAugmentedMiner]

		log.Debug().Msgf("Using augmented prompt for question ID %s with trap hotkey %s", args.syn.QaID, trapHotkey)
	}

	return augmentedPrompt, validatorContent, trapHotkey
}

func (v *Validator) buildAssignees(
	basePrompt string,
	selectedMinerUIDs []int64,
	validatorDuel bool,
	augmentedPrompt string,
	trapHotkey string,
) []taskapi.AssigneeData {
	var assignees []taskapi.AssigneeData
	for _, uid := range selectedMinerUIDs {
		prompt := basePrompt

		if v.MetagraphData.Metagraph.Hotkeys[uid] == trapHotkey && augmentedPrompt != "" {
			prompt = augmentedPrompt
		}

		assignees = append(assignees, taskapi.AssigneeData{
			Hotkey: v.MetagraphData.Metagraph.Hotkeys[uid],
			Prompt: prompt,
			Role:   "miner",
		})
	}

	if validatorDuel {
		validatorPrompt := basePrompt

		if trapHotkey == v.ValidatorHotkey {
			validatorPrompt = augmentedPrompt
		}

		assignees = append(assignees, taskapi.AssigneeData{
			Hotkey: v.ValidatorHotkey,
			Prompt: validatorPrompt,
			Role:   "validator",
		})
	}

	return assignees
}

func (v *Validator) pickRandomMiners(activeMinerUIDs []int64, shouldDuelValidator bool, processedMiners *ProcessedMiners) []int64 {
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

	minerCount := 2
	if shouldDuelValidator {
		minerCount = 1
	}

	if len(availableMiners) < minerCount {
		minerCount = len(availableMiners)
	}

	selectedMiners := make([]int64, 0, minerCount)
	for i := 0; i < minerCount; i++ {
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
