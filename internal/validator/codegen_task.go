package validator

import (
	"time"

	"github.com/rs/zerolog/log"

	"github.com/tensorplex-labs/dojo/internal/syntheticapi"
	"github.com/tensorplex-labs/dojo/internal/taskapi"
)

const (
	taskType             = "codeGen"
	augmentedProbability = int64(25)
	expireAt             = 6 * time.Hour
)

func (v *Validator) processCodegenTask(index int, minerUID int64) {
	synAPIQuestion, err := v.SyntheticAPI.GetQuestion()
	if err != nil {
		log.Error().Err(err).Msg("failed to get question from synthetic API")
		return
	}
	log.Debug().Msgf("Received question: %s of id: %s", synAPIQuestion.Prompt, synAPIQuestion.QaID)
	log.Info().Msgf("Processing question %d with ID %s", index+1, synAPIQuestion.QaID)

	completion, err := v.SyntheticAPI.GetCodegenAnswer(synAPIQuestion.QaID)
	if err != nil {
		log.Error().Err(err).Msgf("failed to get answer for question ID %s", synAPIQuestion.QaID)
		return
	}

	if len(completion.Answer.Responses) == 0 ||
		len(completion.Answer.Responses[0].Completion.Files) == 0 ||
		completion.Answer.Responses[0].Completion.Files[0].Content == "" {
		log.Error().Msgf("empty completion for question ID %s", synAPIQuestion.QaID)
		return
	}
	var validatorContent string
	validatorContent = completion.Answer.Responses[0].Completion.Files[0].Content

	var payload taskapi.CreateTasksRequest[taskapi.CodegenTaskMetadata]
	payload.TaskType = taskType
	payload.ExpireAt = time.Now().Add(expireAt).Format(time.RFC3339)
	payload.Assignees = append(payload.Assignees, v.MetagraphData.Metagraph.Hotkeys[minerUID], v.ValidatorHotkey)
	payload.Metadata = taskapi.CodegenTaskMetadata{
		Prompt: completion.Answer.Prompt,
	}

	if v.shouldAugment(augmentedProbability) {
		var augmentedCompletion syntheticapi.GenerateAnswerResponse[syntheticapi.CodegenAnswer]
		augmentedCompletion, err = v.SyntheticAPI.GetCodegenAnswer(synAPIQuestion.AnsAugID)
		if err != nil {
			log.Error().Err(err).Msgf("failed to get augmented answer for question ID %s", synAPIQuestion.QaID)
		}

		if len(augmentedCompletion.Answer.Responses) > 0 ||
			len(augmentedCompletion.Answer.Responses[0].Completion.Files) > 0 {
			log.Info().Msgf("Using augmented answer for question ID %s", synAPIQuestion.QaID)
			validatorContent = augmentedCompletion.Answer.Responses[0].Completion.Files[0].Content
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
	taskCreationResponse, err := v.TaskAPI.CreateCodegenTask(headers, payload, validatorContent)
	if err != nil {
		log.Error().Err(err).Msgf("failed to create task for question %d with ID %s", index+1, synAPIQuestion.QaID)
		return
	}

	log.Info().Msgf("Created task and completion for task ID %s", taskCreationResponse.Data.TaskID)
}
