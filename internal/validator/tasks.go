package validator

import (
	"context"
	"fmt"
	"time"

	"github.com/rs/zerolog/log"
	"github.com/tensorplex-labs/dojo/internal/synapse"
	chainutils "github.com/tensorplex-labs/dojo/internal/utils/chain_utils"
)

func (v *Validator) heartBeat(ctx context.Context, client *synapse.Client, validatorHotkey string) {
	hb := synapse.HeartbeatRequest{
		ValidatorHotkey: validatorHotkey,
		Timestamp:       time.Now().UnixNano(),
	}

	currentAxons := v.MetagraphData.Metagraph.Axons
	if len(currentAxons) == 0 {
		return
	}

	for uid, axon := range currentAxons {
		rootStake := v.MetagraphData.Metagraph.TaoStake[uid]
		alphaStake := v.MetagraphData.Metagraph.AlphaStake[uid]
		miner, err := chainutils.CheckIfMiner(alphaStake, rootStake)
		if err != nil {
			log.Error().Err(err).Msg("failed to check miner status")
			continue
		}

		if !miner {
			continue
		}

		url := fmt.Sprintf("http://%s/%d/heartbeat", axon.IP, axon.Port)
		resp, err := client.SendHeartbeat(ctx, url, hb)
		if err != nil {
			log.Error().Err(err).Str("url", url).Msg("send heartbeat failed")
			continue
		}

		if resp.Status != "ok" {
			log.Warn().Str("url", url).Str("status", resp.Status).Msg("non-ok heartbeat response")
		}
	}
}

func (v *Validator) syncMetagraph() {
	v.mu.Lock()
	log.Info().Msg(fmt.Sprintf("syncing metagraph data for subnet: %d", v.ValidatorConfig.Netuid))
	// Placeholder for actual metagraph sync logic
	// This would typically involve fetching the latest metagraph from a source
	// and updating v.MetagraphData accordingly.
	newMetagraph, err := v.Kami.GetMetagraph(v.ValidatorConfig.Netuid)
	if err != nil {
		log.Error().Err(err).Msg("failed to get metagraph")
		return
	}
	v.MetagraphData.Metagraph = newMetagraph.Data
	v.mu.Unlock()
}

func (v *Validator) syncBlock() {
	v.mu.Lock()
	log.Info().Msg(fmt.Sprintf("syncing latest block. current block : %d", v.LatestBlock))
	newBlockResp, err := v.Kami.GetLatestBlock()
	if err != nil {
		log.Error().Err(err).Msg("failed to get latest block")
		return
	}

	v.LatestBlock = int64(newBlockResp.Data.BlockNumber)
	v.mu.Unlock()
}

func (v *Validator) sendTaskRound() {
	ctx := v.Ctx
	if v.Redis == nil {
		log.Error().Msg("redis client is not initialized")
		return
	}

	taskCount, err := v.Redis.LLen(ctx, "synthetic:questions")
	if err != nil {
		log.Error().Err(err).Msg("failed to get task count from redis")
		return
	}

	if taskCount < 25 { // TODO: this should be CURRENT_ACTIVE_MINER_UIDS
		log.Info().Msg("not enough tasks in redis, skipping task round")
		return
	}

	log.Info().Msg(fmt.Sprintf("sending task round with %d tasks", taskCount))
	for i := 0; i < int(taskCount); i++ {
		synApiQuestion, err := v.SyntheticApi.GetQuestion()
		if err != nil {
			log.Error().Err(err).Msg("failed to get question from synthetic API")
			return
		}
		log.Debug().Msgf("Received question: %s of id: %s", synApiQuestion.Prompt, synApiQuestion.Qa_Id)

	}
}
