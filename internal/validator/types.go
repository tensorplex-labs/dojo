package validator

import (
	"time"

	"github.com/tensorplex-labs/dojo/internal/kami"
)

type IntervalConfig struct {
	HeartbeatInterval time.Duration
	MetagraphInterval time.Duration
	TaskRoundInterval time.Duration
	BlockInterval     time.Duration
}

type MetagraphData struct {
	Metagraph kami.SubnetMetagraph //  index of array is uids, e.g. [0] is uid 0 then its value is the axon
	Interval  IntervalConfig
}

type Completion[T Codegen] struct {
	TaskPrompt string `json:"task_prompt"`
	Completion T      `json:"completion"`
}

type Codegen struct {
	Completion interface{} `json:"completion"` // This can be a string or a more complex type depending on the task
}
