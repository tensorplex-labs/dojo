package chain

import (
	"context"
	"sync"

	"github.com/rs/zerolog/log"
	"github.com/sethvargo/go-envconfig"
	"github.com/tensorplex-labs/dojo/pkg/config"
)

var stateMutex sync.RWMutex

func init() {
	stateMutex = sync.RWMutex{}
}

type ChainProvider interface {
	GetLatestBlock() func(*ChainState) (*ChainState, error)
	GetSubnetMetagraph(netuid int) func(*ChainState) (*ChainState, error)
	GetKeyringPairInfo() func(*ChainState) (*ChainState, error)
	SetIP(ip string, port int) error
}

// ChainState holds the current state of the chain, including the latest block, metagraph, and netuid.
// It uses a mutex to ensure thread-safe access to its fields.
type ChainState struct {
	netuid    int
	block     int
	metagraph SubnetMetagraph
}

func NewChainState() *ChainState {
	ctx := context.Background()

	var envCfg config.ChainEnvConfig
	if err := envconfig.Process(ctx, &envCfg); err != nil {
		log.Fatal().Err(err).Msg("Failed to process environment variables for Chain")
	}

	return &ChainState{
		block:     0,
		metagraph: SubnetMetagraph{},
		netuid:    envCfg.Netuid,
	}
}

// GetBlock safely reads the current block number
func (cs *ChainState) GetBlock() int {
	stateMutex.RLock()
	defer stateMutex.RUnlock()
	return cs.block
}

// GetMetagraph safely reads the current metagraph
func (cs *ChainState) GetMetagraph() SubnetMetagraph {
	stateMutex.RLock()
	defer stateMutex.RUnlock()
	return cs.metagraph
}

func (cs *ChainState) GetNetuid() int {
	stateMutex.RLock()
	defer stateMutex.RUnlock()
	return cs.netuid
}

// SetBlock safely updates the block number
func (cs *ChainState) SetBlock(block int) {
	stateMutex.Lock()
	defer stateMutex.Unlock()
	cs.block = block
}

// SetMetagraph safely updates the metagraph
func (cs *ChainState) SetMetagraph(metagraph SubnetMetagraph) {
	stateMutex.Lock()
	defer stateMutex.Unlock()
	cs.metagraph = metagraph
}

// SetNetuid safely updates the netuid
func (cs *ChainState) SetNetuid(netuid int) {
	stateMutex.Lock()
	defer stateMutex.Unlock()
	cs.netuid = netuid
}

// UpdateBlock atomically updates the block number and returns a new state
func (cs *ChainState) UpdateBlock(block int) *ChainState {
	stateMutex.Lock()
	defer stateMutex.Unlock()
	if block <= cs.block {
		// If the new block is not greater than the current block, return the same state
		log.Warn().
			Int("current_block", cs.block).
			Int("new_block", block).
			Msg("new block is <= current block, not updating state")
		return cs
	}

	newState := &ChainState{
		block:     block,
		netuid:    cs.netuid,
		metagraph: cs.metagraph,
	}
	return newState
}

// UpdateMetagraph atomically updates the metagraph and returns a new state
func (cs *ChainState) UpdateMetagraph(metagraph SubnetMetagraph) *ChainState {
	stateMutex.Lock()
	defer stateMutex.Unlock()
	newState := &ChainState{
		block:     cs.block,
		netuid:    cs.netuid,
		metagraph: metagraph,
	}
	return newState
}
