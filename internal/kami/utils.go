package kami

func FindAxonByHotkey(metagraph SubnetMetagraph, hotkey string) *AxonInfo {
	index := -1
	for i, currHotkey := range metagraph.Hotkeys {
		if currHotkey == hotkey {
			index = i
			break
		}
	}

	if index < 0 {
		return nil
	}

	axon := metagraph.Axons[index]
	return &axon
}
