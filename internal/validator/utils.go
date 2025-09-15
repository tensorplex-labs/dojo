package validator

import (
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"math/big"
	"os"

	"github.com/bytedance/sonic"
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

func (v *Validator) rollProbability(percentage int64) bool {
	limit := big.NewInt(100)
	n, err := rand.Int(rand.Reader, limit)
	if err != nil {
		return false
	}
	return n.Int64() < percentage
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

// func getCurrentVersion() (int, error) {
// 	cmd := exec.CommandContext(context.Background(), "git describe --tags --abbrev=0")
// 	output, err := cmd.Output()
// 	if err != nil {
// 		return 0, err
// 	}
//
// 	version := strings.TrimSpace(string(output))
// 	return convertVersionToInt(version)
// }

// func convertVersionToInt(version string) (int, error) {
// 	// Remove "v" prefix if present
// 	version = strings.TrimPrefix(version, "v")
//
// 	parts := strings.Split(version, ".")
// 	if len(parts) != 3 {
// 		return 0, fmt.Errorf("invalid version format: %s", version)
// 	}
//
// 	major, err := strconv.Atoi(parts[0])
// 	if err != nil {
// 		return 0, fmt.Errorf("invalid major version: %s", parts[0])
// 	}
//
// 	minor, err := strconv.Atoi(parts[1])
// 	if err != nil {
// 		return 0, fmt.Errorf("invalid minor version: %s", parts[1])
// 	}
//
// 	patch, err := strconv.Atoi(parts[2])
// 	if err != nil {
// 		return 0, fmt.Errorf("invalid patch version: %s", parts[2])
// 	}
//
// 	return (1000 * major) + (10 * minor) + patch, nil
// }

func (v *Validator) setWeightsOnChain(uids []int64, weights []float64) error {
	// versionKey, err := getCurrentVersion()
	// if err != nil {
	// 	return fmt.Errorf("failed to get current version: %w", err)
	// }

	convertedUids, convertedWeights, err := chainutils.ConvertWeightsAndUidsForEmit(uids, weights)
	if err != nil {
		return fmt.Errorf("failed to convert weights and uids: %w", err)
	}

	log.Info().Msgf("Setting weights on chain: uids: %v, weights: %v", convertedUids, convertedWeights)

	subnetHyperparams, err := v.Kami.GetSubnetHyperparams(v.MetagraphData.Metagraph.Netuid)
	if err != nil {
		return fmt.Errorf("failed to get subnet hyperparams: %w", err)
	}

	if subnetHyperparams.Data.CommitRevealWeightsEnabled {
		tempo := v.MetagraphData.Metagraph.Tempo
		revealPeriod := subnetHyperparams.Data.CommitRevealPeriod

		if tempo == 0 || revealPeriod == 0 {
			return fmt.Errorf("tempo or reveal period is not set")
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
		// 	v.ValidatorHotkey, // TODO: needs to be in bytes!
		// )

		commitForReveal := "test"
		revealRound := 0

		log.Info().Msgf("Commit for reveal: %s", hex.EncodeToString([]byte(commitForReveal)))
		log.Info().Msgf("Reveal round: %d", revealRound)

		_, err = v.Kami.SetTimelockedWeights(kami.SetTimelockedWeightsParams{
			Netuid:              v.MetagraphData.Metagraph.Netuid,
			Commit:              hex.EncodeToString([]byte(commitForReveal)),
			RevealRound:         revealRound,
			CommitRevealVersion: 4,
		})
		if err != nil {
			return fmt.Errorf("failed to set timelocked weights: %w", err)
		}

		return nil
	}

	_, err = v.Kami.SetWeights(kami.SetWeightsParams{
		Netuid:  v.ValidatorConfig.Netuid,
		Dests:   convertedUids,
		Weights: convertedWeights,
		// VersionKey: versionKey,
		VersionKey: 1,
	})
	if err != nil {
		return fmt.Errorf("failed to set weights: %w", err)
	}

	return nil
}

func initializeScores(filename string) {
	scoresFileDataInitialState := ScoresFileData{
		Scores: make([]float64, uidCount),
		Step:   0,
	}

	// overwrite the file with 0 scores and 0 step
	jsonData, err := sonic.MarshalIndent(scoresFileDataInitialState, "", "  ")
	if err != nil {
		log.Error().Err(err).Msg("failed to marshal scores file data")
		return
	}
	if err := os.WriteFile(filename, jsonData, 0o600); err != nil {
		log.Error().Err(err).Msg("failed to write scores to file")
		return
	}
}
