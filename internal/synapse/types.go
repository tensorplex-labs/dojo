package synapse

import (
	"time"

	"github.com/tensorplex-labs/dojo/internal/config"
)

type Config struct {
	config.MinerEnvConfig
	ClientTimeout time.Duration
	RetryMax      int
	RetryWait     time.Duration
}

type HeartbeatRequest struct {
	Timestamp       int64  `json:"timestamp"`
	ValidatorHotkey string `json:"validator_hotkey"`
}

type HeartbeatResponse struct {
	Status     string `json:"status"`
	ReceivedAt int64  `json:"received_at"`
	Message    string `json:"message,omitempty"`
}
