package main

import (
	"log"

	"github.com/ChainSafe/gossamer/lib/crypto/sr25519"
	"github.com/tensorplex-labs/dojo/pkg/signature"
)

func main() {
	seed, err := signature.LoadMnemonic(
		"~/.bittensor/wallets/subnet_miner_test/hotkeys/one-time-use-README-update",
	)
	keypair, err := sr25519.NewKeypairFromMnenomic(seed, "")
	if err != nil {
		log.Fatalf("Failed to load private key: %v", err)
	}
	provider, err := signature.NewProvider(keypair)
	if err != nil {
		log.Fatalf("Failed to create signature provider: %v", err)
	}
	message := "Hello, world!"
	sig, err := provider.Sign("Hello, world!")
	if err != nil {
		log.Fatalf("Failed to sign message: %v", err)
	}
	log.Printf("Signature: %s", sig)
	ok, err := signature.Verify(message, sig, "5Eo6NTrTXRZp1FtvUvKQW9o9NPED25d5CpVYAs2eL5n2ZLwG")
	if err != nil {
		log.Fatalf("Failed to verify signature: %v", err)
	}
	log.Println("Signature valid:", ok)
}
