package validator

import (
	"context"
	"fmt"
	"time"

	"github.com/rs/zerolog/log"
	"github.com/tensorplex-labs/dojo/internal/synapse"
	"github.com/tensorplex-labs/dojo/internal/syntheticapi"
	"github.com/tensorplex-labs/dojo/internal/taskapi"
	chainutils "github.com/tensorplex-labs/dojo/internal/utils/chain_utils"
)

func (v *Validator) heartBeat(ctx context.Context, client *synapse.Client, validatorHotkey string) {
	hb := synapse.HeartbeatRequest{
		ValidatorHotkey: validatorHotkey,
		Timestamp:       time.Now().UnixNano(),
	}

	currentAxons := v.MetagraphData.Metagraph.Axons
	if len(currentAxons) == 0 {
		return
	}

	for uid, axon := range currentAxons {
		rootStake := v.MetagraphData.Metagraph.TaoStake[uid]
		alphaStake := v.MetagraphData.Metagraph.AlphaStake[uid]
		miner, err := chainutils.CheckIfMiner(alphaStake, rootStake)
		if err != nil {
			log.Error().Err(err).Msg("failed to check miner status")
			continue
		}

		if !miner {
			continue
		}

		url := fmt.Sprintf("http://%s/%d/heartbeat", axon.IP, axon.Port)
		resp, err := client.SendHeartbeat(ctx, url, hb)
		if err != nil {
			log.Error().Err(err).Str("url", url).Msg("send heartbeat failed")
			continue
		}

		if resp.Status != "ok" {
			log.Warn().Str("url", url).Str("status", resp.Status).Msg("non-ok heartbeat response")
		}
	}
}

func (v *Validator) syncMetagraph() {
	v.mu.Lock()
	log.Info().Msg(fmt.Sprintf("syncing metagraph data for subnet: %d", v.ValidatorConfig.Netuid))
	// Placeholder for actual metagraph sync logic
	// This would typically involve fetching the latest metagraph from a source
	// and updating v.MetagraphData accordingly.
	newMetagraph, err := v.Kami.GetMetagraph(v.ValidatorConfig.Netuid)
	if err != nil {
		log.Error().Err(err).Msg("failed to get metagraph")
		return
	}

	// get current active miner UIDs
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
	if v.Redis == nil {
		log.Error().Msg("redis client is not initialized")
		return
	}

	// readiness checks before incrementing round
	taskCount, err := v.Redis.LLen(ctx, "synthetic:questions")
	if err != nil {
		log.Error().Err(err).Msg("failed to get task count from redis")
		return
	}

	active := len(v.MetagraphData.CurrentActiveMinerUids)
	if active == 0 {
		log.Info().Msg("no active miners, skipping task round")
		return
	}
	if taskCount < int64(active) {
		log.Info().Msg("not enough tasks in redis, skipping task round")
		return
	}

	currentRound, err := v.incrementTaskRound()
	if err != nil {
		log.Error().Err(err).Msg("failed to increment task round")
		return
	}
	log.Info().Msg(fmt.Sprintf("starting task round %d", currentRound))

	log.Info().Msg(fmt.Sprintf("sending task round with %d tasks", active))
	for i := range v.MetagraphData.CurrentActiveMinerUids {
		uid := int(v.MetagraphData.CurrentActiveMinerUids[i])
		targetMinerHotkey := v.MetagraphData.Metagraph.Hotkeys[uid]

		log.Info().Msgf("Processing task for miner UID %d of hotkey %s", v.MetagraphData.CurrentActiveMinerUids[i], targetMinerHotkey)

		synApiQuestion, err := v.SyntheticApi.GetQuestion()
		if err != nil {
			log.Error().Err(err).Msg("failed to get question from synthetic API")
			return
		}
		log.Debug().Msgf("Received question: %s of id: %s", synApiQuestion.Prompt, synApiQuestion.Qa_Id)

		// task request & completion logic
		log.Info().Msgf("Task round %d: processing question %d with ID %s", currentRound, i+1, synApiQuestion.Qa_Id)

		var completion syntheticapi.GenerateAnswerResponse[syntheticapi.CodegenAnswer]
		completion, err = v.SyntheticApi.GetCodegenAnswer(synApiQuestion.Qa_Id)
		if err != nil {
			log.Error().Err(err).Msgf("failed to get answer for question ID %s", synApiQuestion.Qa_Id)
			continue
		}

		// derive a common validatorContent from completion
		var validatorContent string
		if len(completion.Answer.Responses) > 0 {
			resp := completion.Answer.Responses[0]
			if len(resp.Completion.Files) > 0 {
				validatorContent = resp.Completion.Files[0].Content
			}
		}

		shouldAugment := v.shouldAugment()
		// shouldAugment := true // For testing purposes, always augment

		var taskApiRequestPayload taskapi.CreateTasksRequest[taskapi.CodegenTaskMetadata]
		var taskAssignees []string // TODO: bucket assign to multiple miners i guess in the future
		taskApiRequestPayload.TaskType = "codegen"
		taskApiRequestPayload.ExpireAt = time.Now().Add(6 * time.Hour).Format(time.RFC3339)
		taskApiRequestPayload.Assignees = append(taskAssignees, targetMinerHotkey)

		switch shouldAugment {
		case true:
			log.Debug().Msgf("Task round %d: augmenting question %d with ID %s", currentRound, i+1, synApiQuestion.Qa_Id)
			augmentedAnswer, err := v.augmentProcess(ctx, currentRound, uid, synApiQuestion)
			if err != nil {
				log.Error().Err(err).Msgf("failed to augment question ID %s", synApiQuestion.Qa_Id)
				continue
			}

			log.Info().Msgf("Received augmented answer: %+v\n", augmentedAnswer)

			// for now, just take the last augmented answer as the validator content
			if len(augmentedAnswer) == 0 {
				log.Error().Msgf("no augmented answers received for question ID %s", synApiQuestion.Qa_Id)
				continue
			}

			deadline := time.Now().Add(3 * time.Minute)
			var augmentedValidatorContent string
			for {
				log.Debug().Msgf("Waiting for augmented answer ID %s to be available in redis for question ID %s", augmentedAnswer[len(augmentedAnswer)-1], synApiQuestion.Qa_Id)
				// vc, err := v.Redis.Get(ctx, fmt.Sprintf("synthetic:answers:%s", augmentedAnswer[len(augmentedAnswer)-1]))
				augmentedCompletion, err := v.SyntheticApi.GetAugmentedCodegenAnswer(augmentedAnswer[len(augmentedAnswer)-1])
				if err != nil {
					log.Error().Err(err).Msgf("failed to get augmented answer from redis for question ID %s", synApiQuestion.Qa_Id)
				}
				if augmentedCompletion.Success {
					fmt.Printf("Augmented completion received: %+v\n", augmentedCompletion)
					augmentedValidatorContent = augmentedCompletion.AnsID.Responses[0].Completion.Files[0].Content
					log.Info().Msgf("Augmented answer available for question ID %s for completion ID %s", synApiQuestion.Qa_Id, augmentedAnswer[len(augmentedAnswer)-1])
					break
				}
				if time.Now().After(deadline) {
					log.Error().Msgf("timeout waiting for augmented answer for question ID %s reverting back to unaugmented answer", synApiQuestion.Qa_Id)
					break
				}

				select {
				case <-ctx.Done():
					return
				case <-time.After(1 * time.Second):
				}
			}
			taskApiRequestPayload.Metadata = taskapi.CodegenTaskMetadata{
				Prompt:              completion.Answer.Prompt,
				ValidatorCompletion: augmentedValidatorContent,
			}
		default:
			log.Debug().Msgf("Task round %d: processing question %d without augmentation with ID %s", currentRound, i+1, synApiQuestion.Qa_Id)
			taskApiRequestPayload.Metadata = taskapi.CodegenTaskMetadata{
				Prompt:              completion.Answer.Prompt,
				ValidatorCompletion: validatorContent,
			}
		}

		messageToSign, err := v.randomStringToSign()
		signature, err := v.signMessage(messageToSign)
		if err != nil {
			log.Error().Err(err).Msg("failed to sign message")
			continue
		}

		headers := taskapi.AuthHeaders{
			Hotkey:    v.ValidatorHotkey,
			Signature: signature,
			Message:   messageToSign,
		}

		_, err = v.TaskApi.CreateCodegenTask(headers, taskApiRequestPayload)
		if err != nil {
			log.Error().Err(err).Msgf("failed to create task for question %d with ID %s", i+1, synApiQuestion.Qa_Id)
			continue
		}

		log.Info().Msgf("Task round %d: created task for question %d with ID %s.", currentRound, i+1, synApiQuestion.Qa_Id)
	}
}

func (v *Validator) augmentProcess(ctx context.Context, currentRound int, minerUid int, synApiQuestion syntheticapi.GenerateQuestionResponse) ([]string, error) {
	var augmentedCompletionsID []string
	randomAugment := 1 // TODO: get synapi to support augments by level as in put instead of spitting out 1..3 variations
	// randomAugment := rand.Intn(3) + 1
	log.Debug().Msgf("Task round %d: augmenting question for miner %d with ID %s with %d variations\n", currentRound, minerUid, synApiQuestion.Qa_Id, randomAugment)
	augmentResponse, err := v.SyntheticApi.GetQuestionAugment(synApiQuestion.Prompt, randomAugment) // Randomly augment with 1-3 variations
	if err != nil {
		log.Error().Err(err).Msgf("failed to augment question %s for miner %d\n", synApiQuestion.Qa_Id, minerUid)
		return []string{}, err
	}
	log.Info().Msgf("Received augmentations: %+v\n", augmentResponse)
	for _, augment := range augmentResponse.Augments {
		fmt.Printf("Augments: %s", augment)
		augmentedQns, err := v.Redis.Get(ctx, fmt.Sprintf("synthetic:qn_augments:%s", augment))
		if err != nil {
			log.Error().Err(err).Msgf("failed to get augmented question from redis for question %s for miner %d\n", synApiQuestion.Qa_Id, minerUid)
			continue
		}

		log.Info().Msgf("Augmented qns received: %s\n", augmentedQns)

		augmentedCompletion, err := v.SyntheticApi.OrderAnswer(augmentedQns)
		if err != nil {
			log.Error().Err(err).Msgf("failed to get augmented answer for question %s for miner %d\n", synApiQuestion.Qa_Id, minerUid)
			continue
		}
		log.Info().Msgf("Received augmented completion ID: %+v\n", augmentedCompletion)
		augmentedCompletionsID = append(augmentedCompletionsID, augmentedCompletion.AnswerID)
	}
	return augmentedCompletionsID, nil
}
