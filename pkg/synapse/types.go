package synapse

import "time"

type Config struct {
	Address       string
	ClientTimeout time.Duration
	RetryMax      int
	RetryWait     time.Duration
}

type HeartbeatRequest struct {
	ValidatorID string                 `json:"validator_id"`
	Timestamp   int64                  `json:"timestamp"`
	Payload     map[string]interface{} `json:"payload,omitempty"`
}

type HeartbeatResponse struct {
	Status     string `json:"status"`
	ReceivedAt int64  `json:"received_at"`
	Message    string `json:"message,omitempty"`
}
