package scheduler

import "github.com/tensorplex-labs/dojo/pkg/chain"

// BlockCallback is a callback that triggers every N blocks
// WARN: if the block updater hangs, i.e. we have a callback that triggers every N blocks,
// and the current block VS last trigger block is multiples of N, it will only trigger once
// instead of calling (current block - last trigger block) / N times.
type BlockCallback struct {
	LastTriggerAtBlock int
	// interval is the number of blocks between triggers
	interval  int
	executeFn func() error
}

type CallbackHandler interface {
	// Determines if the callback should trigger based on the current chain state
	ShouldTrigger(*chain.ChainState) bool
	// Executes the callback logic and returns an error if it fails
	Execute() error
	// Returns the name of the callback, which may be inferred from the function name
	GetName() string
}
