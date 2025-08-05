package validator

import (
	"github.com/tensorplex-labs/dojo/internal/core"
	"github.com/tensorplex-labs/dojo/pkg/config"
	"github.com/tensorplex-labs/dojo/pkg/schnitz"
)

type Validator struct {
	*core.Node
	client *schnitz.Client
	config config.ValidatorEnvConfig
}
