package kami

func FindAxonByHotkey(metagraph *SubnetMetagraph, hotkey string) *AxonInfo {
	for i, currHotkey := range metagraph.Hotkeys {
		if currHotkey == hotkey {
			axon := metagraph.Axons[i]
			return &axon
		}
	}
	return nil
}

func GetHotkey(k *Kami) (string, error) {
	keyringPair, err := k.GetKeyringPair()
	if err != nil {
		return "", err
	}
	return keyringPair.Data.KeyringPair.Address, nil
}
