package signature

import (
	"encoding/hex"
	"fmt"

	"github.com/ChainSafe/gossamer/lib/crypto/sr25519"
	"github.com/rs/zerolog/log"
)

// NewProvider creates a new signature provider from a hotkey (private key seed)
func NewProvider(keypair *sr25519.Keypair) (*Provider, error) {
	return &Provider{
		keypair: keypair,
	}, nil
}

// Sign implements the SignatureProvider interface
func (p *Provider) Sign(message string) (string, error) {
	if p.keypair == nil {
		return "", fmt.Errorf("private key not initialized")
	}

	// Sign the message
	signature, err := p.keypair.Sign([]byte(message))
	if err != nil {
		log.Error().Err(err).Msg("Failed to sign message")
		return "", fmt.Errorf("failed to sign message: %w", err)
	}

	// Return signature as hex string with 0x prefix
	return "0x" + hex.EncodeToString(signature), nil
}
