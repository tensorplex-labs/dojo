package validator

import (
	"context"
	"fmt"
	"math/rand"
	"os"
	"time"

	"github.com/rs/zerolog/log"
	"github.com/tensorplex-labs/dojo/internal/synapse"
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
	v.MetagraphData.Metagraph = newMetagraph.Data
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
	ctx := v.Ctx
	if v.Redis == nil {
		log.Error().Msg("redis client is not initialized")
		return
	}

	// retrieve the current round
	currentRound, err := v.incrementTaskRound()
	if err != nil {
		log.Error().Err(err).Msg("failed to increment task round")
		return
	}

	log.Info().Msg(fmt.Sprintf("starting task round %d", currentRound))

	taskCount, err := v.Redis.LLen(ctx, "synthetic:questions")
	if err != nil {
		log.Error().Err(err).Msg("failed to get task count from redis")
		return
	}

	if taskCount < 25 { // TODO: this should be CURRENT_ACTIVE_MINER_UIDS
		log.Info().Msg("not enough tasks in redis, skipping task round")
		return
	}

	log.Info().Msg(fmt.Sprintf("sending task round with %d tasks", taskCount))
	for i := 0; i < int(taskCount); i++ {
		synApiQuestion, err := v.SyntheticApi.GetQuestion()
		if err != nil {
			log.Error().Err(err).Msg("failed to get question from synthetic API")
			return
		}
		log.Debug().Msgf("Received question: %s of id: %s", synApiQuestion.Prompt, synApiQuestion.Qa_Id)
		// task request & completion logic
		log.Info().Msgf("Task round %d: processing question %d with ID %s", currentRound, i+1, synApiQuestion.Qa_Id)

		completion, err := v.SyntheticApi.GetCodegenAnswer(synApiQuestion.Qa_Id)
		if err != nil {
			log.Error().Err(err).Msgf("failed to get answer for question ID %s", synApiQuestion.Qa_Id)
			continue
		}

		// fmt.Printf("Task round %d: received completion for question %d with ID %s: %+v\n", currentRound, i+1, synApiQuestion.Qa_Id, completion)
		// os.Exit(0)

		// shouldAugment := v.shouldAugment() // 25% chance to augment the question
		shouldAugment := false // For testing purposes, always augment
		// type CreateTasksRequest struct {
		// 	TaskType string `form:"task_type" json:"task_type"`
		// 	Metadata string `form:"metadata" json:"metadata"`
		// 	Assignee string `form:"assignee" json:"assignee"`
		// 	ExpireAt string `form:"expire_at" json:"expire_at"`
		// }

		// var finalCompletion syntheticapi.CodegenAnswer

		var taskApiRequestPayload taskapi.CreateTasksRequest[taskapi.CodegenTaskMetadata]
		taskApiRequestPayload.TaskType = "codegen"
		taskApiRequestPayload.ExpireAt = time.Now().Add(6 * time.Hour).Format(time.RFC3339)

		switch shouldAugment {
		case true:
			log.Debug().Msgf("Task round %d: augmenting question %d with ID %s", currentRound, i+1, synApiQuestion.Qa_Id)
			augmentResponse, err := v.SyntheticApi.GetQuestionAugment(synApiQuestion.Prompt, rand.Intn(3)+1) // Randomly augment with 1-3 variations
			if err != nil {
				log.Error().Err(err).Msgf("failed to augment question %d with ID %s", i+1, synApiQuestion.Qa_Id)
				continue
			}
			log.Info().Msgf("Received augmentations: %+v\n", augmentResponse)
			for _, augment := range augmentResponse.Augments {
				fmt.Printf("Augments: %s", augment)
				augmentedQns, err := v.Redis.Get(ctx, fmt.Sprintf("synthetic:qn_augments:%s", augment))
				if err != nil {
					log.Error().Err(err).Msgf("failed to get augmented question from redis for question %d with ID %s", i+1, synApiQuestion.Qa_Id)
					continue
				}

				log.Info().Msgf("Augmented qns received: %s", augmentedQns)

				augmentedCompletion, err := v.SyntheticApi.OrderAnswer(augmentedQns)
				if err != nil {
					log.Error().Err(err).Msgf("failed to get augmented answer for question %d with ID %s", i+1, synApiQuestion.Qa_Id)
					continue
				}
				log.Info().Msgf("Received augmented completion ID: %+v\n", augmentedCompletion)
			}
			os.Exit(0)
		default:
			log.Debug().Msgf("Task round %d: processing question %d without augmentation with ID %s", currentRound, i+1, synApiQuestion.Qa_Id)
			// Defensive checks to avoid index panics if responses/files are empty
			var validatorContent string
			if len(completion.Answer.Responses) > 0 {
				resp := completion.Answer.Responses[0]
				if len(resp.Completion.Files) > 0 {
					validatorContent = resp.Completion.Files[0].Content
				}
			}
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

		os.Exit(0)
	}
}

func (v *Validator) augmentProcess() {}
