package signature

import (
	"context"
	"fmt"
	"os"
	"os/user"
	"path/filepath"
	"strings"

	"github.com/ChainSafe/gossamer/lib/crypto/sr25519"
	"github.com/bytedance/sonic"
	"github.com/rs/zerolog/log"
	"github.com/tensorplex-labs/dojo/pkg/config"

	"github.com/sethvargo/go-envconfig"
)

func LoadMnemonic(path string) (string, error) {
	// Expand ~ to home directory
	if strings.HasPrefix(path, "~/") {
		usr, err := user.Current()
		if err != nil {
			return "", fmt.Errorf("failed to get current user: %w", err)
		}
		path = filepath.Join(usr.HomeDir, path[2:])
	}

	// Read the file
	data, err := os.ReadFile(path)
	if err != nil {
		log.Error().
			Err(err).
			Str("path", path).
			Msg("Failed to read keypair file")
		return "", fmt.Errorf("failed to read file: %w", err)
	}

	// Parse JSON
	var result map[string]interface{}
	err = sonic.Unmarshal(data, &result)
	if err != nil {
		log.Error().
			Err(err).
			Str("path", path).
			Msg("Failed to parse keypair JSON")
		return "", fmt.Errorf("failed to parse JSON: %w", err)
	}

	seed, ok := result["secretPhrase"]
	if !ok {
		log.Error().
			Str("path", path).
			Msg("SecretPhrase not found in keypair JSON")
		return "", fmt.Errorf("secretPhrase not found in JSON")
	}

	seedPhrase, ok := seed.(string)
	if !ok {
		log.Error().
			Str("path", path).
			Msg("SecretPhrase is not a string in keypair JSON")
		return "", fmt.Errorf("secretPhrase is not a string")
	}

	return seedPhrase, nil
}

func LoadKeypairFromHotkey(coldkeyName, hotkeyName string) (*sr25519.Keypair, error) {
	// Load bittensor directory from environment with default fallback
	ctx := context.Background()
	var envCfg config.WalletEnvConfig
	if err := envconfig.Process(ctx, &envCfg); err != nil {
		log.Fatal().Err(err).Msg("Failed to process environment variables for Wallet")
	}

	bittensorDir := envCfg.BittensorDir
	if bittensorDir == "" {
		bittensorDir = DefaultBittensorDir
		log.Debug().
			Str("default", DefaultBittensorDir).
			Msg("BITTENSOR_DIR not set, using default")
	} else {
		log.Debug().
			Str("bittensor_dir", bittensorDir).
			Msg("Loaded BITTENSOR_DIR from environment")
	}

	// Load wallet coldkey from environment with default fallback
	path := bittensorDir + "/wallets/" + coldkeyName + "/hotkeys/" + hotkeyName
	log.Debug().
		Str("path", path).
		Str("hotkey_name", hotkeyName).
		Msg("Loading keypair from hotkey path")

	mnemonic, err := LoadMnemonic(path)
	if err != nil {
		return nil, fmt.Errorf("failed to load seed phrase: %w", err)
	}

	// Create keypair from seed phrase
	keypair, err := sr25519.NewKeypairFromMnenomic(mnemonic, "")
	if err != nil {
		log.Error().
			Err(err).
			Str("path", path).
			Str("hotkey_name", hotkeyName).
			Msg("Failed to create keypair from seed phrase")
		return nil, fmt.Errorf("failed to create keypair from seed phrase: %w", err)
	}

	return keypair, nil
}
