package miner

import (
	"github.com/tensorplex-labs/dojo/internal/core"
	"github.com/tensorplex-labs/dojo/pkg/config"
	"github.com/tensorplex-labs/dojo/pkg/schnitz"
)

type Miner struct {
	*core.Node
	server *schnitz.Server
	config *config.MinerEnvConfig
}
