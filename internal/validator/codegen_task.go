package validator

import (
	"context"
	"fmt"
	"time"

	"github.com/rs/zerolog/log"

	"github.com/tensorplex-labs/dojo/internal/syntheticapi"
	"github.com/tensorplex-labs/dojo/internal/taskapi"
)

func (v *Validator) processCodegenTask(currentRound, index int, minerUid int64) {
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
		log.Error().Msgf("empty completion for question ID %s", synAPIQuestion.QaID)
		return
	}

	var payload taskapi.CreateTasksRequest[taskapi.CodegenTaskMetadata]
	payload.TaskType = "codeGen"
	payload.ExpireAt = time.Now().Add(6 * time.Hour).Format(time.RFC3339)
	payload.Assignees = append(payload.Assignees, v.MetagraphData.Metagraph.Hotkeys[minerUid], v.ValidatorHotkey)
	payload.Metadata = taskapi.CodegenTaskMetadata{
		Prompt:              completion.Answer.Prompt,
		ValidatorCompletion: validatorContent,
	}

	if v.shouldAugment() {
		augmentedCompletion, err := v.SyntheticAPI.GetAugmentedCodegenAnswer(synAPIQuestion.QaID)
		if err != nil {
			log.Error().Err(err).Msgf("failed to get augmented answer for question ID %s", synAPIQuestion.QaID)
		} else if len(augmentedCompletion.AnsID.Responses) > 0 {
			resp := augmentedCompletion.AnsID.Responses[0]
			if len(resp.Completion.Files) > 0 {
				payload.Metadata.ValidatorCompletion = resp.Completion.Files[0].Content
			}
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
	contentToSubmit := validatorContent
	var submitCompletionResponse taskapi.Response[taskapi.SubmitCompletionResponse]
	if submitCompletionResponse, err = v.TaskAPI.SubmitCompletion(headers, taskID, contentToSubmit); err != nil {
		log.Error().Err(err).Msgf("failed to submit completion for task ID %s", taskID)
		return
	}

	log.Info().Msgf("Submitted completion with ID %s for task ID %s", submitCompletionResponse.Data.CompletionID, taskID)
}

func (v *Validator) handleAugmentation(
	ctx context.Context,
	currentRound, uid int,
	synAPIQuestion syntheticapi.GenerateQuestionResponse,
) string {
	augmentedAnswer, err := v.augmentProcess(ctx, uid, synAPIQuestion)
	if err != nil {
		log.Error().Err(err).Msgf("failed to augment question ID %s", synAPIQuestion.QaID)
		return ""
	}
	if len(augmentedAnswer) == 0 {
		return ""
	}
	ansID := augmentedAnswer[len(augmentedAnswer)-1]
	deadline := time.Now().Add(3 * time.Minute)
	for {
		augmentedCompletion, err := v.SyntheticAPI.GetAugmentedCodegenAnswer(ansID)
		if err != nil {
			log.Error().Err(err).Msgf(
				"failed to get augmented answer from synthetic API for question ID %s",
				synAPIQuestion.QaID,
			)
		}
		if augmentedCompletion.Success && len(augmentedCompletion.AnsID.Responses) > 0 && len(augmentedCompletion.AnsID.Responses[0].Completion.Files) > 0 {
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
	minerUID int,
	synAPIQuestion syntheticapi.GenerateQuestionResponse,
) ([]string, error) {
	var augmentedCompletionsID []string
	randomAugment := 1
	augmentResponse, err := v.SyntheticAPI.GetQuestionAugment(synAPIQuestion.Prompt, randomAugment)
	if err != nil {
		log.Error().Err(err).Msgf("failed to augment question %s for miner %d\n", synAPIQuestion.QaID, minerUID)
		return []string{}, err
	}
	for _, augment := range augmentResponse.Augments {
		augmentedQns, err := v.Redis.Get(ctx, fmt.Sprintf("synthetic:qn_augments:%s", augment))
		if err != nil {
			log.Error().Err(err).Msgf(
				"failed to get augmented question from redis for question %s for miner %d\n",
				synAPIQuestion.QaID, minerUID,
			)
			continue
		}
		augmentedCompletion, err := v.SyntheticAPI.OrderAnswer(augmentedQns)
		if err != nil {
			log.Error().Err(err).Msgf(
				"failed to get augmented answer for question %s for miner %d\n",
				synAPIQuestion.QaID, minerUID,
			)
			continue
		}
		augmentedCompletionsID = append(augmentedCompletionsID, augmentedCompletion.AnswerID)
	}
	return augmentedCompletionsID, nil
}
