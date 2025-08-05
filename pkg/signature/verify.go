package signature

import (
	"encoding/hex"
	"fmt"
	"strings"

	"github.com/ChainSafe/gossamer/lib/crypto/sr25519"
	"github.com/rs/zerolog/log"
	"github.com/vedhavyas/go-subkey"
)

// NewVerifier creates a new signature verifier
func NewVerifier() *Verifier {
	return &Verifier{}
}

// Verify implements the SignatureVerifier interface
func (v *Verifier) Verify(message, signature, ss58Address string) (bool, error) {
	return Verify(message, signature, ss58Address)
}

func Verify(message, signature, ss58Address string) (bool, error) {
	// Validate signature format
	if !strings.HasPrefix(signature, "0x") {
		log.Error().Msg("Signature does not start with '0x'")
		return false, fmt.Errorf("signature does not start with '0x'")
	}

	// Remove 0x prefix and decode hex
	sigBytes, err := hex.DecodeString(signature[2:])
	if err != nil {
		log.Error().Err(err).Msg("Failed to decode signature hex")
		return false, fmt.Errorf("failed to decode signature hex: %w", err)
	}

	if len(sigBytes) != 64 {
		log.Error().Int("got", len(sigBytes)).Msg("Invalid signature length: expected 64 bytes")
		return false, fmt.Errorf(
			"invalid signature length: expected 64 bytes, got %d",
			len(sigBytes),
		)
	}

	// Use go-subkey to decode SS58 address
	_, pubKeyBytes, err := subkey.SS58Decode(ss58Address)
	if err != nil {
		log.Error().Err(err).Msg("Failed to decode SS58 address to derive public key")
		return false, fmt.Errorf("failed to decode SS58 address to derive public key: %w", err)
	}

	// Create public key using Gossamer
	publicKey, err := sr25519.NewPublicKey(pubKeyBytes)
	if err != nil {
		log.Error().Err(err).Msg("Failed to create public key")
		return false, fmt.Errorf("failed to create public key: %w", err)
	}

	// Verify signature using Gossamer sr25519
	ok, err := publicKey.Verify([]byte(message), sigBytes)
	if err != nil {
		return ok, err
	}

	return ok, nil
}
