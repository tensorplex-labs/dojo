package validator

import (
	"crypto/rand"
	"fmt"
	"math/big"
	"strconv"

	"github.com/rs/zerolog/log"

	"github.com/tensorplex-labs/dojo/internal/kami"
)

func (v *Validator) shouldAugment(probability int64) bool {
	limit := big.NewInt(100)
	n, err := rand.Int(rand.Reader, limit)
	if err != nil {
		return false
	}
	return n.Int64() < probability
}

func (v *Validator) incrementTaskRound() (int, error) {
	currentRound, err := v.Redis.Get(v.Ctx, "validator:task_round")
	if err != nil {
		return -1, fmt.Errorf("failed to get current task round: %w", err)
	}

	if currentRound == "" {
		log.Info().Msg("task round not set, initializing to 1")
		err = v.Redis.Set(v.Ctx, "validator:task_round", "1", 0)
		if err != nil {
			return -1, fmt.Errorf("failed to initialize task round: %w", err)
		}
		return 1, nil
	}

	currentRoundInt, err := strconv.Atoi(currentRound)
	if err != nil {
		return -1, fmt.Errorf("failed to convert current task round to int: %w", err)
	}

	newRound := currentRoundInt + 1
	err = v.Redis.Set(v.Ctx, "validator:task_round", strconv.Itoa(newRound), 0)
	if err != nil {
		return -1, fmt.Errorf("failed to set new task round: %w", err)
	}

	log.Info().Msgf("incremented task round to %d", newRound)
	return newRound, nil
}

func (v *Validator) randomStringToSign() (string, error) {
	const charset = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
	length := 52
	result := make([]byte, length)

	for i := range result {
		n, err := rand.Int(rand.Reader, big.NewInt(int64(len(charset))))
		if err != nil {
			return "", fmt.Errorf("failed to generate random index: %w", err)
		}
		result[i] = charset[n.Int64()]
	}

	return string(result), nil
}

func (v *Validator) signMessage(message string) (string, error) {
	if v.Kami == nil {
		return "", fmt.Errorf("kami client is not initialized")
	}

	params := kami.SignMessageParams{Message: message}

	resp, err := v.Kami.SignMessage(params)
	if err != nil {
		return "", fmt.Errorf("failed to sign message: %w", err)
	}

	return resp.Data.Signature, nil
}
