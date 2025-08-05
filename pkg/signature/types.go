package signature

import "github.com/ChainSafe/gossamer/lib/crypto/sr25519"

const (
	SubstrateNetworkId = 42

	// Default paths
	DefaultBittensorDir  = "~/.bittensor"
	DefaultWalletColdkey = "default"
)

type SignatureVerifier interface {
	// Verify checks if the provided signature is valid for the given message and SS58 address.
	Verify(message, signature, ss58Address string) (bool, error)
}

// Verifier is a concrete implementation of SignatureVerifier
type Verifier struct{}

type SignatureProvider interface {
	// Sign generates a signature for the given message using the hotkey
	Sign(message string) (string, error)
}

// Provider is a concrete implementation of SignatureProvider
type Provider struct {
	keypair *sr25519.Keypair
}
