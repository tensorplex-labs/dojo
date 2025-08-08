package kami

import (
	"fmt"
	"github.com/tensorplex-labs/dojo/pkg/config"
)

type Kami struct {
	Host string	
	Port string
	WalletHotkey string
	WalletColdkey string
}

// NewKami creates a new Kami instance with the provided configuration.
func NewKami(cfg *config.KamiEnvConfig) (*Kami, error) {
	// NewKami creates a new Kami instance with the provided configuration.

	if cfg == nil {
		return nil, fmt.Errorf("configuration cannot be nil")
	}

	return &Kami{
		Host:          cfg.KamiHost,
		Port:          cfg.KamiPort,
		WalletHotkey:  cfg.WalletHotkey,
		WalletColdkey: cfg.WalltetColdkey,
	}, nil
}

func (k *Kami) ServeAxon() error {
	// Implementation for serving the axon
	return nil
}

func (k *Kami) GetMetagraph() error {
	// Implementation for serving the metagraph

	return nil
}

func (k *Kami) GetAxon() error {
	// Implementation for serving the axon
	return nil
}

func (k *Kami) SetWeights() error {
	// Implementation for serving the axon by hotkey
	return nil
}
