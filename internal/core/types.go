package core

import (
	"time"

	"github.com/tensorplex-labs/dojo/internal/scheduler"
	"github.com/tensorplex-labs/dojo/pkg/chain"
)

const (
	IntervalMetagraphSync int           = 10
	BlockTime             time.Duration = 12 * time.Second
)

type Node struct {
	ChainRepo  chain.ChainProvider
	callbacks  []scheduler.CallbackHandler
	ChainState *chain.ChainState
}
