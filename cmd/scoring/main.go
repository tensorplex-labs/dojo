package main

import (
	"github.com/rs/zerolog/log"

	"github.com/tensorplex-labs/dojo/internal/scoring"
	"github.com/tensorplex-labs/dojo/internal/utils/logger"
)

func main() {
	logger.Init()

	testCalcPvPScores()
	testCalcTrapScores()
	testCalcPvVScores()
}

func testCalcPvPScores() {
	log.Info().Msg("--- Testing CalcPvPScores ---")
	generators := map[string]string{
		"g1": "out1",
		"g2": "out2",
	}
	discriminators := map[string]string{
		"d1": "out1",
		"d2": "out1",
		"d3": "out1",
		"d4": "out2",
		"d5": "out2",
	}

	scores := scoring.CalcPvPScores(discriminators, generators)
	for addr, score := range scores {
		log.Info().Str("addr", addr).Float64("score", score).Msgf("addr %s scored %f", addr, score)
	}
}

func testCalcTrapScores() {
	log.Info().Msg("--- Testing CalcTrapScores ---")
	positiveGenerators := map[string]string{
		"pg1": "p_out",
	}
	negativeGenerators := map[string]string{
		"ng1": "n_out",
	}
	discriminators := map[string]string{
		"d1": "p_out",
		"d2": "p_out",
		"d3": "p_out",
		"d4": "n_out",
		"d5": "n_out",
	}

	scores := scoring.CalcTrapScores(discriminators, positiveGenerators, negativeGenerators)
	for addr, score := range scores {
		log.Info().Str("addr", addr).Float64("score", score).Msgf("addr %s scored %f", addr, score)
	}
}

func testCalcPvVScores() {
	log.Info().Msg("--- Testing CalcPvVScores ---")
	validators := map[string]string{
		"v1": "out1",
	}
	generators := map[string]string{
		"g1": "out2", // Output is another generator's completion to test implementation
	}
	discriminators := map[string]string{
		"d1": "out1", // Vote for a validator's completion
		"d2": "out1", // Vote for a validator's completion
		"d3": "out2", // Vote for a generator's completion
		"d4": "out1",
		"d5": "out1",
	}

	scores := scoring.CalcPvVScores(discriminators, generators, validators)
	for addr, score := range scores {
		log.Info().Str("addr", addr).Float64("score", score).Msgf("addr %s scored %f", addr, score)
	}
}
