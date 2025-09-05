package validator

import (
	"time"

	"github.com/rs/zerolog/log"

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
		augmentedCompletion, err := v.SyntheticAPI.GetCodegenAnswer(synAPIQuestion.AnsAugID)
		if err != nil {
			log.Error().Err(err).Msgf("failed to get augmented answer for question ID %s", synAPIQuestion.QaID)
		}
		if len(augmentedCompletion.Answer.Responses) > 0 {
			resp := augmentedCompletion.Answer.Responses[0]
			if len(resp.Completion.Files) > 0 && len(resp.Completion.Files[0].Content) > 0 {
				payload.Metadata.ValidatorCompletion = resp.Completion.Files[0].Content
				validatorContent = resp.Completion.Files[0].Content
				log.Info().Msgf("Using augmented answer for question ID %s", synAPIQuestion.QaID)
			}
		}
	} else {
		log.Info().Msgf("Not using augmented answer for question ID %s", synAPIQuestion.QaID)
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
