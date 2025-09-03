package validator

import (
	"context"
	"fmt"
	"os"
	"time"

	"github.com/rs/zerolog/log"

	"github.com/tensorplex-labs/dojo/internal/syntheticapi"
	"github.com/tensorplex-labs/dojo/internal/taskapi"
	chainutils "github.com/tensorplex-labs/dojo/internal/utils/chain_utils"
)

func (v *Validator) syncMetagraph() {
	v.mu.Lock()

	log.Info().Msg(fmt.Sprintf("syncing metagraph data for subnet: %d", v.ValidatorConfig.Netuid))
	newMetagraph, err := v.Kami.GetMetagraph(v.ValidatorConfig.Netuid)
	if err != nil {
		log.Error().Err(err).Msg("failed to get metagraph")
		return
	}

	var currentActiveMiners []int64
	for uid, axon := range newMetagraph.Data.Axons {
		rootStake := newMetagraph.Data.TaoStake[uid]
		alphaStake := newMetagraph.Data.AlphaStake[uid]
		miner, err := chainutils.CheckIfMiner(alphaStake, rootStake)
		if err != nil {
			log.Error().Err(err).Msg("failed to check miner status")
			continue
		}
		if miner {
			currentActiveMiners = append(currentActiveMiners, int64(uid))
			log.Debug().Msgf("Found active miner UID %d at %s:%d", uid, axon.IP, axon.Port)
		}
	}

	log.Info().Msgf("Metagraph synced. Found %d active miners", len(currentActiveMiners))

	v.MetagraphData.Metagraph = newMetagraph.Data
	v.MetagraphData.CurrentActiveMinerUids = currentActiveMiners

	v.mu.Unlock()
}

func (v *Validator) syncBlock() {
	v.mu.Lock()

	log.Info().Msg(fmt.Sprintf("syncing latest block. current block : %d", v.LatestBlock))
	newBlockResp, err := v.Kami.GetLatestBlock()
	if err != nil {
		log.Error().Err(err).Msg("failed to get latest block")
		return
	}

	v.LatestBlock = int64(newBlockResp.Data.BlockNumber)
	v.mu.Unlock()
}

func (v *Validator) sendTaskRound() {
	if !v.taskRoundRunning.CompareAndSwap(false, true) {
		return
	}
	defer v.taskRoundRunning.Store(false)
	ctx := v.Ctx
	if !v.canStartTaskRound(ctx) {
		return
	}

	currentRound, err := v.incrementTaskRound()
	if err != nil {
		log.Error().Err(err).Msg("failed to increment task round")
		return
	}
	log.Info().Msg(fmt.Sprintf("starting task round %d", currentRound))

	active := len(v.MetagraphData.CurrentActiveMinerUids)
	log.Info().Msg(fmt.Sprintf("sending task round with %d tasks", active))
	for i := range v.MetagraphData.CurrentActiveMinerUids {
		v.processMinerTask(ctx, currentRound, i)
	}
}

func (v *Validator) canStartTaskRound(ctx context.Context) bool {
	if v.Redis == nil {
		log.Error().Msg("redis client is not initialized")
		return false
	}
	taskCount, err := v.Redis.LLen(ctx, "synthetic:questions")
	if err != nil {
		log.Error().Err(err).Msg("failed to get task count from redis")
		return false
	}
	active := len(v.MetagraphData.CurrentActiveMinerUids)
	if active == 0 {
		log.Info().Msg("no active miners, skipping task round")
		return false
	}
	if taskCount < int64(active) {
		log.Info().Msg("not enough tasks in redis, skipping task round")
		return false
	}
	return true
}

func (v *Validator) processMinerTask(ctx context.Context, currentRound, index int) {
	uid := int(v.MetagraphData.CurrentActiveMinerUids[index])
	targetMinerHotkey := v.MetagraphData.Metagraph.Hotkeys[uid]
	log.Info().Msgf(
		"Processing task for miner UID %d of hotkey %s",
		v.MetagraphData.CurrentActiveMinerUids[index], targetMinerHotkey,
	)

	synAPIQuestion, err := v.SyntheticAPI.GetQuestion()
	if err != nil {
		log.Error().Err(err).Msg("failed to get question from synthetic API")
		return
	}
	log.Debug().Msgf("Received question: %s of id: %s", synAPIQuestion.Prompt, synAPIQuestion.QaID)
	log.Info().Msgf("Task round %d: processing question %d with ID %s", currentRound, index+1, synAPIQuestion.QaID)

	completion, err := v.SyntheticAPI.GetCodegenAnswer(synAPIQuestion.QaID)
	if err != nil {
		log.Error().Err(err).Msgf("failed to get answer for question ID %s", synAPIQuestion.QaID)
		return
	}

	var validatorContent string
	if len(completion.Answer.Responses) > 0 {
		resp := completion.Answer.Responses[0]
		if len(resp.Completion.Files) > 0 {
			validatorContent = resp.Completion.Files[0].Content
		}
	}
	if validatorContent == "" {
		validatorContent = completion.Answer.Prompt
	}

	var payload taskapi.CreateTasksRequest[taskapi.CodegenTaskMetadata]
	payload.TaskType = "codegen"
	payload.ExpireAt = time.Now().Add(6 * time.Hour).Format(time.RFC3339)
	payload.Assignees = append(payload.Assignees, v.ValidatorHotkey)

	if v.shouldAugment() {
		augmentedContent := v.handleAugmentation(ctx, currentRound, uid, synAPIQuestion)
		if augmentedContent == "" {
			log.Error().Msgf("no augmented answers received for question ID %s", synAPIQuestion.QaID)
			return
		}
		payload.Metadata = taskapi.CodegenTaskMetadata{
			Prompt:              completion.Answer.Prompt,
			ValidatorCompletion: augmentedContent,
		}
	} else {
		log.Debug().Msgf(
			"Task round %d: processing question %d without augmentation with ID %s",
			currentRound, index+1, synAPIQuestion.QaID,
		)
		payload.Metadata = taskapi.CodegenTaskMetadata{
			Prompt:              completion.Answer.Prompt,
			ValidatorCompletion: validatorContent,
		}
	}

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
	var taskCreationResponse taskapi.Response[taskapi.CreateTaskResponse]
	if taskCreationResponse, err = v.TaskAPI.CreateCodegenTask(headers, payload); err != nil {
		log.Error().Err(err).Msgf("failed to create task for question %d with ID %s", index+1, synAPIQuestion.QaID)
		return
	}

	log.Info().Msgf("Task round %d: created task for question %d with ID %s.", currentRound, index+1, synAPIQuestion.QaID)

	taskID := taskCreationResponse.Data.TaskID
	// submit the completion to the task
	var submitCompletionResponse taskapi.Response[taskapi.SubmitCompletionResponse]
	if submitCompletionResponse, err = v.TaskAPI.SubmitCompletion(headers, taskID, validatorContent); err != nil {
		log.Error().Err(err).Msgf("failed to submit completion for task ID %s", taskID)
		return
	}

	log.Info().Msgf("Submitted completion with ID %s for task ID %s", submitCompletionResponse.Data.CompletionID, taskID)

	os.Exit(1)
}

func (v *Validator) handleAugmentation(
	ctx context.Context,
	currentRound, uid int,
	synAPIQuestion syntheticapi.GenerateQuestionResponse,
) string {
	augmentedAnswer, err := v.augmentProcess(ctx, currentRound, uid, synAPIQuestion)
	if err != nil {
		log.Error().Err(err).Msgf("failed to augment question ID %s", synAPIQuestion.QaID)
		return ""
	}
	log.Info().Msgf("Received augmented answer: %+v\n", augmentedAnswer)
	if len(augmentedAnswer) == 0 {
		return ""
	}
	ansID := augmentedAnswer[len(augmentedAnswer)-1]
	deadline := time.Now().Add(3 * time.Minute)
	for {
		log.Debug().Msgf(
			"Waiting for augmented answer ID %s to be available in redis for question ID %s",
			ansID, synAPIQuestion.QaID,
		)
		augmentedCompletion, err := v.SyntheticAPI.GetAugmentedCodegenAnswer(ansID)
		if err != nil {
			log.Error().Err(err).Msgf(
				"failed to get augmented answer from synthetic API for question ID %s",
				synAPIQuestion.QaID,
			)
		}
		if augmentedCompletion.Success {
			fmt.Printf("Augmented completion received: %+v\n", augmentedCompletion)
			log.Info().Msgf(
				"Augmented answer available for question ID %s for completion ID %s",
				synAPIQuestion.QaID, ansID,
			)
			return augmentedCompletion.AnsID.Responses[0].Completion.Files[0].Content
		}
		if time.Now().After(deadline) {
			log.Error().Msgf(
				"timeout waiting for augmented answer for question ID %s reverting back to unaugmented answer",
				synAPIQuestion.QaID,
			)
			break
		}
		select {
		case <-ctx.Done():
			return ""
		case <-time.After(1 * time.Second):
		}
	}
	return ""
}

func (v *Validator) augmentProcess(
	ctx context.Context,
	currentRound, minerUID int,
	synAPIQuestion syntheticapi.GenerateQuestionResponse,
) ([]string, error) {
	var augmentedCompletionsID []string
	randomAugment := 1
	log.Debug().Msgf(
		"Task round %d: augmenting question for miner %d with ID %s with %d variations\n",
		currentRound, minerUID, synAPIQuestion.QaID, randomAugment,
	)
	augmentResponse, err := v.SyntheticAPI.GetQuestionAugment(synAPIQuestion.Prompt, randomAugment)
	if err != nil {
		log.Error().Err(err).Msgf("failed to augment question %s for miner %d\n", synAPIQuestion.QaID, minerUID)
		return []string{}, err
	}
	log.Info().Msgf("Received augmentations: %+v\n", augmentResponse)
	for _, augment := range augmentResponse.Augments {
		fmt.Printf("Augments: %s", augment)
		augmentedQns, err := v.Redis.Get(ctx, fmt.Sprintf("synthetic:qn_augments:%s", augment))
		if err != nil {
			log.Error().Err(err).Msgf(
				"failed to get augmented question from redis for question %s for miner %d\n",
				synAPIQuestion.QaID, minerUID,
			)
			continue
		}
		log.Info().Msgf("Augmented qns received: %s\n", augmentedQns)
		augmentedCompletion, err := v.SyntheticAPI.OrderAnswer(augmentedQns)
		if err != nil {
			log.Error().Err(err).Msgf(
				"failed to get augmented answer for question %s for miner %d\n",
				synAPIQuestion.QaID, minerUID,
			)
			continue
		}
		log.Info().Msgf("Received augmented completion ID: %+v\n", augmentedCompletion)
		augmentedCompletionsID = append(augmentedCompletionsID, augmentedCompletion.AnswerID)
	}
	return augmentedCompletionsID, nil
}
