package chainutils

import "github.com/tensorplex-labs/dojo/internal/kami"

func GetColdkeyForHotkey(metagraph *kami.SubnetMetagraph, hotkey string) string {
	for uid, h := range metagraph.Hotkeys {
		if h == hotkey {
			if uid < len(metagraph.Coldkeys) {
				return metagraph.Coldkeys[uid]
			}
		}
	}
	return ""
}
