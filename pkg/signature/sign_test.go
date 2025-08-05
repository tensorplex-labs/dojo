package signature

import (
	"testing"

	"github.com/ChainSafe/gossamer/lib/crypto/sr25519"
	"github.com/vedhavyas/go-subkey"
)

func TestSignatureProvider(t *testing.T) {
	// Generate a test keypair
	keypair, err := sr25519.GenerateKeypair()
	if err != nil {
		t.Fatalf("Failed to generate keypair: %v", err)
	}

	// Create provider
	provider, err := NewProvider(keypair)
	if err != nil {
		t.Fatalf("Failed to create provider: %v", err)
	}

	message := "Hello World"

	// Sign the message
	signature, err := provider.Sign(message)
	if err != nil {
		t.Fatalf("Failed to sign message: %v", err)
	}

	// Verify the signature format
	if len(signature) < 2 || signature[:2] != "0x" {
		t.Error("Expected signature to start with '0x'")
	}

	if len(signature) != 130 { // 0x + 128 hex chars (64 bytes)
		t.Errorf("Expected signature length 130, got %d", len(signature))
	}

	// Convert public key to SS58 address for verification
	ss58Address := subkey.SS58Encode(keypair.Public().Encode(), SubstrateNetworkId)

	// Verify the signature using our verification function
	ok, err := Verify(message, signature, ss58Address)
	if err != nil {
		t.Fatalf("Verification failed: %v", err)
	}

	if !ok {
		t.Error("Expected signature to be valid, but verification failed")
	}
}

func TestSignatureProviderWithKnownSeed(t *testing.T) {
	// Use a known test seed for reproducible testing
	keypair, err := sr25519.NewKeypairFromMnenomic(subkey.DevPhrase, "")
	if err != nil {
		t.Fatalf("Failed to create keypair from seed: %v", err)
	}

	// Create provider
	provider, err := NewProvider(keypair)
	if err != nil {
		t.Fatalf("Failed to create provider: %v", err)
	}

	message := "test message for round trip"

	// Sign the message
	signature, err := provider.Sign(message)
	if err != nil {
		t.Fatalf("Failed to sign message: %v", err)
	}

	// Convert public key to SS58 address
	ss58Address := subkey.SS58Encode(keypair.Public().Encode(), SubstrateNetworkId)

	// Verify the signature
	ok, err := Verify(message, signature, ss58Address)
	if err != nil {
		t.Fatalf("Verification failed: %v", err)
	}

	if !ok {
		t.Error("Round trip test failed: signature verification failed")
	}
}

func TestSignatureProviderErrors(t *testing.T) {
	t.Run("nil keypair", func(t *testing.T) {
		provider := &Provider{keypair: nil}
		_, err := provider.Sign("test message")
		if err == nil {
			t.Error("Expected error for nil keypair")
		}
	})
}

func TestMultipleSignatures(t *testing.T) {
	// Test that the same message produces consistent signatures
	keypair, err := sr25519.GenerateKeypair()
	if err != nil {
		t.Fatalf("Failed to generate keypair: %v", err)
	}

	provider, err := NewProvider(keypair)
	if err != nil {
		t.Fatalf("Failed to create provider: %v", err)
	}

	message := "consistent message"

	// Sign the same message multiple times
	sig1, err := provider.Sign(message)
	if err != nil {
		t.Fatalf("Failed to sign message first time: %v", err)
	}

	sig2, err := provider.Sign(message)
	if err != nil {
		t.Fatalf("Failed to sign message second time: %v", err)
	}

	// SR25519 signatures are not deterministic, so they should be different
	if sig1 == sig2 {
		t.Error("Expected different signatures for the same message (SR25519 is non-deterministic)")
	}

	// But both should verify correctly
	ss58Address := subkey.SS58Encode(keypair.Public().Encode(), SubstrateNetworkId)

	ok1, err := Verify(message, sig1, ss58Address)
	if err != nil || !ok1 {
		t.Error("First signature should verify correctly")
	}

	ok2, err := Verify(message, sig2, ss58Address)
	if err != nil || !ok2 {
		t.Error("Second signature should verify correctly")
	}
}
