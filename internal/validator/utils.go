package validator

import (
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"math/big"

	"github.com/rs/zerolog/log"
	"github.com/tensorplex-labs/dojo/internal/kami"
	"github.com/tensorplex-labs/dojo/internal/taskapi"
	chainutils "github.com/tensorplex-labs/dojo/internal/utils/chain_utils"
)

func (v *Validator) shouldAugment(probability int64) bool {
	limit := big.NewInt(100)
	n, err := rand.Int(rand.Reader, limit)
	if err != nil {
		return false
	}
	return n.Int64() < probability
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

func (v *Validator) setupAuthHeaders() (taskapi.AuthHeaders, error) {
	messageToSign, err := v.randomStringToSign()
	if err != nil {
		return taskapi.AuthHeaders{}, fmt.Errorf("failed to generate message: %w", err)
	}

	signature, err := v.signMessage(messageToSign)
	if err != nil {
		return taskapi.AuthHeaders{}, fmt.Errorf("failed to sign message: %w", err)
	}

	return taskapi.AuthHeaders{
		Hotkey:    v.ValidatorHotkey,
		Signature: signature,
		Message:   messageToSign,
	}, nil
}

// TODO implement version key

func (v *Validator) setWeights(uids []int64, weights []float64) (string, error) {

	convertedUids, convertedWeights, err := chainutils.ConvertWeightsAndUidsForEmit(uids, weights)
	if err != nil {
		return "", fmt.Errorf("failed to convert weights and uids: %w", err)
	}

	subnetHyperparams, err := v.Kami.GetSubnetHyperparams(v.MetagraphData.Metagraph.Netuid)
	if err != nil {
		return "", fmt.Errorf("failed to get subnet hyperparams: %w", err)
	}

	if subnetHyperparams.Data.CommitRevealWeightsEnabled {
		tempo := v.MetagraphData.Metagraph.Tempo
		revealPeriod := subnetHyperparams.Data.CommitRevealPeriod

		if tempo == 0 || revealPeriod == 0 {
			return "", fmt.Errorf("tempo or reveal period is not set")
		}

		log.Info().Msgf("Commit reveal weights enabled: tempo: %d, reveal_period: %d", tempo, revealPeriod)

		// TODO: implement get_encrypted_commit
		// commit_for_reveal, reveal_round := get_encrypted_commit(
		// 	convertedUids,
		// 	convertedWeights,
		// 	1,
		// 	tempo,
		// 	v.LatestBlock,
		// 	v.ValidatorConfig.Netuid,
		// 	revealPeriod,
		// 	12.0,
		// 	v.ValidatorHotkey,
		// )

		commit_for_reveal := "test"
		reveal_round := 0

		log.Info().Msgf("Commit for reveal: %s", hex.EncodeToString([]byte(commit_for_reveal)))
		log.Info().Msgf("Reveal round: %d", reveal_round)

		_, err = v.Kami.SetTimelockedWeights(kami.SetTimelockedWeightsParams{
			Netuid:        v.MetagraphData.Metagraph.Netuid,
			Commit:        hex.EncodeToString([]byte(commit_for_reveal)),
			RevealRound:   reveal_round,
			CommitVersion: 4,
		})

		if err != nil {
			return "", fmt.Errorf("failed to set timelocked weights: %w", err)
		}

		return "", nil

	}

	_, err = v.Kami.SetWeights(kami.SetWeightsParams{
		Netuid:     v.ValidatorConfig.Netuid,
		Dests:      convertedUids,
		Weights:    convertedWeights,
		VersionKey: 1,
	})
	if err != nil {
		return "", fmt.Errorf("failed to set weights: %w", err)
	}

	return "", nil

}
