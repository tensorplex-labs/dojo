package chainutils

import "github.com/tensorplex-labs/dojo/internal/kami"

func GetHotkey(k *kami.Kami) (string, error) {
	if k == nil {
		return "", nil
	}
	keyringPair, err := k.GetKeyringPair()
	if err != nil {
		return "", err
	}
	return keyringPair.Data.KeyringPair.Address, nil
}
