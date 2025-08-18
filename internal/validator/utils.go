package validator

import (
	"crypto/rand"
	"fmt"
	"math/big"
	"strconv"

	"github.com/rs/zerolog/log"
)

func (v *Validator) shouldAugment() bool {
	max := big.NewInt(100)
	n, err := rand.Int(rand.Reader, max)
	if err != nil {
		return false
	}
	return n.Int64() < 25 // 25% chance to augment to prevent gaming
}

func (v *Validator) incrementTaskRound() (int, error) {
	// Increment the task round in Redis

	currentRound, err := v.Redis.Get(v.Ctx, "validator:task_round")
	if err != nil {
		return -1, fmt.Errorf("failed to get current task round: %w", err)
	}

	if currentRound == "" {
		log.Info().Msg("task round not set, initializing to 1")
		if err := v.Redis.Set(v.Ctx, "validator:task_round", "1", 0); err != nil {
			return -1, fmt.Errorf("failed to initialize task round: %w", err)
		}
		return 1, nil
	}

	currentRoundInt, err := strconv.Atoi(currentRound)
	if err != nil {
		return -1, fmt.Errorf("failed to convert current task round to int: %w", err)
	}

	newRound := currentRoundInt + 1
	if err := v.Redis.Set(v.Ctx, "validator:task_round", strconv.Itoa(newRound), 0); err != nil {
		return -1, fmt.Errorf("failed to set new task round: %w", err)
	}

	log.Info().Msgf("incremented task round to %d", newRound)
	return newRound, nil
}
