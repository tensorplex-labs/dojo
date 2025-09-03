// Package validator contains the validator orchestration logic and types used
// to coordinate task rounds, metagraph synchronization, and API interactions.
package validator

import (
	"time"

	"github.com/tensorplex-labs/dojo/internal/kami"
)

// IntervalConfig groups ticker intervals used by the validator runtime.
type IntervalConfig struct {
	HeartbeatInterval time.Duration
	MetagraphInterval time.Duration
	TaskRoundInterval time.Duration
	BlockInterval     time.Duration
}

// MetagraphData holds the current subnet metagraph and derived runtime data.
type MetagraphData struct {
	Metagraph              kami.SubnetMetagraph
	Interval               IntervalConfig
	CurrentActiveMinerUids []int64
}

// Completion associates a task prompt with a generic completion payload.
type Completion[T Codegen] struct {
	TaskPrompt string `json:"task_prompt"`
	Completion T      `json:"completion"`
}

// Codegen represents a generic code generation completion payload.
type Codegen struct {
	Completion any `json:"completion"`
}
