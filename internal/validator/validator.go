package validator

import (
	"context"
	"fmt"
	"net/url"

	"github.com/rs/zerolog/log"

	"github.com/sethvargo/go-envconfig"
	"github.com/tensorplex-labs/dojo/internal/core"
	"github.com/tensorplex-labs/dojo/internal/scheduler"
	"github.com/tensorplex-labs/dojo/pkg/chain"
	"github.com/tensorplex-labs/dojo/pkg/config"
	"github.com/tensorplex-labs/dojo/pkg/schnitz"
)

const (
	IntervalHeartbeat int = 10
)

func NewValidator(chainRepo chain.ChainProvider) *Validator {
	client, err := schnitz.NewClient(nil)
	if err != nil {
		panic("failed to create schnitz client: " + err.Error())
	}
	ctx := context.Background()

	var envCfg config.ValidatorEnvConfig
	if err := envconfig.Process(ctx, &envCfg); err != nil {
		log.Fatal().Err(err).Msg("Failed to process environment variables for Validator")
	}

	return &Validator{
		Node:   core.NewNode(chainRepo),
		client: client,
		config: envCfg,
	}
}

func (v *Validator) Run() {
	ctx := context.Background()
	if err := v.Node.Start(ctx); err != nil {
		log.Fatal().Err(err).Msg("Failed to start node")
	}
	// Run once to initialize the state
	v.MetagraphSync()
	v.RegisterMetagraphSync()

	sendHeartbeatsCallback := scheduler.NewBlockCallback(IntervalHeartbeat, v.sendHeartbeats)
	v.RegisterCallback(sendHeartbeatsCallback)
	v.StartBlockUpdater()

	// TODO: scoring logic
}

func (v *Validator) sendHeartbeats() error {
	subnetMetagraph := v.Node.ChainState.GetMetagraph()
	log.Debug().Interface("metagraph", subnetMetagraph).Msg("Retrieved subnet metagraph")
	if len(subnetMetagraph.Axons) == 0 {
		log.Warn().Msg("No axons found in subnet metagraph, skipping heartbeats")
		return nil
	}

	var urls []string
	var requests []core.Heartbeat
	var responses []*core.Heartbeat

	for _, axon := range subnetMetagraph.Axons {
		isUrl, url := ParseUrl(fmt.Sprintf("http://%s:%d", axon.IP, axon.Port))
		if !isUrl {
			log.Trace().Interface("axon", axon).Msg("Invalid axon URL, skipping heartbeat")
			continue
		}

		log.Debug().Str("axon", url.String()).Msg("Sending heartbeat to axon")
		urls = append(urls, url.String())
		request := core.Heartbeat{Ack: false}
		requests = append(requests, request)
		responses = append(responses, &core.Heartbeat{})
	}

	if len(urls) == 0 {
		log.Warn().Msg("No valid axon URLs found, skipping heartbeats")
		return nil
	}

	authParams, err := v.client.CreateAuthParams()
	if err != nil {
		log.Error().Err(err).Msg("Failed to create auth params")
		return err
	}

	_ = schnitz.SendMany(v.client, urls, requests, responses, authParams)
	for i, resp := range responses {
		if resp.Ack {
			log.Info().Str("axon", urls[i]).Msg("Received heartbeat acknowledgment from axon")
		} else {
			log.Warn().Str("axon", urls[i]).Msg("No acknowledgment received from axon")
		}
	}

	return nil
}

func ParseUrl(str string) (bool, *url.URL) {
	u, err := url.Parse(str)
	isUrl := err == nil && u.Scheme != "" && u.Hostname() != ""
	return isUrl, u
}
