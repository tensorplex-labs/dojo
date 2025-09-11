// Package validator contains the validator orchestration logic and types used
// to coordinate task rounds, metagraph synchronization, and API interactions.
package validator

import (
	"time"

	"github.com/tensorplex-labs/dojo/internal/kami"
)

// IntervalConfig groups ticker intervals used by the validator runtime.
type IntervalConfig struct {
	HeartbeatInterval     time.Duration
	MetagraphInterval     time.Duration
	TaskRoundInterval     time.Duration
	BlockInterval         time.Duration
	WeightSettingInterval time.Duration
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

// CachedTasks represents redis cached values for tasks
type CachedTasks struct {
	Question string `json:"question"`
	QaID     string `json:"qa_id"`
	AnsAugID string `json:"ans_aug_id"`
}

const (
	scoresFileName   string  = "scores.json"
	decayFactor      float32 = 0.9
	uidCount         int     = 256
	scoringStepLimit int     = 4
)

type ScoresFileData struct {
	Scores []float64 `json:"scores"`
	Step   int       `json:"step"`
}
