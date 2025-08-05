package scheduler

import (
	"github.com/tensorplex-labs/dojo/pkg/chain"
)

// NewBlockCallback creates a new BlockCallback that triggers every N blocks
func NewBlockCallback(interval int, execute func() error) *BlockCallback {
	return &BlockCallback{
		LastTriggerAtBlock: -1,
		interval:           interval,
		executeFn:          execute,
	}
}

// ShouldTrigger checks if the callback should trigger based on block interval and missed blocks
func (bc *BlockCallback) ShouldTrigger(state *chain.ChainState) bool {
	currentBlock := state.GetBlock()

	// If this is the first time, trigger if we're at the right interval
	if bc.LastTriggerAtBlock <= 0 {
		return currentBlock%bc.interval == 0
	}

	// Check if we should have triggered based on interval
	blocksSinceLastTrigger := currentBlock - bc.LastTriggerAtBlock
	return blocksSinceLastTrigger >= bc.interval
}

// Execute runs the callback and updates the last trigger block
func (bc *BlockCallback) Execute() error {
	err := bc.executeFn()
	// Update lastTriggerAtBlock only if execution was successful
	// This way, failed executions will retry on the next block
	return err
}

// GetName returns the callback name
func (bc *BlockCallback) GetName() string {
	return InferNameFromFunc(bc.executeFn)
}
