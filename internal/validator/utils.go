package validator

import (
	"crypto/rand"
	"fmt"
	"math/big"

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
