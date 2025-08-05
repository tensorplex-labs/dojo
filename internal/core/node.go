package core

import (
	"context"
	"time"

	"github.com/rs/zerolog/log"
	"github.com/tensorplex-labs/dojo/internal/scheduler"
	"github.com/tensorplex-labs/dojo/pkg/chain"
)

func NewNode(chainRepo chain.ChainProvider) *Node {
	return &Node{
		ChainRepo:  chainRepo,
		ChainState: chain.NewChainState(),
	}
}

func (c *Node) RegisterCallback(callback scheduler.CallbackHandler) {
	c.callbacks = append(c.callbacks, callback)
	log.Debug().Str("callback", callback.GetName()).Msg("Registered callback")
}

func (c *Node) BlockUpdater() {
	for {
		currBlock := c.ChainState.GetBlock()
		latestBlockFn := c.ChainRepo.GetLatestBlock()
		latestState, err := latestBlockFn(c.ChainState)
		if err != nil {
			log.Error().Err(err).Msg("Failed to update latest block")
			continue
		}
		c.ChainState = latestState

		log.Info().
			Int("previous_block", currBlock).
			Int("current_block", latestState.GetBlock()).
			Msg("Updated latest block")

		c.onBlockUpdate()
		time.Sleep(BlockTime)
	}
}

func (c *Node) onBlockUpdate() {
	state := c.ChainState
	for _, callback := range c.callbacks {
		if callback.ShouldTrigger(state) {
			log.Info().
				Str("callback", callback.GetName()).
				Msg("Executing callback")

			if err := callback.Execute(); err != nil {
				log.Error().
					Err(err).
					Str("callback", callback.GetName()).
					Msg("Failed to execute callback")
			} else {
				log.Info().
					Str("callback", callback.GetName()).
					Msg("Callback executed successfully")
			}

			if blockCallback, ok := callback.(*scheduler.BlockCallback); ok {
				blockCallback.LastTriggerAtBlock = state.GetBlock()
			}
		}
	}
}

func (c *Node) MetagraphSync() error {
	updateMetagraphFn := c.ChainRepo.GetSubnetMetagraph(c.ChainState.GetNetuid())
	updatedState, err := updateMetagraphFn(c.ChainState)
	if err != nil {
		log.Error().Err(err).Msg("Failed to update metagraph")
		return err
	}
	c.ChainState = updatedState
	log.Info().Msg("Updated metagraph")
	return nil
}

func (c *Node) StartBlockUpdater() {
	go c.BlockUpdater()
}

func (c *Node) Start(ctx context.Context) error {
	log.Info().Msg("Node started")
	return nil
}

func (c *Node) Stop() error {
	log.Info().Msg("Node stopped")
	return nil
}

func (c *Node) RegisterMetagraphSync() {
	c.RegisterCallback(scheduler.NewBlockCallback(
		IntervalMetagraphSync,
		c.MetagraphSync,
	))
}
